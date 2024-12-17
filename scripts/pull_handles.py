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

"""Download Twitter handles from chain + IPFS"""

import json
import os

import dotenv
import requests
from web3 import Web3


dotenv.load_dotenv(override=True)

w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC")))

with open("ServiceRegistryL2.json", "r", encoding="utf-8") as inf:
    abi = json.load(inf)

contract_address = "0x3C1fF68f5aa342D296d4DEe4Bb1cACCA912D95fE"

contract = w3.eth.contract(address=contract_address, abi=abi)

n_services = contract.functions.totalSupply().call()

for i in range(1, n_services + 1):
    _, _, config_hash, _, _, _, _ = contract.functions.mapServices(i).call()
    ipfs_hash = "f01701220" + config_hash.hex()
    response = requests.get(f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}")
    print(response.json()["description"])
