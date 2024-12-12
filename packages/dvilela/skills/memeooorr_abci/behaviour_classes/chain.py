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
from typing import Generator, List, Optional, Tuple, Type, cast

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


EMPTY_CALL_DATA = b"0x"
SAFE_GAS = 0
ZERO_VALUE = 0
TWO_MINUTES = 120
SUMMON_BLOCK_DELTA = 100000
AVAILABLE_ACTIONS = ["heart", "unleash", "collect", "purge", "burn"]


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
            chain_id=self.get_chain_id(),
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

    def store_heart(self, token_nonce: int) -> Generator[None, None, None]:
        """Store a new hearted token to the db"""
        # Load previously hearted memes
        db_data = yield from self._read_kv(keys=("hearted_memes",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            hearted_memes = []
        else:
            hearted_memes = json.loads(db_data["hearted_memes"] or "[]")

        # Write the new hearted token
        hearted_memes.append(token_nonce)
        yield from self._write_kv(
            {"hearted_memes": json.dumps(hearted_memes, sort_keys=True)}
        )
        self.context.logger.info("Wrote latest hearted token to db")


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

        if not native_balance:
            return Event.NO_FUNDS.value

        if native_balance < self.params.minimum_gas_balance:
            return Event.NO_FUNDS.value

        return Event.DONE.value


class DeploymentBehaviour(ChainBehaviour):  # pylint: disable=too-many-ancestors
    """DeploymentBehaviour"""

    matching_round: Type[AbstractRound] = DeploymentRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tx_hash, tx_flag, token_nonce = yield from self.get_tx_hash()

            payload = DeploymentPayload(
                sender=self.context.agent_address,
                tx_hash=tx_hash,
                tx_flag=tx_flag,
                token_nonce=token_nonce,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(
        self,
    ) -> Generator[None, None, Tuple[Optional[str], Optional[str], Optional[int]]]:
        """Prepare the next transaction"""

        tx_flag: Optional[str] = self.synchronized_data.tx_flag
        tx_hash: Optional[str] = None

        # Deploy
        if not tx_flag:
            tx_hash = yield from self.get_deployment_tx()
            tx_flag = "deploy"
            token_nonce = None
            return tx_hash, tx_flag, token_nonce

        # Finished
        self.context.logger.info("The deployment has finished")
        tx_hash = None
        tx_flag = "done"
        token_nonce = yield from self.get_token_nonce()
        if not token_nonce:
            return None, None, None

        if not token_nonce:
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
        token_data["token_nonce"] = token_nonce
        tokens.append(token_data)
        yield from self._write_kv({"tokens": json.dumps(tokens, sort_keys=True)})
        self.context.logger.info("Wrote latest token to db")
        self.store_heart(token_nonce)

        return tx_hash, tx_flag, token_nonce

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
            value=int(self.synchronized_data.token_data["amount"]),
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
            total_supply=int(token_data["token_supply"]),
            chain_id=self.get_chain_id(),
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

    def get_token_nonce(
        self,
    ) -> Generator[None, None, Optional[int]]:
        """Get the data from the deployment event"""

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_token_data",
            tx_hash=self.synchronized_data.final_tx_hash,
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the token data: {response_msg}")
            return None

        token_nonce = cast(str, response_msg.state.body.get("token_nonce", None))
        self.context.logger.info(f"Token nonce is {token_nonce}")
        return token_nonce


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
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin summon events: {response_msg}"
            )
            return None

        summon_events = cast(list, response_msg.state.body.get("events", None))

        if summon_events is None:
            self.context.logger.error("Could not get the memecoin summon events")
            return None

        self.context.logger.info(f"Got {len(summon_events)} summon events")

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_events",
            from_block=from_block,
            event_name="Unleashed",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin unleash events: {response_msg}"
            )
            return None

        unleash_events = cast(list, response_msg.state.body.get("events", None))

        if unleash_events is None:
            self.context.logger.error("Could not get the memecoin unleash events")
            return None

        self.context.logger.info(f"Got {len(unleash_events)} unleash events")

        meme_coins = yield from self.analyze_events(summon_events, unleash_events)

        return meme_coins

    def get_block_number(self) -> Generator[None, None, Optional[int]]:
        """Get the block number"""

        # Call the ledger connection (equivalent to web3.py)
        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_block_number",
            chain_id=self.get_chain_id(),
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

    def analyze_events(
        self, summon_events: List, unleash_events: List
    ) -> Generator[None, None, Optional[List]]:
        """Analyze events"""

        # Merge event lists
        merged_event_dict = {e["token_nonce"]: e for e in summon_events}
        for e in unleash_events:
            merged_event_dict[e["token_nonce"]].update(e)
        merged_events = list(merged_event_dict.values())

        meme_coins = []

        # Load previously hearted memes
        db_data = yield from self._read_kv(keys=("hearted_memes",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            hearted_memes: List[str] = []
        else:
            hearted_memes = db_data["hearted_memes"] or []

        for event in merged_events:
            token_nonce = event["token_nonce"]
            token_address = event.get("token_address", None)
            available_actions = yield from self.get_meme_available_actions(
                token_nonce, token_address, hearted_memes
            )
            meme_coin = {"token_nonce": token_nonce, "actions": available_actions}
            meme_coins.append(meme_coin)

        self.context.logger.info(f"Analyzed meme coins: {meme_coins}")

        return meme_coins


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

        action = token_action["action"]

        contract_callable = f"build_{action}_tx"

        kwargs = {}

        if action in ["heart", "unleash"]:
            kwargs["meme_nonce"] = token_action["token_nonce"]

        if action in ["collect", "purge"]:
            kwargs["meme_address"] = token_action["token_address"]

        self.context.logger.info(f"Preparing the {action} transaction: kwargs={kwargs}")

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable=contract_callable,
            chain_id=self.get_chain_id(),
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
            ZERO_VALUE if action != "heart" else int(token_action["amount"])
        )  # to wei
        safe_tx_hash = yield from self._build_safe_tx_hash(
            to_address=self.params.meme_factory_address,
            data=bytes.fromhex(data_hex),
            value=value,
        )

        # Optimistic design: we now store the hearted token address
        # Ideally, this should be done after a succesful heart transaction
        if action == "heart":
            self.store_heart(token_action["token_nonce"])

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
