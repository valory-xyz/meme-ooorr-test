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

from typing import Set, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.chain import (
    CheckFundsBehaviour,
    DeploymentBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.db import (
    LoadDatabaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.llm import (
    AnalizeFeedbackBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.behaviour_classes.twitter import (
    CollectFeedbackBehaviour,
    PostAnnouncementBehaviour,
    PostTweetBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import MemeooorrAbciApp
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)


class MemeooorrRoundBehaviour(AbstractRoundBehaviour):
    """MemeooorrRoundBehaviour"""

    initial_behaviour_cls = CollectFeedbackBehaviour
    abci_app_cls = MemeooorrAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        LoadDatabaseBehaviour,
        PostTweetBehaviour,
        CollectFeedbackBehaviour,
        AnalizeFeedbackBehaviour,
        CheckFundsBehaviour,
        DeploymentBehaviour,
        PostAnnouncementBehaviour,
    ]
