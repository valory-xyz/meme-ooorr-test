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
from datetime import datetime
from typing import Dict, Generator, List, Optional, Type

from twitter_text import parse_tweet  # type: ignore

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.prompts import DEFAULT_TWEET_PROMPT
from packages.dvilela.skills.memeooorr_abci.rounds import (
    CollectFeedbackPayload,
    CollectFeedbackRound,
    PostAnnouncementRound,
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
            latest_tweet = yield from self.decide_post_tweet()

            payload = PostTweetPayload(
                sender=self.context.agent_address,
                latest_tweet=json.dumps(latest_tweet, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def decide_post_tweet(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""

        pending_tweet = self.synchronized_data.pending_tweet

        # If there is a pending tweet, we send it
        if pending_tweet:
            self.context.logger.info("Sending a pending tweet...")
            latest_tweet = yield from self.post_tweet(tweet=pending_tweet)
            return latest_tweet

        # If we have not posted before, we prepare and send a new tweet
        if self.synchronized_data.latest_tweet == {}:
            self.context.logger.info("Creating a new tweet for the first time...")
            latest_tweet = yield from self.post_tweet(tweet=None)
            return latest_tweet

        # Calculate time since the latest tweet
        latest_tweet_time = datetime.fromtimestamp(
            self.synchronized_data.latest_tweet["timestamp"]
        )
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        hours_since_last_tweet = (now - latest_tweet_time).total_seconds() / 3600

        # If we have posted befored, but not enough time has passed to collect feedback, we wait
        if hours_since_last_tweet < self.params.feedback_period_hours:
            self.context.logger.info(
                f"{hours_since_last_tweet:.1f} hours have passed since last tweet. Awaiting for the feedback period..."
            )
            return {"wait": True}

        # Enough time has passed, collect feedback
        if not self.synchronized_data.feedback:
            self.context.logger.info(
                "Feedback period has finished. Collecting feedback..."
            )
            return {}

        # Not enough feedback, prepare and send a new tweet
        self.context.logger.info("Feedback was not enough. Creating a new tweet...")
        latest_tweet = yield from self.post_tweet(tweet=None)
        return latest_tweet

    def prepare_tweet(self) -> Generator[None, None, Optional[str]]:
        """Prepare a tweet"""

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
        return tweet

    def post_tweet(
        self, tweet: Optional[List] = None
    ) -> Generator[None, None, Optional[Dict]]:
        """Post a tweet"""
        # Prepare a tweet if needed
        if tweet is None:
            new_tweet = yield from self.prepare_tweet()
            tweet = [new_tweet]

            # We fail to prepare the tweet
            if not tweet:
                return None

        # Post the tweet
        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[{"text": t} for t in tweet],
        )

        if not tweet_ids:
            self.context.logger.error("Failed posting to Twitter.")
            return None

        # Write latest tweet to the database
        latest_tweet = {
            "tweet_id": tweet_ids[0],
            "text": tweet,
            "timestamp": self.get_sync_timestamp(),
        }
        yield from self._write_kv(
            {"latest_tweet": json.dumps(latest_tweet, sort_keys=True)}
        )
        self.context.logger.info("Wrote latest tweet to db")

        return latest_tweet


class PostAnnouncementBehaviour(
    PostTweetBehaviour
):  # pylint: disable=too-many-ancestors
    """PostAnnouncementBehaviour"""

    matching_round: Type[AbstractRound] = PostAnnouncementRound


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
                "text": "This is absolutely amazing! I love it!",
                "created_at": "1",
                "view_count": 2000,
                "retweet_count": 1000,
                "quote_count": 1000,
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

        # Sort tweets by popularity using a weighted sum (views + quotes + retweets)
        feedback = list(
            sorted(
                feedback,
                key=lambda t: int(t["view_count"])
                + 3 * int(t["retweet_count"])
                + 5 * int(t["quote_count"]),
                reverse=True,
            )
        )

        # Keep only the most relevant tweet to avoid sending too many tokens to the LLM
        feedback = feedback[:10]

        return feedback
