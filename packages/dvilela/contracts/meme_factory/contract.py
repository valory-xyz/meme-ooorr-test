# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""This module contains the class to connect to an MemeFactory contract."""

from typing import Dict, List, Optional

from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import EthereumApi


PUBLIC_ID = PublicId.from_str("dvilela/meme_factory:0.1.0")


class MemeFactoryContract(Contract):
    """The MemeFactory contract."""

    contract_id = PUBLIC_ID

    @classmethod
    def build_deposit_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        token_name: str,
        token_ticker: str,
        holders: Optional[List[int]] = None,
        allocations: Optional[List[int]] = None,
        total_supply: int = 1000000000000000000000000,  # 1 million tokens for default 18 decimals
        user_allocation: int = 1,
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""

        if holders is None:
            holders = []

        if allocations is None:
            allocations = []

        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="deploy",
            args=[
                token_name,
                token_ticker,
                holders,
                allocations,
                total_supply,
                user_allocation,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def get_event_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        tx_hash: str,
    ) -> Dict[str, Optional[str]]:
        """Get the data from the TokenDeployed event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        tx_receipt = ledger_api.api.eth.get_transaction_receipt(tx_hash)  # type: ignore

        for log in tx_receipt["logs"]:
            event = contract_instance.events.TokenDeployed().processLog(log)
            return {
                "token_address": event["newToken"],
                "pool_address": event["uniswapV2Factory"],
            }

        return {"token_address": None, "pool_address": None}
