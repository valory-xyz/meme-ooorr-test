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

"""Tenderly time fast forward"""

import os

import requests


admin_rpc = os.getenv("TENDERLY_ADMIN_RPC")

seconds = hex(1 * 60 * 60)

json_data = {
    "jsonrpc": "2.0",
    "method": "evm_increaseTime",
    "params": [str(seconds)],
}

response = requests.post(
    url=admin_rpc,
    timeout=300,
    headers={"Content-Type": "application/json"},
    json=json_data,
)

if response.status_code != 200:
    print(response.status_code)
    try:
        print(response.json())
    except requests.exceptions.JSONDecodeError:
        pass
