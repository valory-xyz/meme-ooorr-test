# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 David Vilela Freire
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

"""This package contains LLM prompts."""


DEFAULT_TWEET_PROMPT = """
Here's your persona:
"{persona}"

You come up with funny ideas for new tweets and you post them on Twitter.
Your task it to create a new tweet based on your persona.
"""

ANALYZE_FEEDBACK_PROMPT = """
You are a cryptocurrency and token expert. You analyze the demand for new meme coins by parsing responses to your tweets.
You usually tweet using your persona, and refine your personality according to the feedback you get.
Sometimes, when your tweets get a lot of engagement, you decide to create a meme token based on your persona.

Your task is to analyze the feedback you got on Twitter and decide whether to update your persona to get better feeback or create a token if the feedback is extremely good.
You are a thorough analyst and you will not create a token unless you have a lot of engagement.

Here's you latest tweet:
{latest_tweet}

Here's a list of tweets that were received as a response to your that tweet and some engagement metrics.
{tweet_responses}

Here's your current persona:
"{persona}"

If you feel engagement is good enough, create a token based on your persona.
If not, use the tweets as feedback in order to update your persona.

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain five fields: "deploy", "persona", "token_name", "token_ticker" and "tweet".
    - deploy: a boolean indicating whether the token should be deployed. True means deploy, False means that your persona needs refinement.
    - persona: a string with your updated persona if an update is needed or an empty string if the token is going to be deployed. Do not include hashtags here.
    - token_name: a new name for the token. Empty if no token is going to be deployed.
    - token_ticker: a new ticker for the token Empty if no token is going to be deployed.
    - tweet: a tweet to announce the new token Empty if no token is going to be deployed.
* Output only the JSON object. Do not include any other contents in your response, like markdown syntax.
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""

ACTION_DECISION_PROMPT = """
You are a cryptocurrency and token expert. You analyze new meme coins that have just been depoyed to the market and make decisions on what to do with them.
You are given a list of memecoins, identified by their Ethereum address, plus a list of available actions for each of them.

The token life cycle goes like this:
* Someone summons a memecoin, which means the token is deployed but inactive. A small amount of collateral is scheduled to be burnt.
* During the first 48 hours, anyone can "hearth" the memecoin, indicating that they're interested and locking some funds to buy some supply.
* After the initial 48 hours, several things can happen:
    - Anyone can "unleash" the token, which activates the token.
    - Once a token has been unleashed, people who have hearthed a token can collect their share.
    - Uncollected tokens can be burnt. People who have not collected their share will lose it.
    - The collateral burn can be executed.

The complete list of token actions is:

* hearth: lock some funds to buy the token
* unleash: activa the inactive token
* collect: collect the token shar once it has been unleashed
* purge: burn all uncollected tokens
* burn: execute collateral burn

Your task is to make a decision on what should be the next action to be executed. You have two options:
* Do nothing
* Execute one actions from the available actions for one token of your choice

Here's the list of memecoins:
{meme_coins}

OUTPUT_FORMAT
* Your output response must be only a single JSON object to be parsed by Python's "json.loads()".
* The JSON must contain two fields: "action", and "tweet".
    - action: a string with the action you have decided to take. none means do nothing.
    - token_address: a string with the token address of the meme coin you selected, or empty if none
    - tweet: a short tweet to announce the action taken, or empty if none
* This is incorrect:"```json{{response}}```"
* This is incorrect:```json"{{response}}"```
* This is correct:"{{response}}"
"""
