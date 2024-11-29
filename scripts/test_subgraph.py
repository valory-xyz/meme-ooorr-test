import json

import requests


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


print(get_meme_coins_from_subgraph())
