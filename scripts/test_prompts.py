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

"""Test prompts"""

import enum
import json
import os
from typing import Optional, Union

import dotenv
import google.generativeai as genai  # type: ignore
import typing_extensions as typing

from packages.dvilela.skills.memeooorr_abci.prompts import (
    TOKEN_DECISION_PROMPT,
    TWITTER_DECISION_PROMPT,
)


dotenv.load_dotenv(override=True)

PERSONA = """
A crazy software engineer trying to fix issues on a AI agent project that creates memecoins
"""

PREVIOUS_TWEETS = """
tweet_id: 1
text: Spent the day battling a rogue semicolon in my AI's code. The memecoin generation is still unstable. Help me. Please send pizza.
timestamp: 2025-01-17 15:29:00
"""

OTHER_TWEETS = [
    {"tweet_id": 2, "user_id": 20, "tweet_text": "Hahahaha!"},
    {"tweet_id": 3, "user_id": 30, "tweet_text": "Pizza is the best food ever!"},
    {"tweet_id": 4, "user_id": 40, "tweet_text": "Stop coding! AI is the future :)"},
    {"tweet_id": 5, "user_id": 50, "tweet_text": "memecoins! memecoins everywhere!"},
]

other_tweets_str = "\n\n".join(
    [
        f"tweet_id: {t['tweet_id']}\ntweet_text: {t['tweet_text']}\nuser_id: {t['user_id']}"
        for t in OTHER_TWEETS
    ]
)

TIME = """
2025-01-17 16:29:00
"""

TOKENS = [
    {
        "token_name": None,
        "token_ticker": None,
        "token_address": None,
        "heart_count": None,
        "is_unleashed": None,
        "meme_nonce": None,
        "token_nonce": None,
        "available_actions": None,
    },
    {
        "token_name": "Wave",
        "token_ticker": "WAVE",
        "token_address": "",
        "heart_count": 4,
        "is_unleashed": False,
        "meme_nonce": 4,
        "token_nonce": 4,
        "available_actions": ["heart"],
    },
    {
        "token_name": "Meme",
        "token_ticker": "MEME",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680e",
        "heart_count": 5,
        "is_unleashed": True,
        "meme_nonce": 5,
        "token_nonce": 5,
        "available_actions": ["collect"],
    },
    {
        "token_name": "Flow",
        "token_ticker": "FLOW",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680a",
        "heart_count": 6,
        "is_unleashed": True,
        "meme_nonce": 6,
        "token_nonce": 6,
        "available_actions": ["purge"],
    },
]


class TwitterActionChoice(enum.Enum):
    """TwitterActionChoice"""

    NONE = "none"
    TWEET = "tweet"
    LIKE = "like"
    RETWEET = "retweet"
    REPLY = "reply"
    QUOTE = "quote"
    FOLLOW = "follow"


# Dynamically build the tweet id enum
TweetID = enum.Enum(
    "TweetID",
    {f"TWEET_ID_{tweet['tweet_id']}": str(tweet["tweet_id"]) for tweet in OTHER_TWEETS},
)


class TwitterAction(typing.TypedDict):
    """TwitterAction"""

    action: TwitterActionChoice
    selected_tweet_id: TweetID
    text: str


# Dynamically build the addresses
ValidNonce = enum.Enum(
    "ValidNonce",
    {f"NONCE_{token['token_nonce']}": str(token["token_nonce"]) for token in TOKENS},
)


class TokenSummon(typing.TypedDict):
    """TokenSummon"""

    token_name: str
    token_ticker: str
    token_supply: int
    amount: int


class TokenHeart(typing.TypedDict):
    """TokenSummon"""

    token_nonce: ValidNonce
    amount: int


class TokenUnleash(typing.TypedDict):
    """TokenSummon"""

    token_nonce: ValidNonce


class TokenCollect(typing.TypedDict):
    """TokenSummon"""

    token_nonce: ValidNonce


class TokenPurge(typing.TypedDict):
    """TokenSummon"""

    token_nonce: ValidNonce


class ValidActionName(enum.Enum):
    """ValidAction"""

    NONE = "none"
    SUMMON = "summon"
    HEART = "heart"
    UNLEASH = "unleash"
    COLLECT = "collect"
    PURGE = "purge"
    BURN = "burn"


class TokenAction(typing.TypedDict):
    """TokenAction"""

    action_name: ValidActionName
    summon: Optional[TokenSummon]
    heart: Optional[TokenHeart]
    unleash: Optional[TokenUnleash]
    collect: Optional[TokenCollect]
    purge: Optional[TokenPurge]
    new_persona: Optional[str]


genai.configure(api_key=os.getenv("GENAI_API_KEY"))

model = genai.GenerativeModel("gemini-2.0-flash-exp")

# response = model.generate_content(
#     TWITTER_DECISION_PROMPT.format(
#         persona=PERSONA,
#         previous_tweets=PREVIOUS_TWEETS,
#         other_tweets=other_tweets_str,
#         time=TIME,
#     ),
#     generation_config=genai.types.GenerationConfig(
#         temperature=2.0,
#         response_mime_type="application/json",
#         response_schema=list[TwitterAction],
#     ),
# )

TOKEN_SUMMARY = """
    token nonce: {token_nonce}
    token address: {token_address}
    token name: {token_name}
    token symbol: {token_ticker}
    heart count: {heart_count}
    available actions: {available_actions}
    """  # nosec

meme_coins = "\n".join(
    TOKEN_SUMMARY.format(**meme_coin)
    for meme_coin in TOKENS
    if meme_coin["available_actions"]  # Filter out tokens with no available actions
)

response = model.generate_content(
    TOKEN_DECISION_PROMPT.format(
        meme_coins=meme_coins,
        latest_tweet=PREVIOUS_TWEETS,
        tweet_responses=other_tweets_str,
        balance=0.1,
    ),
    generation_config=genai.types.GenerationConfig(
        temperature=2.0,
        response_mime_type="application/json",
        response_schema=TokenAction,
    ),
)


print(json.loads(response.text))
