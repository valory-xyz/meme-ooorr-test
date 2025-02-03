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
    ActionDecisionPayload,
    ActionPreparationPayload,
    ActionTweetPayload,
    CallCheckpointPayload,
    CheckFundsPayload,
    CheckStakingPayload,
    CollectFeedbackPayload,
    EngageTwitterPayload,
    LoadDatabasePayload,
    PostTxDecisionMakingPayload,
    PullMemesPayload,
)
from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    BaseTxPayload,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    NONE_EVENT_ATTRIBUTE,
    get_name,
)


class StakingState(Enum):
    """Staking state enumeration for the staking."""

    UNSTAKED = 0
    STAKED = 1
    EVICTED = 2


class Event(Enum):
    """MemeooorrAbciApp Events"""

    DONE = "done"
    NO_FUNDS = "no_funds"
    SETTLE = "settle"
    REFINE = "refine"
    ERROR = "ERROR"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    NOT_ENOUGH_FEEDBACK = "not_enough_feedback"
    WAIT = "wait"
    NO_MEMES = "no_memes"
    TO_DEPLOY = "to_deploy"
    TO_ACTION_TWEET = "to_action_tweet"
    ACTION = "action"
    SERVICE_NOT_STAKED = "service_not_staked"
    SERVICE_EVICTED = "service_evicted"
    NEXT_CHECKPOINT_NOT_REACHED_YET = "next_checkpoint_not_reached_yet"


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
    def participants_to_db(self) -> DeserializedCollection:
        """Get the participants_to_db."""
        return self._get_deserialized("participants_to_db")

    @property
    def persona(self) -> Optional[str]:
        """Get the persona."""
        return cast(str, self.db.get("persona", None))

    @property
    def meme_coins(self) -> List[Dict]:
        """Get the meme_coins."""
        return cast(list, json.loads(cast(str, self.db.get("meme_coins", "[]"))))

    @property
    def pending_tweet(self) -> Optional[List]:
        """Get the pending tweet."""
        pending_tweet_str = self.db.get("pending_tweet", None)
        return json.loads(pending_tweet_str) if pending_tweet_str else []

    @property
    def feedback(self) -> List:
        """Get the feedback."""
        feedback = self.db.get("feedback", None)
        return json.loads(feedback) if feedback else []

    @property
    def token_action(self) -> Dict:
        """Get the token action."""
        return cast(dict, json.loads(cast(str, self.db.get("token_action", "{}"))))

    @property
    def most_voted_tx_hash(self) -> Optional[str]:
        """Get the most_voted_tx_hash."""
        return cast(str, self.db.get_strict("most_voted_tx_hash"))

    @property
    def final_tx_hash(self) -> Optional[str]:
        """Get the verified tx hash."""
        return self.db.get("final_tx_hash", None)

    @property
    def tx_submitter(self) -> str:
        """Get the round that submitted a tx to transaction_settlement_abci."""
        return str(self.db.get_strict("tx_submitter"))

    @property
    def is_staking_kpi_met(self) -> bool:
        """Get the is_staking_kpi_met."""
        return bool(self.db.get_strict("is_staking_kpi_met"))

    @property
    def participant_to_staking(self) -> DeserializedCollection:
        """Get the participants to the staking round."""
        return self._get_deserialized("participant_to_staking")


class EventRoundBase(CollectSameUntilThresholdRound):
    """EventRoundBase"""

    synchronized_data_class = SynchronizedData
    payload_class = BaseTxPayload  # will be overwritten
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            event = Event(self.most_voted_payload)
            return self.synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class LoadDatabaseRound(CollectSameUntilThresholdRound):
    """LoadDatabaseRound"""

    payload_class = LoadDatabasePayload
    synchronized_data_class = SynchronizedData
    collection_key = get_name(SynchronizedData.participants_to_db)
    selection_key = (get_name(SynchronizedData.persona),)

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            payload = dict(zip(self.selection_key, self.most_voted_payload_values))

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.persona): payload["persona"],
                },
            )

            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    required_class_attributes = ()


class CheckStakingRound(CollectSameUntilThresholdRound):
    """CheckStakingRound"""

    payload_class = CheckStakingPayload
    synchronized_data_class = SynchronizedData
    collection_key = get_name(SynchronizedData.participant_to_staking)
    selection_key = (get_name(SynchronizedData.is_staking_kpi_met),)


