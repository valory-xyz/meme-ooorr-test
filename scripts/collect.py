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
safe = Safe(  # pylint: disable=abstract-class-instantiated
    SAFE_ADDRESS, ethereum_client_safe
)


def collect_from_safe(meme_address):
    """Collect from safe"""

    # Get the safe nonce
    response = requests.get(
        url=f"{SAFE_SERVICE_URL_BASE}/api/v1/safes/{SAFE_ADDRESS}/", timeout=60
    )
    safe_nonce = response.json()["nonce"]

    # Build the internal transaction
    collect_tx = meme_factory_contract.functions.collectThisMeme(
        meme_address,
    ).build_transaction(
        {
            "chainId": BASE_CHAIN_ID,
            "gas": 1000000,
            "gasPrice": w3.to_wei("3", "gwei"),
            "nonce": safe_nonce,
        }
    )

    # Build the safe transaction
    safe_tx = safe.build_multisig_tx(  # nosec
        to=meme_factory_address_base,
        value=0,
        data=collect_tx["data"],
        operation=0,
        safe_tx_gas=500000,
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
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if tx_receipt.status == 1:
        print("The collect transaction has been successfully validated")
    else:
        print("The collect transaction has failed")


if __name__ == "__main__":
    collect_from_safe("0x56406D9bDeB280Cf2ce3af3c2aB6050c1E196C9a")
