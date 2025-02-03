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

"""This module contains the shared state for the abci skill of MemeooorrAbciApp."""

import os
from pathlib import Path
from typing import Any, Optional

from packages.dvilela.skills.memeooorr_abci.rounds import MemeooorrAbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MemeooorrAbciApp


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool


class RandomnessApi(ApiSpecs):
    """A model that wraps ApiSpecs for randomness api specifications."""


class Params(BaseParams):  # pylint: disable=too-many-instance-attributes
    """Parameters."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the parameters object."""
        self.service_endpoint = self._ensure("service_endpoint", kwargs, str)
        self.minimum_gas_balance = self._ensure("minimum_gas_balance", kwargs, float)
        self.min_feedback_replies = self._ensure("min_feedback_replies", kwargs, int)
        self.meme_factory_address_base = self._ensure(
            "meme_factory_address_base", kwargs, str
        )
        self.meme_factory_address_celo = self._ensure(
            "meme_factory_address_celo", kwargs, str
        )
        self.olas_token_address_base = self._ensure(
            "olas_token_address_base", kwargs, str
        )
        self.olas_token_address_celo = self._ensure(
            "olas_token_address_celo", kwargs, str
        )
        self.service_registry_address_base = self._ensure(
            "service_registry_address_base", kwargs, str
        )
        self.service_registry_address_celo = self._ensure(
            "service_registry_address_celo", kwargs, str
        )
        self.persona = self._ensure("persona", kwargs, str)
        self.feedback_period_min_hours = self._ensure(
            "feedback_period_min_hours", kwargs, int
        )
        self.feedback_period_max_hours = self._ensure(
            "feedback_period_max_hours", kwargs, int
        )
        self.home_chain_id = self._ensure("home_chain_id", kwargs, str)
        self.twitter_username = self._ensure("twitter_username", kwargs, str)

        self.meme_factory_deployment_block_base = self._ensure(
            "meme_factory_deployment_block_base", kwargs, int
        )
        self.meme_factory_deployment_block_celo = self._ensure(
            "meme_factory_deployment_block_celo", kwargs, int
        )
        self.meme_subgraph_url = self._ensure("meme_subgraph_url", kwargs, str)
        self.skip_engagement = self._ensure("skip_engagement", kwargs, bool)

        self.min_summon_amount_base = self._ensure(
            "min_summon_amount_base", kwargs, float
        )
        self.max_summon_amount_base = self._ensure(
            "max_summon_amount_base", kwargs, float
        )
        self.max_heart_amount_base = self._ensure(
            "max_heart_amount_base", kwargs, float
        )

        self.min_summon_amount_celo = self._ensure(
            "min_summon_amount_celo", kwargs, float
        )
        self.max_summon_amount_celo = self._ensure(
            "max_summon_amount_celo", kwargs, float
        )
        self.staking_contract_address = self._ensure(
            "max_heart_amount_celo", kwargs, float
        )

        self.max_heart_amount_celo = self._ensure("max_heart_amount_celo", kwargs, str)

        self.staking_contract_address: str = self._ensure(
            "staking_contract_address", kwargs, str
        )
        self.staking_interaction_sleep_time: int = self._ensure(
            "staking_interaction_sleep_time", kwargs, int
        )
        self.mech_activity_checker_contract: str = self._ensure(
            "mech_activity_checker_contract", kwargs, str
        )
        self.store_path = get_store_path(kwargs)

        self.staking_contract_address: str = self._ensure(
            "staking_contract_address", kwargs, str
        )
        self.staking_interaction_sleep_time: int = self._ensure(
            "staking_interaction_sleep_time", kwargs, int
        )
        self.mech_activity_checker_contract: str = self._ensure(
            "mech_activity_checker_contract", kwargs, str
        )
        self.store_path = get_store_path(kwargs)
        super().__init__(*args, **kwargs)


def get_store_path(kwargs: dict) -> Path:
    """Get the path of the store."""
    path = kwargs.get("store_path", "")
    if not path:
        msg = "The path to the store must be provided as a keyword argument."
        raise ValueError(msg)

    # check if the path exists, and we can write to it
    if (
        not os.path.isdir(path)
        or not os.access(path, os.W_OK)
        or not os.access(path, os.R_OK)
    ):
        msg = f"The store path {path!r} is not a directory or is not writable."
        raise ValueError(msg)

    return Path(path)
