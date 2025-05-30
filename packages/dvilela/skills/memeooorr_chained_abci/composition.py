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

"""This package contains round behaviours of MemeooorrChainedSkillAbciApp."""

import packages.dvilela.skills.memeooorr_abci.rounds as MemeooorrAbci
import packages.valory.skills.mech_interact_abci.rounds as MechInteractAbci
import packages.valory.skills.mech_interact_abci.states.final_states as MechFinalStates
import packages.valory.skills.mech_interact_abci.states.request as MechRequestStates
import packages.valory.skills.mech_interact_abci.states.response as MechResponseStates
import packages.valory.skills.registration_abci.rounds as RegistrationAbci
import packages.valory.skills.reset_pause_abci.rounds as ResetAndPauseAbci
import packages.valory.skills.transaction_settlement_abci.rounds as TransactionSettlementAbci
from packages.valory.skills.abstract_round_abci.abci_app_chain import (
    AbciAppTransitionMapping,
    chain,
)
from packages.valory.skills.abstract_round_abci.base import BackgroundAppConfig
from packages.valory.skills.termination_abci.rounds import (
    BackgroundRound,
    Event,
    TerminationAbciApp,
)


# Here we define how the transition between the FSMs should happen
# more information here: https://docs.autonolas.network/fsm_app_introduction/#composition-of-fsm-apps
abci_app_transition_mapping: AbciAppTransitionMapping = {
    RegistrationAbci.FinishedRegistrationRound: MemeooorrAbci.LoadDatabaseRound,
    MemeooorrAbci.FinishedToResetRound: ResetAndPauseAbci.ResetAndPauseRound,
    MemeooorrAbci.FinishedToSettlementRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    TransactionSettlementAbci.FinishedTransactionSubmissionRound: MemeooorrAbci.PostTxDecisionMakingRound,
    TransactionSettlementAbci.FailedRound: MemeooorrAbci.TransactionLoopCheckRound,
    ResetAndPauseAbci.FinishedResetAndPauseRound: MemeooorrAbci.PullMemesRound,
    ResetAndPauseAbci.FinishedResetAndPauseErrorRound: ResetAndPauseAbci.ResetAndPauseRound,
    MemeooorrAbci.FinishedForMechRequestRound: MechRequestStates.MechRequestRound,
    MechFinalStates.FinishedMechRequestRound: TransactionSettlementAbci.RandomnessTransactionSubmissionRound,
    MechFinalStates.FinishedMechResponseRound: MemeooorrAbci.PostMechResponseRound,
    MechFinalStates.FinishedMechRequestSkipRound: MemeooorrAbci.FailedMechRequestRound,
    MechFinalStates.FinishedMechResponseTimeoutRound: MemeooorrAbci.FailedMechResponseRound,
    MemeooorrAbci.FinishedForMechResponseRound: MechResponseStates.MechResponseRound,
}


termination_config = BackgroundAppConfig(
    round_cls=BackgroundRound,
    start_event=Event.TERMINATE,
    abci_app=TerminationAbciApp,
)

MemeooorrChainedSkillAbciApp = chain(
    (
        RegistrationAbci.AgentRegistrationAbciApp,
        MemeooorrAbci.MemeooorrAbciApp,
        TransactionSettlementAbci.TransactionSubmissionAbciApp,
        ResetAndPauseAbci.ResetPauseAbciApp,
        MechInteractAbci.MechInteractAbciApp,
    ),
    abci_app_transition_mapping,
).add_background_app(termination_config)
