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

"""This package contains the rounds of MemeooorrAbciApp."""

import json
from enum import Enum
from typing import Dict, FrozenSet, Set, cast, Optional, Tuple

from packages.dvilela.skills.memeooorr_abci.payloads import (
    CheckFundsPayload,
    SearchTweetsPayload,
    DeploymentPayload,
    PostTweetPayload
)
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    get_name,
)


class Event(Enum):
    """MemeooorrAbciApp Events"""

    DONE = "done"
    NO_FUNDS = "no_funds"
    NO_TWEETS = "no_tweets"
    SETTLE = "settle"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def pending_tweets(self) -> list:
        """Get the pending tweets."""
        return cast(list, json.loads(cast(str, self.db.get("pending_tweets", "[]"))))

    @property
    def most_voted_tx_hash(self) -> Optional[str]:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))


class SearchTweetsRound(CollectSameUntilThresholdRound):
    """SearchTweetsRound"""

    payload_class = SearchTweetsPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            pending_tweets = json.loads(self.most_voted_payload)

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.pending_tweets): pending_tweets,
                }
            )

            event = Event.DONE if pending_tweets else Event.NO_TWEETS

            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class CheckFundsRound(CollectSameUntilThresholdRound):
    """CheckFundsRound"""

    payload_class = CheckFundsPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # this needs to be mentioned for static checkers
            # Event.NO_MAJORITY, Event.DONE, Event.NO_FUNDS, Event.NO_MAJORITY
            payload = json.loads(self.most_voted_payload)
            event = Event(payload["event"])
            return self.synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class DeploymentRound(CollectSameUntilThresholdRound):
    """DeploymentRound"""

    payload_class = DeploymentPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            pending_tweets = json.loads(self.most_voted_payload.pending_tweets)
            tx_hash = self.most_voted_payload.tx_hash

            event = Event.SETTLE if tx_hash else Event.DONE

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.pending_tweets): pending_tweets,
                    get_name(SynchronizedData.most_voted_tx_hash): tx_hash,
                }
            )

            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class PostTweetRound(CollectSameUntilThresholdRound):
    """PostTweetRound"""

    payload_class = PostTweetPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # this needs to be mentioned for static checkers
            # Event.NO_MAJORITY, Event.DONE, Event.NO_FUNDS, Event.NO_MAJORITY
            payload = json.loads(self.most_voted_payload)
            event = Event(payload["event"])
            return self.synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class FinishedNoTweetsRound(DegenerateRound):
    """FinishedNoTweetsRound"""


class FinishedTxPreparationRound(DegenerateRound):
    """FinishedTxPreparationRound"""


class FinishedPostingRound(DegenerateRound):
    """FinishedPostingRound"""


class MemeooorrAbciApp(AbciApp[Event]):
    """MemeooorrAbciApp"""

    initial_round_cls: AppState = SearchTweetsRound
    initial_states: Set[AppState] = {SearchTweetsRound, DeploymentRound}
    transition_function: AbciAppTransitionFunction = {
        SearchTweetsRound: {
            Event.DONE: CheckFundsRound,
            Event.NO_TWEETS: FinishedNoTweetsRound,
            Event.NO_MAJORITY: SearchTweetsRound,
            Event.ROUND_TIMEOUT: SearchTweetsRound,
        },
        CheckFundsRound: {
            Event.DONE: DeploymentRound,
            Event.NO_FUNDS: CheckFundsRound,
            Event.NO_MAJORITY: CheckFundsRound,
            Event.ROUND_TIMEOUT: CheckFundsRound,
        },
        DeploymentRound: {
            Event.DONE: PostTweetRound,
            Event.SETTLE: FinishedTxPreparationRound,
            Event.NO_MAJORITY: DeploymentRound,
            Event.ROUND_TIMEOUT: DeploymentRound,
        },
        PostTweetRound: {
            Event.DONE: FinishedPostingRound,
            Event.NO_FUNDS: PostTweetRound,
            Event.NO_MAJORITY: PostTweetRound,
            Event.ROUND_TIMEOUT: PostTweetRound,
        },
        FinishedTxPreparationRound: {},
        FinishedPostingRound: {},
        FinishedNoTweetsRound: {},
    }
    final_states: Set[AppState] = {FinishedPostingRound}
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        CheckFundsRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedPostingRound: set(),
        FinishedTxPreparationRound: set(),
        FinishedNoTweetsRound: set(),
    }
