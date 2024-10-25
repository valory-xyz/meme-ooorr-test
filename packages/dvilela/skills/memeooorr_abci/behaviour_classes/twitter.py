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
from typing import Dict, Generator, List, Optional, Type

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import DEFAULT_TWEET_PROMPT
from packages.dvilela.skills.memeooorr_abci.rounds import (
    CollectFeedbackPayload,
    CollectFeedbackRound,
    Event,
    PostAnnouncementtRound,
    PostTweetPayload,
    PostTweetRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


MAX_TWEET_CHARS = 280


def is_tweet_valid(tweet: str) -> bool:
    """Checks a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"] <= MAX_TWEET_CHARS


class PostTweetBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
    """PostTweetBehaviour"""

    matching_round: Type[AbstractRound] = PostTweetRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            tweet = yield from self.post_tweet()

            payload = PostTweetPayload(
                sender=self.context.agent_address,
                tweet=json.dumps(tweet, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def post_tweet(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, Optional[str]]:
        """Post a tweet"""

        tweet = self.synchronized_data.pending_tweet

        if not tweet:
            self.context.logger.info("Preparing tweet...")
            persona = self.get_persona()

            llm_response = yield from self._call_genai(
                prompt=DEFAULT_TWEET_PROMPT.format(persona=persona)
            )
            self.context.logger.info(f"LLM response: {llm_response}")

            if llm_response is None:
                self.context.logger.error("Error getting a response from the LLM.")
                return None

            if not is_tweet_valid(llm_response):
                self.context.logger.error("The tweet is too long.")
                return None

            tweet = llm_response

        # Post the tweet
        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[{"text": tweet}],
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting to Twitter.")
            return None

        return {"tweet_id": tweet_ids[0], "text": tweet}


class PostAnnouncementtBehaviour(
    PostTweetBehaviour
):  # pylint: disable=too-many-ancestors
    """PostAnnouncementtBehaviour"""

    matching_round: Type[AbstractRound] = PostAnnouncementtRound


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

    def get_feedback(self) -> Generator[None, None, Optional[List]]:
        """Get the responses"""

        # Search new replies
        latest_tweet = self.synchronized_data.latest_tweet
        query = f"conversation_id:{latest_tweet['tweet_id']}"
        feedback = yield from self._call_twikit(method="search", query=query, count=100)

        # REMOVE, FOR TESTING ONLY
        feedback = [
            {
                "id": "1849853239392600458",
                "user_name": "",
                "text": "This is shit, dogs rule and are way better!",
                "created_at": "1",
                "view_count": 2,
                "retweet_count": 1,
                "quote_count": 1,
                "view_count_state": "",
            }
        ] * 10

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
