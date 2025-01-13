#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
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

import json
import os
from pathlib import Path

import dotenv
from web3 import Web3


dotenv.load_dotenv(override=True)

rpc = os.getenv("BASE_LEDGER_RPC")
w3 = Web3(Web3.HTTPProvider(rpc))
meme_factory_address_base = w3.to_checksum_address(
    "0x82a9c823332518c32a0c0edc050ef00934cf04d4"
)
abi_file = Path(
    "packages", "dvilela", "contracts", "meme_factory", "build", "MemeFactory.json"
)

BASE_CHAIN_ID = 8453

with open(abi_file, "r", encoding="utf-8") as file:
    abi = json.load(file)["abi"]

with open("keys.json", "r", encoding="utf-8") as file:
    keys = json.load(file)
    PUBLIC_KEY = keys[0]["address"]
    PRIVATE_KEY = keys[0]["private_key"]

meme_factory_contract = w3.eth.contract(address=meme_factory_address_base, abi=abi)

tx = meme_factory_contract.functions.summonThisMeme(
    "Test Meme",
    "TST",
    1000000000000000000000000,
).build_transaction(
    {
        "value": int(0.01e18),
        "chainId": BASE_CHAIN_ID,
        "gas": 500000,
        "gasPrice": w3.to_wei("3", "gwei"),
        "nonce": w3.eth.get_transaction_count(PUBLIC_KEY),
    }
)

signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
print(tx_receipt)
