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
from typing import Dict, FrozenSet, List, Optional, Set, Tuple, cast

from packages.dvilela.skills.memeooorr_abci.payloads import (
    AnalizeFeedbackPayload,
    CheckFundsPayload,
    CollectFeedbackPayload,
    DeploymentPayload,
    PostTweetPayload,
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
    SETTLE = "settle"
    REFINE = "refine"
    API_ERROR = "api_error"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    NOT_ENOUGH_FEEDBACK = "not_enough_feedback"


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
    def token_proposal(self) -> Dict:
        """Get the tokwn proposal."""
        return cast(dict, json.loads(cast(str, self.db.get("token_proposal", "{}"))))

    @property
    def feedback(self) -> Optional[List]:
        """Get the feedback."""
        return cast(list, json.loads(cast(str, self.db.get("feedback", None))))

    @property
    def most_voted_tx_hash(self) -> Optional[str]:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def tx_flag(self) -> Optional[str]:
        """Get the tx_flag."""
        return cast(str, self.db.get("tx_flag", None))

    @property
    def final_tx_hash(self) -> str:
        """Get the verified tx hash."""
        return cast(str, self.db.get_strict("final_tx_hash"))


class PostInitialTweetRound(CollectSameUntilThresholdRound):
    """PostInitialTweetRound"""

    payload_class = PostTweetPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = json.loads(self.most_voted_payload)
            token_proposal = payload["token_proposal"]

            # API error
            if not token_proposal:
                return self.synchronized_data, Event.API_ERROR

            synchronized_data = self.synchronized_data.update(
                **{get_name(SynchronizedData.token_proposal): token_proposal}
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class PostDeploymentRound(PostInitialTweetRound):
    """PostDeploymentRound"""

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class PostRefinedTweetRound(PostInitialTweetRound):
    """PostRefinedTweetRound"""

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class CollectFeedbackRound(CollectSameUntilThresholdRound):
    """CollectFeedbackRound"""

    payload_class = CollectFeedbackPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = json.loads(self.most_voted_payload)
            feedback = payload["feedback"]

            # API error
            if feedback is None:
                return self.synchronized_data, Event.API_ERROR

            # Not enough replies
            if len(feedback) < self.context.params.min_feedback_replies:
                return self.synchronized_data, Event.NOT_ENOUGH_FEEDBACK

            synchronized_data = self.synchronized_data.update(
                **{get_name(SynchronizedData.feedback): feedback}
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class AnalizeFeedbackRound(CollectSameUntilThresholdRound):
    """AnalizeFeedbackRound"""

    payload_class = AnalizeFeedbackPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

            # Errors
            if not self.most_voted_payload:
                return self.synchronized_data, Event.API_ERROR

            token_proposal = json.loads(self.most_voted_payload)

            # Refine
            if not token_proposal["deploy"]:
                synchronized_data = self.synchronized_data.update(
                    **{get_name(SynchronizedData.token_proposal): token_proposal}
                )
                return synchronized_data, Event.REFINE

            # Deploy
            return self.synchronized_data, Event.DONE

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
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.NO_FUNDS
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
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = json.loads(self.most_voted_payload)

            if payload.tx_flag is None:
                return self.synchronized_data, Event.API_ERROR

            synchronized_data = self.synchronized_data.update(
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                    get_name(SynchronizedData.tx_flag): payload.tx_flag,
                }
            )

            event = Event.DONE if payload.tx_flag == "done" else Event.SETTLE
            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class FinishedToResetRound(DegenerateRound):
    """FinishedToResetRound"""


class FinishedToSettlementRound(DegenerateRound):
    """FinishedToSettlementRound"""


class MemeooorrAbciApp(AbciApp[Event]):
    """MemeooorrAbciApp"""

    initial_round_cls: AppState = PostInitialTweetRound
    initial_states: Set[AppState] = {PostInitialTweetRound, DeploymentRound}
    transition_function: AbciAppTransitionFunction = {
        PostInitialTweetRound: {
            Event.DONE: CollectFeedbackRound,
            Event.API_ERROR: PostInitialTweetRound,
            Event.NO_MAJORITY: PostInitialTweetRound,
            Event.ROUND_TIMEOUT: PostInitialTweetRound,
        },
        CollectFeedbackRound: {
            Event.DONE: AnalizeFeedbackRound,
            Event.API_ERROR: CollectFeedbackRound,
            Event.NOT_ENOUGH_FEEDBACK: FinishedToResetRound,
            Event.NO_MAJORITY: CollectFeedbackRound,
            Event.ROUND_TIMEOUT: CollectFeedbackRound,
        },
        AnalizeFeedbackRound: {
            Event.DONE: CheckFundsRound,
            Event.REFINE: PostRefinedTweetRound,
            Event.API_ERROR: AnalizeFeedbackRound,
            Event.NO_MAJORITY: AnalizeFeedbackRound,
            Event.ROUND_TIMEOUT: AnalizeFeedbackRound,
        },
        CheckFundsRound: {
            Event.DONE: DeploymentRound,
            Event.NO_FUNDS: CheckFundsRound,
            Event.NO_MAJORITY: CheckFundsRound,
            Event.ROUND_TIMEOUT: CheckFundsRound,
        },
        DeploymentRound: {
            Event.DONE: PostDeploymentRound,
            Event.SETTLE: FinishedToSettlementRound,
            Event.API_ERROR: DeploymentRound,
            Event.NO_MAJORITY: DeploymentRound,
            Event.ROUND_TIMEOUT: DeploymentRound,
        },
        PostDeploymentRound: {
            Event.DONE: FinishedToResetRound,
            Event.API_ERROR: PostDeploymentRound,
            Event.NO_MAJORITY: PostDeploymentRound,
            Event.ROUND_TIMEOUT: PostDeploymentRound,
        },
        PostRefinedTweetRound: {
            Event.DONE: FinishedToResetRound,
            Event.API_ERROR: PostRefinedTweetRound,
            Event.NO_MAJORITY: PostRefinedTweetRound,
            Event.ROUND_TIMEOUT: PostRefinedTweetRound,
        },
        FinishedToResetRound: {},
        FinishedToSettlementRound: {},
    }
    final_states: Set[AppState] = {FinishedToResetRound, FinishedToSettlementRound}
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        PostInitialTweetRound: set(),
        DeploymentRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedToResetRound: set(),
        FinishedToSettlementRound: {"most_voted_tx_hash"},
    }
