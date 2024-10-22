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
from typing import Generator, List, Optional, Tuple, Type, cast

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

        # ERC20 check
        erc20_balance = yield from self.get_erc20_balance()
        if erc20_balance < self.params.olas_per_pool:
            return Event.NO_FUNDS.value

        return Event.DONE.value

    def get_erc20_balance(self) -> Generator[None, None, Optional[float]]:
        """Get ERC20 balance"""
        self.context.logger.info(
            f"Getting Olas balance for Safe {self.synchronized_data.safe_contract_address}"
        )

        # Use the contract api to interact with the ERC20 contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=self.params.olas_token_address,
            contract_id=str(ERC20.contract_id),
            contract_callable="check_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=BASE_CHAIN_ID,
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Error while retrieving the balance: {response_msg}"
            )
            return None

        balance = response_msg.raw_transaction.body.get("token", None)

        # Ensure that the balance is not None
        if balance is None:
            self.context.logger.error(
                f"Error while retrieving the balance:  {response_msg}"
            )
            return None

        balance = balance / 10**18  # from wei

        self.context.logger.info(
            f"Account {self.synchronized_data.safe_contract_address} has {balance} Olas"
        )
        return balance

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

        balance = cast(int, ledger_api_response.state.body["get_balance_result"])
        balance = balance / 10**18  # from wei

        self.context.logger.error(f"Got native balance: {balance}")

        return balance


class DeploymentBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
    """DeploymentBehaviour"""

    matching_round: Type[AbstractRound] = DeploymentRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            pending_deployments, tx_hash = yield from self.get_tx_hash()

            payload = DeploymentPayload(
                sender=self.context.agent_address,
                pending_deployments=json.dumps(pending_deployments, sort_keys=True),
                tx_hash=tx_hash,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_tx_hash(self) -> Generator[None, None, Tuple[List, str]]:
        """Prepare the next transaction"""

        # Have we just came back from deploying?

        # Get the first tweet in the queue
        pending_deployments = self.synchronized_data.pending_deployments
        tx_hash = None

        if not pending_deployments[0]["is_deployed"]:
            tx_hash = yield from self.get_deployment_tx()
            pending_deployments[0]

        if not pending_deployments[0]["is_funded"]:
            tx_hash = yield from self.get_deployment_tx()

        raise ValueError("This token has been already deployed and funded")

    def get_deployment_tx(self) -> Generator[None, None, str]:
        """Prepare a deployment tx"""

    def get_funding_tx(self) -> Generator[None, None, str]:
        """Prepare a tx to add liquidity to the pool"""

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
        tx_hash: Optional[str] = response_msg.state.body.get("tx_hash", None)

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
