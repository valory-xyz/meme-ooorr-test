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
import requests
from safe_eth.eth import EthereumClient
from safe_eth.safe import Safe
from web3 import Web3


dotenv.load_dotenv(override=True)

# Constants
TOKEN_NAME = "Wave"
TOKEN_SYMBOL = "WAVE"
TOKEN_SUPPLY = 1000000000000000000000000
MIN_SUMMON_VALUE = int(0.01e18)  # 0.01 ETH

RPC = os.getenv("BASE_LEDGER_RPC")
SAFE_ADDRESS = os.getenv("SAFE_CONTRACT_ADDRESS")
BASE_CHAIN_ID = 8453
SAFE_SERVICE_URL_BASE = "https://safe-transaction-base.safe.global"

# Load the signer keys
with open("keys.json", "r", encoding="utf-8") as file:
    keys = json.load(file)
    PUBLIC_KEY = keys[0]["address"]
    PRIVATE_KEY = keys[0]["private_key"]

# Instantiate the factory contract
w3 = Web3(Web3.HTTPProvider(RPC))

meme_factory_address_base = w3.to_checksum_address(
    "0x82a9c823332518c32a0c0edc050ef00934cf04d4"
)
meme_factory_abi_file = Path(
    "packages", "dvilela", "contracts", "meme_factory", "build", "MemeFactory.json"
)

with open(meme_factory_abi_file, "r", encoding="utf-8") as file:
    meme_factory_abi = json.load(file)["abi"]

meme_factory_contract = w3.eth.contract(
    address=meme_factory_address_base, abi=meme_factory_abi
)

# Instantiate the Safe contract
ethereum_client_safe = EthereumClient(RPC)
safe = Safe(SAFE_ADDRESS, ethereum_client_safe)


def summon_from_agent():
    """Summon from agent"""

    # Build
    summon_tx = meme_factory_contract.functions.summonThisMeme(
        TOKEN_NAME,
        TOKEN_SYMBOL,
        TOKEN_SUPPLY,
    ).build_transaction(
        {
            "value": MIN_SUMMON_VALUE,
            "chainId": BASE_CHAIN_ID,
            "gas": 500000,
            "gasPrice": w3.to_wei("3", "gwei"),
            "nonce": w3.eth.get_transaction_count(PUBLIC_KEY),
        }
    )

    # Sign
    signed_tx = w3.eth.account.sign_transaction(summon_tx, private_key=PRIVATE_KEY)

    # Send
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

    # Wait
    w3.eth.wait_for_transaction_receipt(tx_hash)


def summon_from_safe():
    """Summon from safe"""

    # Get the safe nonce
    response = requests.get(
        url=f"{SAFE_SERVICE_URL_BASE}/api/v1/safes/{SAFE_ADDRESS}/", timeout=60
    )
    safe_nonce = response.json()["nonce"]

    # Build the internal transaction
    summon_tx = meme_factory_contract.functions.summonThisMeme(
        TOKEN_NAME,
        TOKEN_SYMBOL,
        TOKEN_SUPPLY,
    ).build_transaction(
        {
            "chainId": BASE_CHAIN_ID,
            "gas": 500000,
            "gasPrice": w3.to_wei("3", "gwei"),
            "nonce": safe_nonce,
        }
    )

    # Build the safe transaction
    safe_tx = safe.build_multisig_tx(
        to=meme_factory_address_base,
        value=MIN_SUMMON_VALUE,
        data=summon_tx["data"],
        operation=0,
        safe_tx_gas=100000,
        base_gas=0,
        gas_price=int(1e9),
        gas_token="0x0000000000000000000000000000000000000000",
        refund_receiver="0x0000000000000000000000000000000000000000",
    )

    # Sign
    safe_tx.sign(PRIVATE_KEY)

    # Send
    tx_hash, _ = safe_tx.execute(PRIVATE_KEY)

    # Wait
    w3.eth.wait_for_transaction_receipt(tx_hash)


# summon_from_agent()
summon_from_safe()