class PullMemesRound(CollectSameUntilThresholdRound):
    """PullMemesRound"""

    payload_class = PullMemesPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        # This needs to be mentioned for static checkers
        # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT

        if self.threshold_reached:
            if self.most_voted_payload is None:
                meme_coins = []
            else:
                meme_coins = json.loads(self.most_voted_payload)

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.meme_coins): json.dumps(
                        meme_coins, sort_keys=True
                    ),
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    # Event.ROUND_TIMEOUT  # this needs to be mentioned for static checkers


class CollectFeedbackRound(CollectSameUntilThresholdRound):
    """CollectFeedbackRound"""

    payload_class = CollectFeedbackPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            feedback = json.loads(self.most_voted_payload)

            # API error
            if feedback is None:
                return self.synchronized_data, Event.ERROR

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.feedback): json.dumps(
                        feedback, sort_keys=True
                    )
                },
            )
            return synchronized_data, Event.DONE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class EngageTwitterRound(EventRoundBase):
    """EngageTwitterRound"""

    payload_class = EngageTwitterPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.ERROR, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class ActionDecisionRound(CollectSameUntilThresholdRound):
    """ActionDecisionRound"""

    payload_class = ActionDecisionPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.WAIT
            payload = ActionDecisionPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )
            event = Event(payload.event)
            synchronized_data = self.synchronized_data

            if event == Event.DONE:
                token_action = {
                    "action": payload.action,
                    "token_address": payload.token_address,
                    "token_nonce": payload.token_nonce,
                    "token_name": payload.token_name,
                    "token_ticker": payload.token_ticker,
                    "token_supply": payload.token_supply,
                    "amount": payload.amount,
                    "tweet": payload.tweet,
                }

                synchronized_data = synchronized_data.update(
                    synchronized_data_class=SynchronizedData,
                    **{
                        get_name(SynchronizedData.token_action): json.dumps(
                            token_action, sort_keys=True
                        ),
                    },
                )

                if payload.new_persona:
                    synchronized_data = synchronized_data.update(
                        synchronized_data_class=SynchronizedData,
                        **{
                            get_name(SynchronizedData.persona): payload.new_persona,
                        },
                    )

            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class ActionPreparationRound(CollectSameUntilThresholdRound):
    """ActionPreparationRound"""

    payload_class = ActionPreparationPayload
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            # This needs to be mentioned for static checkers
            # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT
            payload = ActionPreparationPayload(
                *(("dummy_sender",) + self.most_voted_payload_values)
            )

            # Error preparing the transaction
            if payload.tx_hash is None:
                return self.synchronized_data, Event.ERROR

            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    get_name(SynchronizedData.most_voted_tx_hash): payload.tx_hash,
                },
            )

            # Transaction has been settled already
            if payload.tx_hash == "":
                return synchronized_data, Event.DONE

            # The tx has been prepared
            return synchronized_data, Event.SETTLE

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY
        return None


class ActionTweetRound(EventRoundBase):
    """ActionTweetRound"""

    payload_class = ActionTweetPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.ERROR


class CheckFundsRound(EventRoundBase):
    """CheckFundsRound"""

    payload_class = CheckFundsPayload  # type: ignore
    required_class_attributes = ()
    # This needs to be mentioned for static checkers
    # Event.DONE, Event.NO_MAJORITY, Event.ROUND_TIMEOUT, Event.NO_FUNDS


class PostTxDecisionMakingRound(EventRoundBase):
    """PostTxDecisionMakingRound"""

    payload_class = PostTxDecisionMakingPayload  # type: ignore
    synchronized_data_class = SynchronizedData
    required_class_attributes = ()

    # This needs to be mentioned for static checkers
    # Event.DONE, Event.ERROR, Event.NO_MAJORITY, Event.ROUND_TIMEOUT


class CallCheckpointRound(CollectSameUntilThresholdRound):
    """A round for the checkpoint call preparation."""

    payload_class = CallCheckpointPayload
    done_event: Enum = Event.DONE
    no_majority_event: Enum = Event.NO_MAJORITY
    selection_key = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
        get_name(SynchronizedData.service_staking_state),
        get_name(SynchronizedData.previous_checkpoint),
        get_name(SynchronizedData.is_checkpoint_reached),
    )
    collection_key = get_name(SynchronizedData.participant_to_checkpoint)
    synchronized_data_class = SynchronizedData
    # the none event is not required because the `CallCheckpointPayload` payload does not allow for `None` values
    required_class_attributes = tuple(
        attribute
        for attribute in CollectSameUntilThresholdRound.required_class_attributes
        if attribute != NONE_EVENT_ATTRIBUTE
    )

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Enum]]:
        """Process the end of the block."""
        res = super().end_block()
        if res is None:
            return None

        synced_data, event = cast(Tuple[SynchronizedData, Enum], res)

        if event != Event.DONE:
            return res

        if synced_data.service_staking_state == StakingState.UNSTAKED:
            return synced_data, Event.SERVICE_NOT_STAKED

        if synced_data.service_staking_state == StakingState.EVICTED:
            return synced_data, Event.SERVICE_EVICTED

        if synced_data.most_voted_tx_hash is None:
            return synced_data, Event.NEXT_CHECKPOINT_NOT_REACHED_YET

        return res


