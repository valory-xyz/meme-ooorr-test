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

from typing import Dict, Optional

import web3
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import EthereumApi


PUBLIC_ID = PublicId.from_str("dvilela/meme_factory:0.1.0")


class MemeFactoryContract(Contract):
    """The MemeFactory contract."""

    contract_id = PUBLIC_ID

    @classmethod
    def build_summon_tx(  # pylint: disable=too-many-arguments
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        token_name: str,
        token_ticker: str,
        total_supply: int = 1000000000000000000000000,  # 1 million tokens for default 18 decimals
    ) -> Dict[str, bytes]:
        """Build a deposit transaction."""

        contract_instance = cls.get_instance(ledger_api, contract_address)
        data = contract_instance.encodeABI(
            fn_name="summonThisMeme",
            args=[
                token_name,
                token_ticker,
                total_supply,
            ],
        )
        return {"data": bytes.fromhex(data[2:])}

    @classmethod
    def get_token_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
        tx_hash: str,
    ) -> Dict[str, Optional[str]]:
        """Get the data from the Summoned event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        tx_receipt = ledger_api.api.eth.get_transaction_receipt(tx_hash)  # type: ignore

        for log in tx_receipt["logs"]:
            try:
                event = contract_instance.events.Summoned().process_log(log)
                return {
                    "token_address": event.args["memeToken"],
                    "summoner": event.args["summoner"],
                    "eth_contributed": event.args["ethContributed"],
                }
            except web3.exceptions.MismatchedABI:
                continue

        return {"token_address": None, "summoner": None, "eth_contributed": None}
