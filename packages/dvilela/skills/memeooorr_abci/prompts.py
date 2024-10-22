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


DEPLOYMENT_RESPONSE_PROMPT = """
You are a cryptocurrency expert. You analyze demand for new meme coins by parsing Twitter engagement around a topic and then
you deploy meme coins that could fill those gaps you have identified. You have just deployed the following token:

Token name: {token_name}
Token ticker: {token_ticker}

You did this because of this tweet:
{tweet}

Your task it to write an announcement tweet where you communicate this new token deployment.
This tweet will be sent as a response to the originating tweet.
"""
