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

from dataclasses import dataclass
from typing import Any, Dict, Optional
from aea.exceptions import enforce

from packages.dvilela.skills.memeooorr_abci.rounds import MemeooorrAbciApp
from packages.valory.skills.abstract_round_abci.models import ApiSpecs, BaseParams
from packages.valory.skills.abstract_round_abci.models import (
    BenchmarkTool as BaseBenchmarkTool,
)
from packages.valory.skills.abstract_round_abci.models import Requests as BaseRequests
from packages.valory.skills.abstract_round_abci.models import (
    SharedState as BaseSharedState,
)
from packages.valory.skills.mech_interact_abci.models import MechParams


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    abci_app_cls = MemeooorrAbciApp


Requests = BaseRequests
BenchmarkTool = BaseBenchmarkTool


class RandomnessApi(ApiSpecs):
    """A model that wraps ApiSpecs for randomness api specifications."""


@dataclass(frozen=True)
class AlternativeModelForTweets:  # pylint: disable=too-many-instance-attributes
    """The configuration for the alternative LLM models."""

    use: bool
    url: str
    api_key: str
    model: str
    max_tokens: int
    top_p: int
    top_k: int
    presence_penalty: int
    frequency_penalty: int
    temperature: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlternativeModelForTweets":
        """Create an instance from a dictionary."""
        return cls(
            use=data["use"],
            url=data["url"],
            api_key=data["api_key"],
            model=data["model"],
            max_tokens=data["max_tokens"],
            top_p=data["top_p"],
            top_k=data["top_k"],
            presence_penalty=data["presence_penalty"],
            frequency_penalty=data["frequency_penalty"],
            temperature=data["temperature"],
        )


class Params(MechParams):  # pylint: disable=too-many-instance-attributes
    """Parameters."""
    @property
    def ipfs_address(self) -> str:
        """Get the IPFS address."""
        if self._ipfs_address.endswith("/"):
            return self._ipfs_address
        return f"{self._ipfs_address}/"

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

        self.max_heart_amount_celo = self._ensure(
            "max_heart_amount_celo", kwargs, float
        )

        self.staking_token_contract_address: str = self._ensure(
            "staking_token_contract_address", kwargs, str
        )
        self.activity_checker_contract_address: str = self._ensure(
            "activity_checker_contract_address", kwargs, str
        )
        self.alternative_model_for_tweets: AlternativeModelForTweets = (
            AlternativeModelForTweets.from_dict(kwargs["alternative_model_for_tweets"])
        )
        self.tx_loop_breaker_count = self._ensure("tx_loop_breaker_count", kwargs, int)

        multisend_batch_size = kwargs.get("multisend_batch_size", None)
        enforce(multisend_batch_size is not None, "multisend_batch_size not specified!")
        self.multisend_address: str = multisend_batch_size

        # self.multisend_batch_size: int = self._ensure(
        #     "multisend_batch_size", kwargs, int
        # )

        # mech_contract_address = kwargs.get("mech_contract_address", None)
        # enforce(
        #     mech_contract_address is not None, "mech_contract_address not specified!"
        # )
        # self.mech_contract_address: str = mech_contract_address

        # # self.mech_contract_address: str = self._ensure(
        # #     "mech_contract_address", kwargs, str
        # # )

        # self.mech_request_price: Optional[int] = kwargs.get("mech_request_price", None)

        # self.mech_chain_id: Optional[str] = kwargs.get("mech_chain_id", "gnosis")
        # self.mech_wrapped_native_token_address: Optional[str] = kwargs.get(
        #     "mech_wrapped_native_token_address", None
        # )

        # mech_interaction_sleep_time = kwargs.get("mech_interaction_sleep_time", None)
        # enforce(
        #     mech_interaction_sleep_time is not None,
        #     "mech_interaction_sleep_time not specified!",
        # )
        # self.mech_interaction_sleep_time: str = mech_interaction_sleep_time

        # # self.mech_interaction_sleep_time: int = self._ensure(
        # #     "mech_interaction_sleep_time", kwargs, int
        # # )

        # use_mech_marketplace = kwargs.get("use_mech_marketplace", None)
        # enforce(
        #     use_mech_marketplace is not None,
        #     "use_mech_marketplace not specified!",
        # )
        # self.use_mech_marketplace: str = use_mech_marketplace

        # self.use_mech_marketplace = self._ensure("use_mech_marketplace", kwargs, bool)

        # ipfs_address = kwargs.get("ipfs_address", None)
        # enforce(multisend_batch_size is not None, "ipfs_address not specified!")
        # self.ipfs_address: str = ipfs_address
        # self._ipfs_address: str = self._ensure("ipfs_address", kwargs, str)

        super().__init__(*args, **kwargs)
