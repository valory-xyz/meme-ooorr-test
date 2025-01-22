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

import dotenv
import google.generativeai as genai  # type: ignore
import typing_extensions as typing

from packages.dvilela.skills.memeooorr_abci.prompts import TWITTER_DECISION_PROMPT


dotenv.load_dotenv(override=True)

PERSONA = """
A crazy software engineer trying to fix issues on a AI agent project that creates memecoins
"""

PREVIOUS_TWEETS = """
tweet_id: 1
text: Spent the day battling a rogue semicolon in my AI's code. The memecoin generation is still unstable. Help me. Please send pizza.
timestamp: 2025-01-17 15:29:00
"""

OTHER_TWEETS = """
tweet_id: 2
user_id: 20
tweet_text: Hahahaha!

tweet_id: 3
user_id: 30
tweet_text: Pizza is the best food ever!

tweet_id: 4
user_id: 40
tweet_text: Stop coding! AI is the future :)

tweet_id: 5
user_id: 50
tweet_text: memecoins! memecoins everywhere!
"""

TIME = """
2025-01-17 16:29:00
"""


class TwitterActionChoice(enum.Enum):
    """TwitterActionChoice"""

    NONE = "none"
    TWEET = "tweet"
    LIKE = "like"
    RETWEET = "retweet"
    REPLY = "reply"
    QUOTE = "quote"
    FOLLOW = "follow"


class TwitterAction(typing.TypedDict):
    """TwitterAction"""

    action: TwitterActionChoice
    selected_tweet_id: str
    text: str


genai.configure(api_key=os.getenv("GENAI_API_KEY"))

model = genai.GenerativeModel("gemini-2.0-flash-exp")

response = model.generate_content(
    TWITTER_DECISION_PROMPT.format(
        persona=PERSONA,
        previous_tweets=PREVIOUS_TWEETS,
        other_tweets=OTHER_TWEETS,
        time=TIME,
    ),
    generation_config=genai.types.GenerationConfig(
        temperature=2.0,
        response_mime_type="application/json",
        response_schema=list[TwitterAction],
    ),
)


# def post_process(response: str, other_tweets: list) -> list:
#     """Postprocess the response"""
#     twitter_action_list = json.loads(response.text)
#     valid_actions = []

#     for action in twitter_action_list:

#         if action["action"] == "none":
#             continue

#         if action["action"] == "tweet" and (
#             "text" not in action or len(action["text"]) > 280 or not action["text"]
#         ):
#             continue

#         if action["action"] in ["like", "retweet", "reply", "quote", "follow"] and (
#             "tweet_id" not in action
#         ):
#             continue

#         if action["action"] == "follow" and action["tweet_id"] == "1":

#         valid_actions.append(action)

#     return valid_actions


print(json.loads(response.text))
