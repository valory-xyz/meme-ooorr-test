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

"""Test subgraph"""


import re

import requests


MEMEOOORR_DESCRIPTION_PATTERN = r"^Memeooorr @(\w+)$"

TOKENS_QUERY = """
query Tokens {
  memeTokens {
    items {
      blockNumber
      chain
      heartCount
      id
      isUnleashed
      liquidity
      lpPairAddress
      owner
      timestamp
    }
  }
}
"""

PACKAGE_QUERY = """
query getPackages($package_type: String!) {
    units(where: {packageType: $package_type}) {
        id,
        packageType,
        publicId,
        packageHash,
        tokenId,
        metadataHash,
        description,
        owner,
        image
    }
}
"""

HTTP_OK = 200


def get_meme_coins_from_subgraph():
    """Get a list of meme coins"""

    url = "https://agentsfun-indexer-production-6ab5.up.railway.app"

    query = {"query": TOKENS_QUERY}

    headers = {"Content-Type": "application/json"}

    # Make the HTTP request
    response = requests.post(url=url, json=query, headers=headers)

    # Handle HTTP errors
    if response.status_code != HTTP_OK:
        print(f"Error while pulling the memes from subgraph: {response.body!r}")
        return []

    # Load the response
    response_json = response.json()
    meme_coins = [
        {
            "token_address": t["id"],
            "liquidity": int(t["liquidity"]),
            "heart_count": int(t["heartCount"]),
            "is_unleashed": t["isUnleashed"],
            "timestamp": t["timestamp"],
        }
        for t in response_json["data"]["memeTokens"]["items"]
        if t["chain"] == "base"  # TODO: adapt to Celo
    ]
    return meme_coins


def get_packages(package_type: str):
    """Gets minted packages from the Olas subgraph"""

    url = "https://subgraph.staging.autonolas.tech/subgraphs/name/autonolas-base/"

    headers = {"Content-Type": "application/json"}

    query = {
        "query": PACKAGE_QUERY,
        "variables": {
            "package_type": package_type,
        },
    }

    response = requests.post(url=url, json=query, headers=headers)

    # Handle HTTP errors
    if response.status_code != HTTP_OK:
        print(f"Error while pulling the memes from subgraph: {response}")
        return []

    response_json = response.json()["data"]  # type: ignore
    return response_json


def get_memeooorr_handles_from_subgraph():
    """Get Memeooorr service handles"""
    handles = []
    services = get_packages("service")
    if not services:
        return handles

    for service in services["units"]:
        match = re.match(MEMEOOORR_DESCRIPTION_PATTERN, service["description"])

        if not match:
            continue

        handle = match.group(1)
        handles.append(handle)
    return handles


print(get_memeooorr_handles_from_subgraph())
