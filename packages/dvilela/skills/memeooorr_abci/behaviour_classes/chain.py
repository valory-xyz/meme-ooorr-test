# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 David Vilela Freire
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains round behaviours of MemeooorrAbciApp."""

import json
from abc import ABC
from copy import copy
from datetime import datetime
from typing import Generator, List, Optional, Tuple, Type, cast

from packages.dvilela.contracts.meme.contract import MemeContract
from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    ActionPreparationPayload,
    ActionPreparationRound,
    CheckFundsPayload,
    CheckFundsRound,
    DeploymentPayload,
    DeploymentRound,
    Event,
    PullMemesPayload,
    PullMemesRound,
    TransactionMultiplexerPayload,
    TransactionMultiplexerRound,
)
from packages.valory.contracts.gnosis_safe.contract import GnosisSafeContract
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)
from packages.valory.skills.transaction_settlement_abci.rounds import TX_HASH_LENGTH


BASE_CHAIN_ID = "base"
EMPTY_CALL_DATA = b"0x"
SAFE_GAS = 0
ZERO_VALUE = 0
TWO_MINUTES = 120
SUMMON_BLOCK_DELTA = 100000
HTTP_OK = 200
AVAILABLE_ACTIONS = ["hearth", "unleash", "collect", "purge", "burn"]

TOKENS_QUERY = """
query Tokens {
  memeTokens {
    items {
      blockNumber
      chain
      heartCount
      id
      isUnleashed
      liquidity
      lpPairAddress
      owner
      timestamp
    }
  }
}
"""


class ChainBehaviour(MemeooorrBaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """ChainBehaviour"""

    def _build_safe_tx_hash(
        self,
        to_address: str,
        value: int = ZERO_VALUE,
        data: bytes = EMPTY_CALL_DATA,
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash for a tx."""

        self.context.logger.info(
            f"Preparing Safe transaction [{self.synchronized_data.safe_contract_address}]"
        )

        # Prepare the safe transaction
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.synchronized_data.safe_contract_address,
            contract_id=str(GnosisSafeContract.contract_id),
            contract_callable="get_raw_safe_transaction_hash",
            to_address=to_address,
            value=value,
            data=data,
            safe_tx_gas=SAFE_GAS,
            chain_id=BASE_CHAIN_ID,
        )

        # Check for errors
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                "Couldn't get safe tx hash. Expected response performative "
                f"{ContractApiMessage.Performative.STATE.value!r}, "  # type: ignore
                f"received {response_msg.performative.value!r}: {response_msg}."
            )
            return None

        # Extract the hash and check it has the correct length
        tx_hash: Optional[str] = cast(str, response_msg.state.body.get("tx_hash", None))

        if tx_hash is None or len(tx_hash) != TX_HASH_LENGTH:
            self.context.logger.error(
                "Something went wrong while trying to get the safe transaction hash. "
                f"Invalid hash {tx_hash!r} was returned."
            )
            return None

        # Transaction to hex
        tx_hash = tx_hash[2:]  # strip the 0x

        safe_tx_hash = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=value,
            safe_tx_gas=SAFE_GAS,
            to_address=to_address,
            data=data,
        )

        self.context.logger.info(f"Safe transaction hash is {safe_tx_hash}")

        return safe_tx_hash

    def store_hearth(self, token_address: str) -> Generator[None, None, None]:
        """Store a new hearthed token to the db"""
        # Load previously hearthed memes
        db_data = yield from self._read_kv(keys=("hearthed_memes",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            hearthed_memes = []
        else:
            hearthed_memes = json.loads(db_data["hearthed_memes"] or "[]")

        # Write the new hearthed token
        hearthed_memes.append(token_address)
        yield from self._write_kv(
            {"hearthed_memes": json.dumps(hearthed_memes, sort_keys=True)}
        )
        self.context.logger.info("Wrote latest hearthed token to db")


class CheckFundsBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """CheckFundsBehaviour"""

    matching_round: Type[AbstractRound] = CheckFundsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = yield from self.get_event()

            payload = CheckFundsPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> Generator[None, None, str]:
        """Get the next event"""

        # Gas check
        native_balance = yield from self.get_native_balance()
        if native_balance < self.params.minimum_gas_balance:
            return Event.NO_FUNDS.value

        return Event.DONE.value

    def get_native_balance(self) -> Generator[None, None, Optional[float]]:
        """Get the native balance"""
        self.context.logger.info(
            f"Getting native balance for Safe {self.synchronized_data.safe_contract_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=BASE_CHAIN_ID,
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            return None

        balance = cast(float, ledger_api_response.state.body["get_balance_result"])
        balance = balance / 10**18  # from wei

        self.context.logger.error(f"Got native balance: {balance}")

        return balance


class DeploymentBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """DeploymentBehaviour"""

    matching_round: Type[AbstractRound] = DeploymentRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash, tx_flag, token_address = yield from self.get_tx_hash()

            payload = DeploymentPayload(
                sender=self.context.agent_address,
                tx_hash=tx_hash,
                tx_flag=tx_flag,
                token_address=token_address,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(
        self,
    ) -> Generator[None, None, Tuple[Optional[str], Optional[str], Optional[str]]]:
        """Prepare the next transaction"""

        tx_flag: Optional[str] = self.synchronized_data.tx_flag
        tx_hash: Optional[str] = None

        # Deploy
        if not tx_flag:
            tx_hash = yield from self.get_deployment_tx()
            tx_flag = "deploy"
            token_address = None
            return tx_hash, tx_flag, token_address

        # Finished
        self.context.logger.info("The deployment has finished")
        tx_hash = None
        tx_flag = "done"
        token_address = yield from self.get_token_address()
        if not token_address:
            return None, None, None

        # Read previous tokens from db
        db_data = yield from self._read_kv(keys=("tokens",))

        if db_data is None:
            self.context.logger.error("Error while loading tokens from the database")
            tokens = []
        else:
            tokens = json.loads(db_data["tokens"]) if db_data["tokens"] else []

        # Write token to db
        token_data = self.synchronized_data.token_data
        token_data["token_address"] = token_address
        tokens.append(token_data)
        yield from self._write_kv({"tokens": json.dumps(tokens, sort_keys=True)})
        self.context.logger.info("Wrote latest token to db")
        self.store_hearth(token_address)

        return tx_hash, tx_flag, token_address

    def get_deployment_tx(self) -> Generator[None, None, Optional[str]]:
        """Prepare a deployment tx"""

        # Transaction data
        data_hex = yield from self.get_deployment_data()

        # Check for errors
        if data_hex is None:
            return None

        # Prepare safe transaction
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.meme_factory_address,
            data=bytes.fromhex(data_hex),
            value=int(self.params.deployment_amount_eth * 1e18),
        )

        self.context.logger.info(f"Deployment hash is {safe_tx_hash}")

        return safe_tx_hash

    def get_deployment_data(self) -> Generator[None, None, Optional[str]]:
        """Get the deployment transaction data"""

        token_data = self.synchronized_data.token_data
        self.context.logger.info(
            f"Preparing deployment transaction. token_data={token_data}"
        )

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="build_summon_tx",
            token_name=token_data["token_name"],
            token_ticker=token_data["token_ticker"],
            total_supply=int(self.params.total_supply),
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while building the deployment tx: {response_msg}"
            )
            return None

        data_bytes: Optional[bytes] = cast(
            bytes, response_msg.raw_transaction.body.get("data", None)
        )

        # Ensure that the data is not None
        if data_bytes is None:
            self.context.logger.error(
                f"Error while preparing the transaction: {response_msg}"
            )
            return None

        data_hex = data_bytes.hex()
        self.context.logger.info(f"Deployment data is {data_hex}")
        return data_hex

    def get_token_address(
        self,
    ) -> Generator[None, None, Optional[str]]:
        """Get the data from the deployment event"""

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_token_data",
            tx_hash=self.synchronized_data.final_tx_hash,
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the token data: {response_msg}")
            return None

        token_address = cast(str, response_msg.state.body.get("token_address", None))
        self.context.logger.info(f"Token address is {token_address}")
        return token_address


class PullMemesBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """PullMemesBehaviour"""

    matching_round: Type[AbstractRound] = PullMemesRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            meme_coins = yield from self.get_meme_coins_from_subgraph()

            payload = PullMemesPayload(
                sender=self.context.agent_address,
                meme_coins=json.dumps(meme_coins, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_meme_coins_from_chain(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""

        current_block = yield from self.get_block_number()

        if not current_block:
            return None

        # Get the event from the latest 100k blocks
        from_block = current_block - SUMMON_BLOCK_DELTA

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_events",
            from_block=from_block,
            event_name="Summoned",
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin events: {response_msg}"
            )
            return None

        events = cast(list, response_msg.state.body.get("events", None))

        if events is None:
            self.context.logger.error("Could not get the memecoin events")
            return None

        self.context.logger.info(f"Got {len(events)} summon events")

        meme_coins = yield from self.analyze_summon_events(events)

        return meme_coins

    def get_block_number(self) -> Generator[None, None, Optional[int]]:
        """Get the block number"""

        # Call the ledger connection (equivalent to web3.py)
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_block_number",
            chain_id=BASE_CHAIN_ID,
        )

        # Check for errors on the response
        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving block number: {ledger_api_response}"
            )
            return None

        # Extract and return the block number
        block_number = cast(
            int, ledger_api_response.state.body["get_block_number_result"]
        )

        self.context.logger.error(f"Got block number: {block_number}")

        return block_number

    def analyze_summon_events(
        self, events: List
    ) -> Generator[None, None, Optional[List]]:
        """Analyze summon events"""

        meme_coins = []

        # Load previously hearthed memes
        db_data = yield from self._read_kv(keys=("hearthed_memes",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            hearthed_memes: List[str] = []
        else:
            hearthed_memes = db_data["hearthed_memes"] or []

        for event in events:
            meme_address = event["token_address"]
            available_actions = yield from self.get_meme_available_actions(
                meme_address, hearthed_memes
            )
            meme_coin = {"token_address": meme_address, "actions": available_actions}
            meme_coins.append(meme_coin)

        self.context.logger.info(f"Analyzed meme coins: {meme_coins}")

        return meme_coins

    def get_meme_coins_from_subgraph(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""

        url = "https://memeooorr-subgraph-production.up.railway.app/"

        query = {"query": TOKENS_QUERY}

        # Make the HTTP request
        response = yield from self.get_http_response(
            method="POST", url=url, content=json.dumps(query).encode()
        )

        # Handle HTTP errors
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Error while pulling the memes from subgraph: {response.body!r}"
            )

        # Load the response
        response_json = json.loads(response.body)
        meme_coins = [
            {
                "token_address": t["id"],
                "liquidity": int(t["liquidity"]),
                "heart_count": int(t["heartCount"]),
                "is_unleashed": t["isUnleashed"],
                "timestamp": t["timestamp"],
            }
            for t in response_json["data"]["memeTokens"]["items"]
            if t["chain"] == "base"  # TODO: adapt to Celo
        ]

        enriched_meme_coins = yield from self.get_extra_meme_info(meme_coins)

        return enriched_meme_coins

    def get_extra_meme_info(self, meme_coins: List) -> Generator[None, None, List]:
        """Get the meme coin names, symbols and other info"""

        enriched_meme_coins = []

        for meme_coin in meme_coins:
            response_msg = yield from self.get_contract_api_response(
                performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
                contract_address=meme_coin["token_address"],
                contract_id=str(MemeContract.contract_id),
                contract_callable="get_token_data",
                chain_id=BASE_CHAIN_ID,
            )

            # Check that the response is what we expect
            if response_msg.performative != ContractApiMessage.Performative.STATE:
                self.context.logger.error(
                    f"Error while getting the token data: {response_msg}"
                )
                continue

            meme_coin["name"] = response_msg.raw_transaction.body.get("name")
            meme_coin["symbol"] = response_msg.raw_transaction.body.get("symbol")
            meme_coin["total_supply"] = response_msg.raw_transaction.body.get(
                "total_supply"
            )
            meme_coin["decimals"] = response_msg.raw_transaction.body.get("decimals")

            # Load previously hearthed memes
            db_data = yield from self._read_kv(keys=("hearthed_memes",))

            if db_data is None:
                self.context.logger.error("Error while loading the database")
                hearthed_memes: List[str] = []
            else:
                hearthed_memes = db_data["hearthed_memes"] or []

            # Get available actions
            available_actions = yield from self.get_meme_available_actions(
                meme_coin["token_address"], hearthed_memes
            )
            meme_coin["available_actions"] = available_actions

            enriched_meme_coins.append(meme_coin)

        return enriched_meme_coins

    def get_meme_available_actions(
        self, meme_address: str, hearthed_memes: List[str]
    ) -> Generator[None, None, Optional[List]]:
        """Get the available actions"""

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_summon_data",
            meme_address=meme_address,
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin summon data: {response_msg}"
            )
            return None

        # Extract the data
        summon_time_ts = cast(int, response_msg.state.body.get("summon_time", 0))
        unleash_time_ts = cast(int, response_msg.state.body.get("unleash_time", 0))

        self.context.logger.info(
            f"Token {meme_address} summon_time_ts={summon_time_ts} unleash_time_ts={unleash_time_ts}"
        )

        # Get the times
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        summon_time = datetime.fromtimestamp(summon_time_ts)
        seconds_since_summon = (now - summon_time).total_seconds()

        available_actions = copy(AVAILABLE_ACTIONS)

        # We can unleash if it has not been unleashed
        if unleash_time_ts != 0:
            available_actions.remove("unleash")

        # We can hearth during the first 48h
        if seconds_since_summon > 48 * 3600:
            available_actions.remove("hearth")

        # We use 47.5 to be on the safe side
        if seconds_since_summon < 47.5 * 3600:
            available_actions.remove("unleash")
            available_actions.remove("purge")
            available_actions.remove("burn")

            # We can collect if we have hearthed this token
            if meme_address not in hearthed_memes:
                available_actions.remove("collect")

        return available_actions


class ActionPreparationBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """ActionPreparationBehaviour"""

    matching_round: Type[AbstractRound] = ActionPreparationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash, tx_flag = yield from self.get_tx_hash()

            payload = ActionPreparationPayload(
                sender=self.context.agent_address,
                tx_hash=tx_hash,
                tx_flag=tx_flag,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(self) -> Generator[None, None, Tuple[Optional[str], Optional[str]]]:
        """Get the action transaction hash"""

        token_action = self.synchronized_data.token_action

        if not token_action:
            return None, None

        token_address = token_action["token_address"]
        action = token_action["action"]

        contract_callable = f"build_{action}_tx"

        kwargs = {}

        if action != "burn":
            kwargs["meme_address"] = token_address

        self.context.logger.info(
            f"Preparing the {action} transaction for token {token_address}. kwargs={kwargs}"
        )

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable=contract_callable,
            chain_id=BASE_CHAIN_ID,
            **kwargs,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while building the {action} tx: {response_msg}"
            )
            return None, None

        data_bytes: Optional[bytes] = cast(
            bytes, response_msg.raw_transaction.body.get("data", None)
        )

        # Ensure that the data is not None
        if data_bytes is None:
            self.context.logger.error(
                f"Error while preparing the transaction: {response_msg}"
            )
            return None, None

        data_hex = data_bytes.hex()
        self.context.logger.info(f"Tx data is {data_hex}")

        # Check for errors
        if data_hex is None:
            return None, None

        # Prepare safe transaction
        value = (
            ZERO_VALUE
            if action != "hearth"
            else self.params.hearth_amount_eth * int(1e18)
        )  # to wei
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.meme_factory_address,
            data=bytes.fromhex(data_hex),
            value=value,
        )

        # Optimistic design: we now store the hearthed token address
        # Ideally, this should be done after a succesful hearth transaction
        if action == "hearth":
            self.store_hearth(token_address)

        tx_flag = "action"
        return safe_tx_hash, tx_flag


class TransactionMultiplexerBehaviour(
    ChainBehaviour
):  # pylint: disable=too-many-ancestors
    """TransactionMultiplexerBehaviour"""

    matching_round: Type[AbstractRound] = TransactionMultiplexerRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = self.get_event()

            payload = TransactionMultiplexerPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(self) -> str:
        """Get the event"""

        tx_flag = self.synchronized_data.tx_flag

        if tx_flag == "deploy":
            return Event.TO_DEPLOY.value

        if tx_flag == "action":
            return Event.TO_ACTION_TWEET.value

        return Event.DONE.value
