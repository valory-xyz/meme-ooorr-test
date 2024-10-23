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
from typing import Dict, Generator, List, Type

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import DEFAULT_TWEET_PROMPT
from packages.dvilela.skills.memeooorr_abci.rounds import (
    CollectFeedbackPayload,
    CollectFeedbackRound,
    Event,
    PostDeploymentPayload,
    PostDeploymentRound,
    PostInitialTweetRound,
    PostRefinedTweetPayload,
    PostRefinedTweetRound,
    PostTweetPayload,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


MAX_TWEET_CHARS = 280


def is_tweet_valid(tweet: str) -> bool:
    """Checks a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"] <= MAX_TWEET_CHARS


class PostInitialTweetBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """PostInitialTweetBehaviour"""

    matching_round: Type[AbstractRound] = PostInitialTweetRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            token_proposal = yield from self.post_tweet()

            payload = PostTweetPayload(
                sender=self.context.agent_address,
                token_proposal=json.dumps(token_proposal, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def post_tweet(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, Dict]:
        """Post a tweet"""

        token_proposal = self.synchronized_data.token_proposal
        tweet_text = None

        # INITIAL PROPOSAL
        # If a tweet token proposal does not exist, prepare one
        if not token_proposal:
            self.context.logger.info("Preparing initial tweet...")

            llm_response = yield from self._call_genai(prompt=DEFAULT_TWEET_PROMPT)
            self.context.logger.info(f"LLM response: {llm_response}")

            if llm_response is None:
                self.context.logger.error("Error getting a response from the LLM.")
                return None

            token_proposal = {
                "token_name": llm_response["token_name"],
                "token_ticker": llm_response["token_name"],
                "proposal": llm_response["proposal"],
                "announcement": None,
                "deploy": None,
                "token_address": None,
                "pool_address": None,
            }

            tweet_text = token_proposal["proposal"]

        # Post either the announcement or the refined proposal
        else:
            tweet_text = token_proposal["announcement"] or token_proposal["proposal"]

        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[{"text": tweet_text}],
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting to Twitter.")
            return None

        # Reset the proposal if we have finished the cycle
        if token_proposal["announcement"]:
            token_proposal = {}

        return token_proposal


class PostRefinedTweetBehaviour(PostInitialTweetBehaviour):
    """PostRefinedTweetBehaviour"""

    matching_round: Type[AbstractRound] = PostRefinedTweetRound


class PostDeploymentBehaviour(PostInitialTweetBehaviour):
    """PostDeploymentBehaviour"""

    matching_round: Type[AbstractRound] = PostDeploymentRound


class CollectFeedbackBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """CollectFeedbackBehaviour"""

    matching_round: Type[AbstractRound] = CollectFeedbackRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            feedback = yield from self.get_feedback()

            payload = CollectFeedbackPayload(
                sender=self.context.agent_address,
                feedback=json.dumps(feedback, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_feedback(self) -> Generator[None, None, List]:
        """Get the responses"""

        # Search new replies
        token_proposal = self.synchronized_data.token_proposal
        query = f"conversation_id:{token_proposal['tweet']['id']}"
        feedback = yield from self._call_twikit(
            method="search", query=query, max_results=100
        )

        if feedback is None:
            self.context.logger.error(
                "Could not retrieve any replies due to an API error"
            )
            return None

        if not feedback:
            self.context.logger.error("No tweets match the query")
            return []

        self.context.logger.info(f"Retrieved {len(feedback)} replies")

        return feedback
