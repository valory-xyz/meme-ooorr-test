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

"""Test prompts"""

import os

import dotenv
import google.generativeai as genai  # type: ignore

from packages.dvilela.skills.memeooorr_abci.prompts import INTERACT_DECISION_PROMPT


dotenv.load_dotenv(override=True)

persona = "A cat lover"
tweet_data = """

tweet_id: 111112
tweet_text: "It's never late to be a bot!"

tweet_id: 111111
tweet_text: "I love cats! 🐱"

tweet_id: 111113
tweet_text: "I love rats!"
"""

genai.configure(api_key=os.getenv("GENAI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content(
    INTERACT_DECISION_PROMPT.format(persona=persona, tweet_data=tweet_data)
)
print(response.text)
