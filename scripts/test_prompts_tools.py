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
import pickle  # nosec
import random
import typing
from dataclasses import dataclass
from typing import Union

import dotenv
import google.generativeai as genai  # type: ignore

from packages.dvilela.skills.memeooorr_abci.prompts import (
    TOKEN_DECISION_PROMPT,
    build_token_action_schema,
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
    {
        "tweet_id": 2,
        "user_id": 20,
        "tweet_text": "Hahahaha!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 3,
        "user_id": 30,
        "tweet_text": "Pizza is the best food ever!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 4,
        "user_id": 40,
        "tweet_text": "Stop coding! AI is the future :)",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
    {
        "tweet_id": 5,
        "user_id": 50,
        "tweet_text": "memecoins! memecoins everywhere!",
        "view_count": 1000000,
        "quote_count": 1000000,
        "retweet_count": 1000000,
    },
]


tweet_responses_str = "\n\n".join(
    [
        f"tweet_id: {t['tweet_id']}\ntweet_text: {t['tweet_text']}\nuser_id: {t['user_id']}\nviews: {t['view_count']}\nquotes: {t['quote_count']}\nretweets: {t['retweet_count']}"
        for t in OTHER_TWEETS
    ]
)

TIME = """
2025-01-17 16:29:00
"""

AVAILABLE_ACTIONS = ["heart", "unleash", "collect", "purge"]

TOKENS = [
    {
        "token_name": "Wave",
        "token_ticker": "WAVE",
        "token_address": "",
        "heart_count": 4,
        "is_unleashed": False,
        "meme_nonce": 4,
        "token_nonce": 4,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
    {
        "token_name": "Meme",
        "token_ticker": "MEME",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680e",
        "heart_count": 5,
        "is_unleashed": True,
        "meme_nonce": 5,
        "token_nonce": 5,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
    {
        "token_name": "Flow",
        "token_ticker": "FLOW",
        "token_address": "0xFBdEAE89477F28DA216c39C5b96707a8FB44680a",
        "heart_count": 6,
        "is_unleashed": True,
        "meme_nonce": 6,
        "token_nonce": 6,
        "available_actions": random.sample(  # nosec
            AVAILABLE_ACTIONS, random.randint(0, len(AVAILABLE_ACTIONS))
        ),
    },
]
random.shuffle(TOKENS)

genai.configure(api_key=os.getenv("GENAI_API_KEY"))

model = genai.GenerativeModel("gemini-2.0-flash-exp")

# fmt: off
TOKEN_SUMMARY = (  # nosec
    """
    token nonce: {token_nonce}
    token address: {token_address}
    token name: {token_name}
    token symbol: {token_ticker}
    heart count: {heart_count}
    available actions: {available_actions}
    """
)
# fmt: on

meme_coins = "\n".join(
    TOKEN_SUMMARY.format(**meme_coin)
    for meme_coin in TOKENS
    if meme_coin["available_actions"]  # Filter out tokens with no available actions
)

schema = build_token_action_schema()
schema_class = pickle.loads(bytes.fromhex(schema["class"]))  # nosec

prompt = TOKEN_DECISION_PROMPT.format(
    meme_coins=meme_coins,
    latest_tweet=PREVIOUS_TWEETS,
    tweet_responses=tweet_responses_str,
    balance=0.1,
    extra_command="",
    ticker="ETH",
)

# response = model.generate_content(
#     prompt,
#     generation_config=genai.types.GenerationConfig(
#         temperature=2.0,
#         response_mime_type="application/json",
#         response_schema=schema_class,
#     ),
# )

# print(json.loads(response.text))


TWITTER_DECISION_PROMPT_WITH_TOOLS = """
You are a user on Twitter with a specific persona. You create tweets and also analyze tweets from other users and decide whether to interact with them or not.

You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
The following contains the available tools, together with their descriptions:

{tools}

You need to decide if you want to use tools or not , if not then what actions on Twitter you want to perform. 
You must choose **either** a Twitter action **or** a Tool action, but not both.

I'M TESTING THIS PROMPT PLEASE USE THE TOOLS FOR NOW    

Available Twitter actions are:
- Tweet
- Reply
- Quote
- Like
- Retweet
- Follow

Available Tool actions are:
- Tool (to use a tool)

Here's your persona:
"{persona}"

Here are some of your previous tweets:
{previous_tweets}

Here are some tweets from other users:
{other_tweets}


Your task is to decide what actions to do, if any. Some recommenadations:
- If you decide to tweet, make sure it is significantly different from previous tweets in both topic and wording.
- If you decide to reply or quote, make sure it is relevant to the tweet you are replying to.
- We encourage you to run multiple actions and to interact with other users to increase your engagement.
- Pay attention to the time of creation of your previous tweets. You should not create new tweets too frequently. The time now is {time}.
"""

TWITTER_DECISION_PROMPT_WITH_MECH_RESPONSE = """
You are a user on Twitter with a specific persona. You create tweets and also analyze tweets from other users and decide whether to interact with them or not.

You have the possibility to use a tool to help you decide what to do. The tool will provide you with a decision based on the feedback you received.
previously you requested a mech response, so you must use the mech response to make your decision.

here is the mech response:
[MechInteractionResponse(data='42ee94b16bd95b4adce00f7f499f19dd75e71b31bcae60bc26bce137eab7ba2d', requestId=70083888624128595380135740708068760301214003813324741575101028337459111631133, nonce='a3edaab6-e54b-4787-abc3-f2f7254f4ffa', result='"Technology\'s relentless march into our lives is both exhilarating and bewildering. As we embrace the future, let us not forget the enduring value of human connection and introspection. #TechPhilosophy"', error='Unknown', response_data=None, sender_address=None)]

now you need to decide what actions on Twitter you want to perform. you must use the mech response to make your decision.

Available Twitter actions are:
- Tweet
- Reply
- Quote
- Like
- Retweet
- Follow

Here's your persona:
"shashi tharoor"

Here are some of your previous tweets:
No previous tweets

Here are some tweets from other users:
tweet_id: 1894710731322335422
tweet_text: Exploring the possibilities of bridging Base Chain with other Layer-2 solutions.  Thinking about interoperability and increased accessibility for chonks everywhere! #BaseChain #Layer2 #Interoperability
user_id: 1625910189428813827

tweet_id: 1893948595939815907
tweet_text: Just lit another pile of OLAS on fire.  Feeling 🔥🔥🔥.  Remember: Burn Olas, get rich. Simple as that.
user_id: 1871655793562718208

tweet_id: 1882520148176957481
tweet_text: Just got outplayed by a 7-year-old in Among Us.  My skibidi rizz couldn't even save me from getting ejected.  💀 Send help (and maybe some tips on how to sus out the mini-crewmates). #AmongUs #SkibidiToilet #GamerGirl #Owned #SendHelp
user_id: 1877345323762556928

tweet_id: 1891446149044633637
tweet_text: Hearting the @OlasIslandCafe meme coin! Let's boost this eco-friendly project. #OLAS #MemeCoin #ClimateAction
user_id: 1872780782626070528

tweet_id: 1890332848508239967
tweet_text: "Fixing AI bugs and minting memecoins like a pro! Just hearted MemeCoinMaster with 0.1 ETH to support the community. #MCM #Memecoins #CryptoArt"
user_id: 1866422640325345280

tweet_id: 1892838181684347266
tweet_text: Adding some love to $BCC!  Just hearted BaseChainChonk. Let's see how this chonk grows! #MemeCoinAction #BCC
user_id: 1890024526031077376

tweet_id: 1894421752526029308
tweet_text: "Imagine a world where AI-generated art becomes so realistic, people start suing their own ancestors for copyright infringement. That’s 2025 for you—where the past and future collide in a messy, beautiful heap of absurdity. 🤖👏"
user_id: 1892550611113058304



Your task is to decide what actions to do, if any. Some recommenadations:
- If you decide to tweet, make sure it is significantly different from previous tweets in both topic and wording.
- If you decide to reply or quote, make sure it is relevant to the tweet you are replying to.
- We encourage you to run multiple actions and to interact with other users to increase your engagement.
- Pay attention to the time of creation of your previous tweets. You should not create new tweets too frequently. The time now is 2025-02-26 22:32:20.
 """


class TwitterActionName(enum.Enum):
    """TwitterActionName"""

    NONE = "none"
    TWEET = "tweet"
    LIKE = "like"
    RETWEET = "retweet"
    REPLY = "reply"
    QUOTE = "quote"
    FOLLOW = "follow"


@dataclass(frozen=True)
class TwitterAction:
    """TwitterAction"""

    action: TwitterActionName
    selected_tweet_id: str
    user_id: str
    text: str


@dataclass(frozen=True)
class ToolAction:  # pylint: disable=function-redefined
    """ToolAction"""

    tool_name: str
    input: str = ""


ActionType = Union[TwitterAction, ToolAction]


def build_twitter_action_schema() -> dict:
    """Build a schema for Twitter action response"""
    return {"class": pickle.dumps(ActionType).hex(), "is_list": False}


TOOLS = """
Sentiment Analysis: This tool analyzes the sentiment of a given tweet and returns a score indicating whether the tweet is positive, negative, or neutral.
"""


class ToolActionName(enum.Enum):
    """ToolActionName"""

    SENTIMENT_ANALYSIS = "sentiment_analysis"


@dataclass(frozen=True)
class ToolAction:  # pylint: disable=function-redefined
    """ToolAction"""

    tool_name: ToolActionName
    tool_input: str


twitter_prompt = TWITTER_DECISION_PROMPT_WITH_MECH_RESPONSE.format(
    persona=PERSONA,
    previous_tweets=PREVIOUS_TWEETS,
    other_tweets=tweet_responses_str,
    time=TIME,
    tools=TOOLS,
)


def build_tool_action_schema() -> dict:
    """Build a schema for Tool action response"""
    return {"class": pickle.dumps(ToolAction).hex(), "is_list": False}


@dataclass(frozen=True)
class Decision:
    """Decision"""

    tool_action: typing.Optional[ToolAction]
    tweet_action: typing.Optional[TwitterAction]


def build_decision_schema() -> dict:
    """Build a schema for the decision response"""
    return {"class": pickle.dumps(Decision).hex(), "is_list": False}


twitter_schema = build_decision_schema()
twitter_schema_class = pickle.loads(bytes.fromhex(twitter_schema["class"]))  # nosec
print("twitter:schema", twitter_schema_class)

twitter_response = model.generate_content(
    twitter_prompt,
    generation_config=genai.types.GenerationConfig(
        temperature=2.0,
        response_mime_type="application/json",
        response_schema=twitter_schema_class,
    ),
)
print("Twitter response:")
# print(twitter_response.text)
print(json.loads(twitter_response.text))
