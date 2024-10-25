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

"""This package contains round behaviours of MemeooorrAbciApp."""

import json
from typing import Dict, Generator, Optional, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.twitter import (
    is_tweet_valid,
)
from packages.dvilela.skills.memeooorr_abci.prompts import ANALYZE_FEEDBACK_PROMPT
from packages.dvilela.skills.memeooorr_abci.rounds import (
    AnalizeFeedbackPayload,
    AnalizeFeedbackRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


class AnalizeFeedbackBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """AnalizeFeedbackBehaviour"""

    matching_round: Type[AbstractRound] = AnalizeFeedbackRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            analysis = yield from self.get_analysis()

            payload = AnalizeFeedbackPayload(
                sender=self.context.agent_address,
                analysis=json.dumps(analysis, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_analysis(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""

        tweet_responses = "\n\n".join(
            [
                f"tweet: {t['text']}\nviews: {t['view_count']}\nquotes: {t['quote_count']}\nretweets{t['retweet_count']}"
                for t in self.synchronized_data.feedback
            ]
        )

        prompt_data = {
            "latest_tweet": self.synchronized_data.latest_tweet["text"],
            "tweet_responses": tweet_responses,
            "persona": self.get_persona(),
        }

        llm_response = yield from self._call_genai(
            prompt=ANALYZE_FEEDBACK_PROMPT.format(**prompt_data)
        )
        self.context.logger.info(f"LLM response: {llm_response}")

        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return None

        try:
            response = json.loads(llm_response)
        except json.JSONDecodeError as e:
            self.context.logger.error(f"Error loading the LLM response: {e}")
            return None

        if (
            response["deploy"]
            and "tweet" not in response
            and not is_tweet_valid(response["tweet"])
        ):
            self.context.logger.error("Announcement tweet is too long.")
            return None

        if (
            response["deploy"]
            and "token_name" not in response
            or "token_ticker" not in response
        ):
            self.context.logger.error("Missing some token data from the respons.")
            return None

        if not response["deploy"] and "persona" not in response:
            self.context.logger.error("Missing the new persona from the response.")
            return None

        return response
