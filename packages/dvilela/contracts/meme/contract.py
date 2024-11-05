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

import logging

from aea.common import JSONLike
from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import EthereumApi


PUBLIC_ID = PublicId.from_str("dvilela/meme:0.1.0")


class MemeContract(Contract):
    """The Meme ERC20 contract."""

    contract_id = PUBLIC_ID

    @classmethod
    def get_token_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
    ) -> JSONLike:
        """Get the data from the Summoned event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)
        name = contract_instance.functions.name().call()
        symbol = contract_instance.functions.symbol().call()
        total_supply = contract_instance.functions.totalSupply().call()
        decimals = contract_instance.functions.decimals().call()
        return {
            "name": name,
            "symbol": symbol,
            "total_supply": total_supply,
            "decimals": decimals,
        }
