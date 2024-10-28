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
from typing import Generator, Optional, Tuple, Type, cast

from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    CheckFundsPayload,
    CheckFundsRound,
    DeploymentPayload,
    DeploymentRound,
    Event,
)
from packages.valory.contracts.erc20.contract import ERC20
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


class CheckFundsBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
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


class DeploymentBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
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

        # Read previous tokens from db
        db_data = yield from self._read_kv(keys=("tokens",))

        if db_data is None:
            self.context.logger.error("Error while loading tokens from the database")
            tokens = []
        else:
            tokens = db_data["tokens"]

        # Write token to db
        token_data = self.synchronized_data.token_data
        token_data["token_address"] = token_data
        tokens.append(token_data)
        yield from self._write_kv({"tokens": json.dumps(tokens, sort_keys=True)})
        self.context.logger.info("Wrote latest token to db")

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

        # Use the contract api to interact with the ERC20 contract
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

    def _build_safe_tx_hash(
        self,
        to_address: str,
        value: int = ZERO_VALUE,
        data: bytes = EMPTY_CALL_DATA,
    ) -> Generator[None, None, Optional[str]]:
        """Prepares and returns the safe tx hash for a multisend tx."""

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

    def get_token_address(
        self,
    ) -> Generator[None, None, Optional[str]]:
        """Get the data from the deployment event"""

        # Use the contract api to interact with the ERC20 contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_event_data",
            tx_hash=self.synchronized_data.final_tx_hash,
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the event data: {response_msg}")
            return None

        token_address = cast(
            str, response_msg.raw_transaction.body.get("token_address", None)
        )
        return token_address
