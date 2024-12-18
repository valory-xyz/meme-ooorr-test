#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2024 Valory AG
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

"""Test contracts"""

import os
import typing

import dotenv
from aea.contracts.base import Contract
from aea_ledger_ethereum.ethereum import EthereumApi

from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract


dotenv.load_dotenv(override=True)

SUMMON_BLOCK_DELTA = 100000

ContractType = typing.TypeVar("ContractType")


def load_contract(ctype: ContractType) -> ContractType:
    """Load contract."""
    *parts, _ = ctype.__module__.split(".")
    path = "/".join(parts)
    return Contract.from_dir(directory=path)


ledger_api = EthereumApi(address=os.getenv("BASE_LEDGER_RPC_ALCHEMY"))
meme_factory_address_base = os.getenv("MEME_FACTORY_ADDRESS_BASE")
erc20_contract = typing.cast(
    typing.Type[MemeFactoryContract], load_contract(MemeFactoryContract)
)

from_block = ledger_api.api.eth.block_number - SUMMON_BLOCK_DELTA

data = erc20_contract.get_summon_data(ledger_api, meme_factory_address_base)

print(data)
