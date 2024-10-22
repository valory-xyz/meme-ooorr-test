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
from packages.dvilela.skills.memeooorr_abci.prompts import DEPLOYMENT_RESPONSE_PROMPT
from packages.dvilela.skills.memeooorr_abci.rounds import (
    Event,
    PostTweetPayload,
    PostTweetRound,
    SearchTweetsPayload,
    SearchTweetsRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


MAX_TWEET_CHARS = 280


def tweet_len(tweet: str) -> int:
    """Calculates a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"]


class SearchTweetsBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """SearchTweetsBehaviour"""

    matching_round: Type[AbstractRound] = SearchTweetsRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            pending_deployments = yield from self.get_pending_deployments()

            payload = SearchTweetsPayload(
                sender=self.context.agent_address,
                fake_news=json.dumps(pending_deployments, sort_keys=True),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_pending_deployments(self) -> Generator[None, None, List]:
        """Get the pending tweet queue"""

        pending_deployments = self.synchronized_data.pending_deployments

        # Get responded tweets from the db
        response = yield from self._read_kv(keys=("deployed_tokens",))

        if response is None:
            self.context.logger.error(
                "Error reading from the database. Responded tweets couldn't be loaded and therefore no new tweets will be searched."
            )
            return pending_deployments

        deployed_tokens = (
            json.loads(response["deployed_tokens"])
            if response["deployed_tokens"]
            else []
        )
        self.context.logger.info(
            f"Loaded {len(deployed_tokens)} responded tweets from db"
        )

        # Search new tweets
        tweets = yield from self._call_twikit(method="search", query=query)

        if tweets is None:
            self.context.logger.error("No tweets match the query")
            return pending_deployments

        self.context.logger.info(f"Retrieved {len(tweets)} tweets")

        # Iterate all the tweets
        for tweet in tweets:
            self.context.logger.info(
                f"Analyzing tweet {tweet['id']!r}: {tweet['text']}"
            )

            if tweet["id"] in deployed_tokens:
                self.context.logger.info("Tweet was already processed")
                continue

            # Add new tweets to the pending queue
            # TODO

        return pending_deployments


class PostTweetBehaviour(MemeooorrBaseBehaviour):  # pylint: disable=too-many-ancestors
    """PostTweetBehaviour"""

    matching_round: Type[AbstractRound] = PostTweetRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            event = yield from self.get_event()

            payload = PostTweetPayload(
                sender=self.context.agent_address,
                event=event,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_event(  # pylint: disable=too-many-locals
        self,
    ) -> Generator[None, None, Dict]:
        """Post the announcement"""

        # Get the first tweet in the queue
        deployment = self.synchronized_data.pending_deployments[0]

        # Get deployed tokens from the db
        response = yield from self._read_kv(keys=("deployed_tokens",))

        if response is None:
            self.context.logger.error(
                "Error reading from the database. Responded tweets couldn't be loaded and therefore no new tweets will be responded."
            )
            return Event.API_ERROR.value

        deployed_tokens = (
            json.loads(response["deployed_tokens"])
            if response["deployed_tokens"]
            else []
        )
        self.context.logger.info(
            f"Loaded {len(deployed_tokens)} responded tweets from db"
        )

        # Send a request to the LLM
        self.context.logger.info(
            f"Preparing response for tweet {deployment['tweet']['id']}"
        )

        prompt = DEPLOYMENT_RESPONSE_PROMPT.format(
            token_name=deployment["token_name"],
            token_ticker=deployment["token_name"],
            tweet=deployment["tweet"]["text"],
        )
        llm_response = yield from self._call_genai(prompt=prompt)
        self.context.logger.info(f"LLM response: {llm_response}")

        if llm_response is None:
            self.context.logger.error("Error getting a response from the LLM.")
            return Event.API_ERROR.value

        # Postprocess the tweet
        t_len = tweet_len(llm_response)
        if t_len > MAX_TWEET_CHARS:
            self.context.logger.error(
                f"Tweet is too long [{t_len}]. will retry: {llm_response}"
            )
            return Event.API_ERROR

        self.context.logger.info(f"Response to tweet is OK!: {llm_response}")

        if not self.params.enable_posting:
            self.context.logger.info("Posting is disabled")
            return Event.DONE.value

        self.context.logger.info("Posting the response...")

        tweet_ids = yield from self._call_twikit(
            method="post",
            tweets=[{"text": llm_response, "reply_to": deployment["tweet"]["id"]}],
        )

        if tweet_ids is None:
            self.context.logger.error("Failed posting to Twitter.")
            return Event.API_ERROR.value

        # Write responded tweets
        yield from self._write_kv({"deployed_tokens": json.dumps(deployed_tokens)})
        self.context.logger.info("Wrote deployed_tokens to db")

        return Event.DONE.value