class FinishedToResetRound(DegenerateRound):
    """FinishedToResetRound"""


class FinishedToSettlementRound(DegenerateRound):
    """FinishedToSettlementRound"""


class MemeooorrAbciApp(AbciApp[Event]):
    """MemeooorrAbciApp"""

    initial_round_cls: AppState = LoadDatabaseRound
    initial_states: Set[AppState] = {
        LoadDatabaseRound,
        PullMemesRound,
        ActionPreparationRound,
        PostTxDecisionMakingRound,
    }
    transition_function: AbciAppTransitionFunction = {
        LoadDatabaseRound: {
            Event.DONE: CheckStakingRound,
            Event.NO_MAJORITY: LoadDatabaseRound,
            Event.ROUND_TIMEOUT: LoadDatabaseRound,
        },
        CheckStakingRound: {
            Event.DONE: PullMemesRound,
            Event.NO_MAJORITY: CheckStakingRound,
            Event.ROUND_TIMEOUT: CheckStakingRound,
        },
        PullMemesRound: {
            Event.DONE: CollectFeedbackRound,
            Event.NO_MAJORITY: PullMemesRound,
            Event.ROUND_TIMEOUT: PullMemesRound,
        },
        CollectFeedbackRound: {
            Event.DONE: EngageTwitterRound,
            Event.ERROR: CollectFeedbackRound,
            Event.NO_MAJORITY: CollectFeedbackRound,
            Event.ROUND_TIMEOUT: CollectFeedbackRound,
        },
        EngageTwitterRound: {
            Event.DONE: ActionDecisionRound,
            Event.ERROR: EngageTwitterRound,
            Event.NO_MAJORITY: EngageTwitterRound,
            Event.ROUND_TIMEOUT: EngageTwitterRound,
        },
        ActionDecisionRound: {
            Event.DONE: ActionPreparationRound,
            Event.WAIT: FinishedToResetRound,
            Event.NO_MAJORITY: ActionDecisionRound,
            Event.ROUND_TIMEOUT: ActionDecisionRound,
        },
        ActionPreparationRound: {
            Event.DONE: ActionTweetRound,  # This will never happen
            Event.ERROR: FinishedToResetRound,
            Event.SETTLE: CheckFundsRound,
            Event.NO_MAJORITY: ActionPreparationRound,
            Event.ROUND_TIMEOUT: ActionPreparationRound,
        },
        ActionTweetRound: {
            Event.DONE: CallCheckpointRound,
            Event.ERROR: ActionTweetRound,
            Event.NO_MAJORITY: ActionTweetRound,
            Event.ROUND_TIMEOUT: ActionTweetRound,
        },
        CheckFundsRound: {
            Event.DONE: FinishedToSettlementRound,
            Event.NO_FUNDS: CheckFundsRound,
            Event.NO_MAJORITY: CheckFundsRound,
            Event.ROUND_TIMEOUT: CheckFundsRound,
        },
        PostTxDecisionMakingRound: {
            Event.DONE: FinishedToResetRound,
            Event.ACTION: ActionPreparationRound,
            Event.NO_MAJORITY: PostTxDecisionMakingRound,
            Event.ROUND_TIMEOUT: PostTxDecisionMakingRound,
        },
        CallCheckpointRound: {
            Event.DONE: FinishedToSettlementRound,
            Event.SERVICE_NOT_STAKED: FinishedToResetRound,
            Event.SERVICE_EVICTED: FinishedToResetRound,
            Event.NEXT_CHECKPOINT_NOT_REACHED_YET: FinishedToResetRound,
            Event.ROUND_TIMEOUT: CallCheckpointRound,
            Event.NO_MAJORITY: CallCheckpointRound,
        },
        FinishedToResetRound: {},
        FinishedToSettlementRound: {},
    }
    final_states: Set[AppState] = {FinishedToResetRound, FinishedToSettlementRound}
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset(["persona"])
    db_pre_conditions: Dict[AppState, Set[str]] = {
        LoadDatabaseRound: set(),
        PullMemesRound: set(),
        ActionPreparationRound: set(),
        PostTxDecisionMakingRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedToResetRound: set(),
        FinishedToSettlementRound: {"most_voted_tx_hash"},
    }
