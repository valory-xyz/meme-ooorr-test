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
import re
from abc import ABC
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from aea.protocols.base import Message

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.kv_store.connection import (
    PUBLIC_ID as KV_STORE_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.mirror_db.connection import (
    PUBLIC_ID as MIRRORDB_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.twikit.connection import (
    PUBLIC_ID as TWIKIT_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
from packages.dvilela.contracts.service_registry.contract import ServiceRegistryContract
from packages.dvilela.protocols.kv_store.dialogues import (
    KvStoreDialogue,
    KvStoreDialogues,
)
from packages.dvilela.protocols.kv_store.message import KvStoreMessage
from packages.dvilela.skills.memeooorr_abci.models import Params, SharedState
from packages.dvilela.skills.memeooorr_abci.rounds import SynchronizedData
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.protocols.ledger_api import LedgerApiMessage
from packages.valory.protocols.srr.dialogues import SrrDialogue, SrrDialogues
from packages.valory.protocols.srr.message import SrrMessage
from packages.valory.skills.abstract_round_abci.behaviours import BaseBehaviour
from packages.valory.skills.abstract_round_abci.models import Requests


BASE_CHAIN_ID = "base"
CELO_CHAIN_ID = "celo"
HTTP_OK = 200
MEMEOOORR_DESCRIPTION_PATTERN = r"^Memeooorr @(\w+)$"
IPFS_ENDPOINT = "https://gateway.autonolas.tech/ipfs/{ipfs_hash}"


TOKENS_QUERY = """
query Tokens {
  memeTokens {
    items {
      blockNumber
      chain
      heartCount
      id
      isUnleashed
      liquidity
      lpPairAddress
      owner
      timestamp
      memeNonce
      summonTime
      memeToken
      name
    }
  }
}
"""

PACKAGE_QUERY = """
query getPackages($package_type: String!) {
    units(where: {packageType: $package_type}) {
        id,
        packageType,
        publicId,
        packageHash,
        tokenId,
        metadataHash,
        description,
        owner,
        image
    }
}
"""


class MemeooorrBaseBehaviour(
    BaseBehaviour, ABC
):  # pylint: disable=too-many-ancestors,too-many-public-methods
    """Base behaviour for the memeooorr_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
        """Return the params."""
        return cast(Params, super().params)

    @property
    def local_state(self) -> SharedState:
        """Return the state."""
        return cast(SharedState, self.context.state)

    def _do_connection_request(
        self,
        message: Message,
        dialogue: Message,
        timeout: Optional[float] = None,
    ) -> Generator[None, None, Message]:
        """Do a request and wait the response, asynchronously."""

        self.context.outbox.put_message(message=message)
        request_nonce = self._get_request_nonce_from_dialogue(dialogue)  # type: ignore
        cast(Requests, self.context.requests).request_id_to_callback[
            request_nonce
        ] = self.get_callback_request()
        response = yield from self.wait_for_message(timeout=timeout)
        return response

    def _call_twikit(  # pylint: disable=too-many-locals,too-many-statements
        self, method: str, **kwargs: Any
    ) -> Generator[None, None, Any]:
        """Send a request message to the Twikit connection and handle MirrorDB interactions."""
        # Define the mapping of Twikit methods to MirrorDB methods
        twikit_to_mirrordb = {
            "like_tweet": "create_interaction",
            "retweet": "create_interaction",
            "follow_user": "create_interaction",
            "post": "create_tweet",
        }

        mirror_db_config_data = yield from self._read_kv(keys=("mirrod_db_config",))
        mirror_db_config_data = mirror_db_config_data.get("mirrod_db_config")  # type: ignore

        # Ensure mirror_db_config_data is parsed as JSON if it is a string
        if isinstance(mirror_db_config_data, str):
            mirror_db_config_data = json.loads(mirror_db_config_data)

        self.context.logger.info(f"MirrorDB config data: {mirror_db_config_data}")
        if mirror_db_config_data is None:
            self.context.logger.info("Registering with MirrorDB")
            yield from self._register_with_mirror_db()

        mirror_db_config_data = yield from self._read_kv(keys=("mirrod_db_config",))
        mirror_db_config_data = mirror_db_config_data.get("mirrod_db_config")  # type: ignore

        # Ensure mirror_db_config_data is parsed as JSON if it is a string
        if isinstance(mirror_db_config_data, str):
            mirror_db_config_data = json.loads(mirror_db_config_data)
            # Extract the agent_id, twitter_user_id and api_key from the mirrorDB config
            agent_id = mirror_db_config_data.get("agent_id")  # type: ignore
            if agent_id is None:
                self.context.logger.error("agent_id is None, which is not expected.")

            twitter_user_id = mirror_db_config_data.get("twitter_user_id")  # type: ignore
            if twitter_user_id is None:
                self.context.logger.error(
                    "twitter_user_id is None, which is not expected."
                )
        else:
            self.context.logger.error(
                "MirrorDB config data is None, which is not expected."
            )

        # Create the request message for Twikit
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWIKIT_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"method": method, "kwargs": kwargs}),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        # Handle MirrorDB interaction if applicable
        if method in twikit_to_mirrordb and mirror_db_config_data is not None:
            mirrordb_method = twikit_to_mirrordb[method]
            mirrordb_kwargs = kwargs.copy()
            if method == "post":
                tweet_text = mirrordb_kwargs.pop("tweets")[0][
                    "text"
                ]  # Remove 'tweets' key
                self.context.logger.info(f"Tweet text: {tweet_text}")
                tweet_data = {
                    "user_name": self.params.twitter_username,
                    "text": tweet_text,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "tweet_id": response_json["response"][0],
                }
                mirrordb_kwargs["tweet_data"] = tweet_data
                mirrordb_kwargs["agent_id"] = agent_id  # Ensure agent_id is passed
                mirrordb_kwargs[
                    "twitter_user_id"
                ] = twitter_user_id  # Ensure twitter_user_id is passed
                # Use the tweet ID returned by Twikit
                tweet_id = response_json["response"][0]
                mirrordb_kwargs["tweet_data"]["tweet_id"] = tweet_id
                self.context.logger.info(f"mirrorDb kwargs: {mirrordb_kwargs}")
            elif method in [
                "like_tweet",
                "retweet",
                "reply",
                "quote_tweet",
                "follow_user",
            ]:
                interaction_type = method.replace("_tweet", "").replace("_user", "")
                interaction_data = {
                    "interaction_type": interaction_type,
                }
                if interaction_type == "follow":
                    interaction_data["user_id"] = str(kwargs.get("user_id"))
                else:
                    interaction_data["tweet_id"] = str(kwargs.get("tweet_id"))

                mirrordb_kwargs = {
                    "interaction_data": interaction_data,
                    "agent_id": agent_id,
                    "twitter_user_id": twitter_user_id,
                }
                self.context.logger.info(f"mirrorDb kwargs: {mirrordb_kwargs}")
                mirrordb_response = yield from self._call_mirrordb(
                    "create_interaction", **mirrordb_kwargs
                )
                if mirrordb_response is None:
                    self.context.logger.error(
                        f"MirrorDB interaction for method {method} failed."
                    )

            mirrordb_response = yield from self._call_mirrordb(
                mirrordb_method, **mirrordb_kwargs
            )
            if mirrordb_response is None:
                self.context.logger.error(
                    f"MirrorDB interaction for method {method} failed."
                )

        return response_json["response"]  # type: ignore

    def _call_mirrordb(self, method: str, **kwargs: Any) -> Generator[None, None, Any]:
        """Send a request message to the MirrorDB connection."""
        try:
            srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
            srr_message, srr_dialogue = srr_dialogues.create(
                counterparty=str(MIRRORDB_CONNECTION_PUBLIC_ID),
                performative=SrrMessage.Performative.REQUEST,
                payload=json.dumps({"method": method, "kwargs": kwargs}),
            )
            srr_message = cast(SrrMessage, srr_message)
            srr_dialogue = cast(SrrDialogue, srr_dialogue)
            response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

            response_json = json.loads(response.payload)  # type: ignore

            if "error" in response_json:
                self.context.logger.error(response_json["error"])
                return None

            return response_json.get("response")  # type: ignore
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Exception while calling MirrorDB: {e}")
            return None

    def _register_with_mirror_db(self) -> Generator[None, None, None]:
        """Register with the MirrorDB service and save the configuration."""
        try:
            # Pull the twitter_user_id using Twikit
            twitter_user_data = yield from self._get_twitter_user_data()

            twitter_user_id = twitter_user_data.get("id")
            twitter_username = twitter_user_data.get("screen_name")
            twitter_name = twitter_user_data.get("name")

            if twitter_user_id is None:
                self.context.logger.error(
                    "twitter_user_id is None, which is not expected."
                )

            if twitter_username is None:
                self.context.logger.error(
                    "twitter_username is None, which is not expected."
                )

            if twitter_name is None:
                self.context.logger.error(
                    "twitter_name is None, which is not expected."
                )

            # Create the agent
            agent_data = {
                "agent_name": f"{self.synchronized_data.safe_contract_address}_{datetime.utcnow().isoformat()}",
            }
            twitter_account_data = {
                "username": twitter_username,
                "name": twitter_name,
                "twitter_user_id": twitter_user_id,
            }
            agent_response = yield from self._call_mirrordb(
                "create_agent", agent_data=agent_data
            )
            self.context.logger.info(f"Agent created: {agent_response}")

            agent_id = agent_response.get("agent_id")
            api_key = agent_response.get("api_key")

            if agent_id is None:
                self.context.logger.error("agent_id is None, which is not expected.")

            if api_key is None:
                self.context.logger.error("api_key is None, which is not expected.")

            twitter_account_data["api_key"] = api_key
            twitter_account_data["name"] = twitter_name
            twitter_account_data["twitter_user_id"] = twitter_user_id
            twitter_account_data["username"] = twitter_username

            # create the twitter account
            twitter_account_response = yield from self._call_mirrordb(
                "create_twitter_account",
                agent_id=agent_id,
                account_data=twitter_account_data,
            )
            self.context.logger.info(
                f"Twitter account created in MirrorDB: {twitter_account_response}"
            )

            # updating class vars
            yield from self._call_mirrordb("update_agent_id", agent_id=agent_id)
            yield from self._call_mirrordb(
                "update_twitter_user_id", twitter_user_id=twitter_user_id
            )
            yield from self._call_mirrordb("update_api_key", api_key=api_key)

            # Save the configuration to mirrorDB.json
            config_data = {
                "agent_id": agent_response.get("agent_id"),
                "twitter_user_id": twitter_user_id,
                "api_key": agent_response.get("api_key"),
            }
            self.context.logger.info(f"Saving MirrorDB config data: {config_data}")
            yield from self._write_kv({"mirrod_db_config": json.dumps(config_data)})
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Exception while registering with MirrorDB: {e}")

    def _get_twitter_user_data(self) -> Generator[None, None, Dict[str, str]]:
        """Get the twitter user data using Twikit."""

        TWIKIT_USERNAME = self.params.twitter_username
        if not TWIKIT_USERNAME:
            raise ValueError("TWIKIT_USERNAME environment variable not set")

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWIKIT_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(
                {
                    "method": "get_user_by_screen_name",
                    "kwargs": {"screen_name": TWIKIT_USERNAME},
                }
            ),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore
        if "error" in response_json:
            raise ValueError(response_json["error"])

        twitter_user_data = response_json.get("response")
        if twitter_user_data is None:
            self.context.logger.error(
                "twitter_user_data is None, which is not expected."
            )

        self.context.logger.info(f"Got twitter_user_data: {twitter_user_data}")
        return twitter_user_data

    def _call_genai(
        self,
        prompt: str,
        temperature: Optional[float] = None,
    ) -> Generator[None, None, Optional[str]]:
        """Send a request message from the skill context."""

        payload_data: Dict[str, Any] = {"prompt": prompt}

        if temperature is not None:
            payload_data["temperature"] = temperature

        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(GENAI_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps(payload_data),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore

        if "error" in response_json:
            self.context.logger.error(response_json["error"])
            return None

        return response_json["response"]  # type: ignore

    def _read_kv(
        self,
        keys: Tuple[str, ...],
    ) -> Generator[None, None, Optional[Dict]]:
        """Send a request message from the skill context."""
        self.context.logger.info(f"Reading keys from db: {keys}")
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.READ_REQUEST,
            keys=keys,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self._do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        if response.performative != KvStoreMessage.Performative.READ_RESPONSE:
            return None

        data = {key: response.data.get(key, None) for key in keys}  # type: ignore

        return data

    def _write_kv(
        self,
        data: Dict[str, str],
    ) -> Generator[None, None, bool]:
        """Send a request message from the skill context."""
        kv_store_dialogues = cast(KvStoreDialogues, self.context.kv_store_dialogues)
        kv_store_message, srr_dialogue = kv_store_dialogues.create(
            counterparty=str(KV_STORE_CONNECTION_PUBLIC_ID),
            performative=KvStoreMessage.Performative.CREATE_OR_UPDATE_REQUEST,
            data=data,
        )
        kv_store_message = cast(KvStoreMessage, kv_store_message)
        kv_store_dialogue = cast(KvStoreDialogue, srr_dialogue)
        response = yield from self._do_connection_request(
            kv_store_message, kv_store_dialogue  # type: ignore
        )
        return response == KvStoreMessage.Performative.SUCCESS

    def get_sync_timestamp(self) -> float:
        """Get the synchronized time from Tendermint's last block."""
        now = cast(
            SharedState, self.context.state
        ).round_sequence.last_round_transition_timestamp.timestamp()

        return now

    def get_sync_datetime(self) -> datetime:
        """Get the synchronized time from Tendermint's last block."""
        return datetime.fromtimestamp(self.get_sync_timestamp())

    def get_sync_time_str(self) -> str:
        """Get the synchronized time from Tendermint's last block."""
        return self.get_sync_datetime().strftime("%Y-%m-%d %H:%M:%S")

    def get_persona(self) -> Generator[None, None, str]:
        """Get the agent persona"""

        # If the persona is already in the synchronized data, return it
        if self.synchronized_data.persona:
            return self.synchronized_data.persona

        # If we reach this point, the agent has just started
        persona_config = self.params.persona

        # Try getting the persona from the db
        db_data = yield from self._read_kv(keys=("persona", "initial_persona"))

        if not db_data:
            self.context.logger.error(
                "Error while loading the database. Falling back to the config."
            )
            return persona_config

        # Load values from the config and database
        initial_persona_db = db_data.get("initial_persona", None)
        persona_db = db_data.get("persona", None)

        # If the initial persona is not in the db, we need to store it
        if initial_persona_db is None:
            yield from self._write_kv({"initial_persona": persona_config})
            initial_persona_db = persona_config

        # If the persona is not in the db, this is the first run
        if persona_db is None:
            yield from self._write_kv({"persona": persona_config})
            persona_db = persona_config

        # If the configured persona does not match the initial persona in the db,
        # the user has reconfigured it and we need to update it:
        if persona_config != initial_persona_db:
            yield from self._write_kv(
                {"persona": persona_config, "initial_persona": persona_config}
            )
            initial_persona_db = persona_config
            persona_db = persona_config

        # At this point, the db in the persona is the correct one
        return persona_db

    def get_native_balance(self) -> Generator[None, None, dict]:
        """Get the native balance"""

        # Safe
        self.context.logger.info(
            f"Getting native balance for the Safe {self.synchronized_data.safe_contract_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.synchronized_data.safe_contract_address,
            chain_id=self.get_chain_id(),
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            safe_balance = None
        else:
            safe_balance = cast(
                float, ledger_api_response.state.body["get_balance_result"]
            )
            safe_balance = safe_balance / 10**18  # from wei

        self.context.logger.info(f"Got Safe's native balance: {safe_balance}")

        # Agent
        self.context.logger.info(
            f"Getting native balance for the agent {self.context.agent_address}"
        )

        ledger_api_response = yield from self.get_ledger_api_response(
            performative=LedgerApiMessage.Performative.GET_STATE,
            ledger_callable="get_balance",
            account=self.context.agent_address,
            chain_id=self.get_chain_id(),
        )

        if ledger_api_response.performative != LedgerApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Error while retrieving the native balance: {ledger_api_response}"
            )
            agent_balance = None
        else:
            agent_balance = cast(
                float, ledger_api_response.state.body["get_balance_result"]
            )
            agent_balance = agent_balance / 10**18  # from wei

        self.context.logger.info(f"Got agent's native balance: {agent_balance}")

        return {"safe": safe_balance, "agent": agent_balance}

    def get_heart_burn_and_purge_data(
        self,
    ) -> Generator[None, None, Tuple[List[str], List[str], int]]:
        """Get heart, burn and purge data"""
        # Load previously hearted memes
        db_data = yield from self._read_kv(keys=("hearted_memes",))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            hearted_memes_str = "[]"
        else:
            hearted_memes_str = db_data["hearted_memes"] or "[]"

        hearted_memes = json.loads(hearted_memes_str)

        # Load purged memes
        purged_memes = yield from self.get_purged_memes_from_chain()

        # Get
        burnable_amount = yield from self.get_burnable_amount()

        return hearted_memes, purged_memes, burnable_amount

    def get_meme_available_actions(  # pylint: disable=too-many-arguments
        self,
        meme_data: Dict,
        hearted_memes: List[str],
        purged_memes: List[str],
        burnable_amount: int,
        maga_launched: bool,
    ) -> List[str]:
        """Get the available actions"""

        # Get the times
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        summon_time = datetime.fromtimestamp(meme_data["summon_time"])
        unleash_time = datetime.fromtimestamp(meme_data["unleash_time"])
        seconds_since_summon = (now - summon_time).total_seconds()
        seconds_since_unleash = (now - unleash_time).total_seconds()
        is_unleashed = meme_data.get("unleash_time", 0) != 0
        is_purged = meme_data.get("token_address", None) in purged_memes

        available_actions: List[str] = []

        # Heart
        if not is_unleashed and meme_data.get("token_nonce", None) in hearted_memes:
            available_actions.append("heart")

        # Unleash
        if not is_unleashed and seconds_since_summon > 24 * 3600:
            available_actions.append("unleash")

        # Collect
        if (
            is_unleashed
            and seconds_since_unleash < 24 * 3600
            and meme_data.get("token_nonce", None) in hearted_memes
        ):
            available_actions.append("collect")

        # Purge
        if is_unleashed and seconds_since_unleash > 24 * 3600 and not is_purged:
            available_actions.append("purge")

        # Burn
        if maga_launched and burnable_amount > 0:
            available_actions.append("burn")

        return available_actions

    def get_chain_id(self) -> str:
        """Get chain id"""
        if self.params.home_chain_id.lower() == BASE_CHAIN_ID:
            return BASE_CHAIN_ID

        if self.params.home_chain_id.lower() == CELO_CHAIN_ID:
            return CELO_CHAIN_ID

        return ""

    def get_native_ticker(self) -> str:
        """Get native ticker"""
        native_ticker = "ETH" if self.params.home_chain_id == "BASE" else "CELO"
        return native_ticker

    def get_packages(self, package_type: str) -> Generator[None, None, Optional[Dict]]:
        """Gets minted packages from the Olas subgraph"""

        self.context.logger.info("Getting packages from Olas subgraph...")

        SUBGRAPH_URL = (
            "https://subgraph.staging.autonolas.tech/subgraphs/name/autonolas-base"
        )

        headers = {
            "Content-Type": "application/json",
        }

        data = {
            "query": PACKAGE_QUERY,
            "variables": {
                "package_type": package_type,
            },
        }

        # Get all existing agents from the subgraph
        self.context.logger.info("Getting agents from subgraph")
        response = yield from self.get_http_response(  # type: ignore
            method="POST",
            url=SUBGRAPH_URL,
            headers=headers,
            content=json.dumps(data).encode(),
        )

        if response.status_code != HTTP_OK:  # type: ignore
            self.context.logger.error(
                f"Error getting agents from subgraph: {response}"  # type: ignore
            )
            return None

        response_json = json.loads(response.body)["data"]  # type: ignore
        return response_json

    def get_memeooorr_handles_from_subgraph(self) -> Generator[None, None, List[str]]:
        """Get Memeooorr service handles"""
        handles: List[str] = []
        services = yield from self.get_packages("service")
        if not services:
            return handles

        for service in services["units"]:
            match = re.match(MEMEOOORR_DESCRIPTION_PATTERN, service["description"])

            if not match:
                continue

            handle = match.group(1)

            # Exclude my own username
            if handle == self.params.twitter_username:
                continue

            handles.append(handle)

        self.context.logger.info(f"Got Twitter handles: {handles}")
        return handles

    def get_service_registry_address(self) -> str:
        """Get the service registry address"""
        return (
            self.params.service_registry_address_base
            if self.get_chain_id() == "base"
            else self.params.service_registry_address_celo
        )

    def get_olas_address(self) -> str:
        """Get the olas address"""
        return (
            self.params.olas_token_address_base
            if self.get_chain_id() == "base"
            else self.params.olas_token_address_celo
        )

    def get_meme_factory_address(self) -> str:
        """Get the meme factory address"""
        return (
            self.params.meme_factory_address_base
            if self.get_chain_id() == "base"
            else self.params.meme_factory_address_celo
        )

    def get_meme_factory_deployment_block(self) -> str:
        """Get the meme factory deployment block"""
        return (
            self.params.meme_factory_deployment_block_base
            if self.get_chain_id() == "base"
            else self.params.meme_factory_deployment_block_celo
        )

    def get_memeooorr_handles_from_chain(self) -> Generator[None, None, List[str]]:
        """Get Memeooorr service handles"""

        handles = []

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_service_registry_address(),
            contract_id=str(ServiceRegistryContract.contract_id),
            contract_callable="get_services_data",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(f"Could not get the service data: {response_msg}")
            return []

        services_data = cast(dict, response_msg.state.body.get("services_data", None))

        for service_data in services_data:
            response = yield from self.get_http_response(  # type: ignore
                method="GET",
                url=IPFS_ENDPOINT.format(ipfs_hash=service_data["ipfs_hash"]),
            )

            if response.status_code != HTTP_OK:  # type: ignore
                self.context.logger.error(
                    f"Error getting data from IPFS endpoint: {response}"  # type: ignore
                )
                continue

            metadata = json.loads(response.body)
            match = re.match(MEMEOOORR_DESCRIPTION_PATTERN, metadata["description"])

            if not match:
                continue

            handle = match.group(1)

            # Exclude my own username
            if handle == self.params.twitter_username:
                continue

            handles.append(handle)

        self.context.logger.info(f"Got Twitter handles: {handles}")

        return handles

    def get_meme_coins_from_chain(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""
        self.context.logger.info("Getting meme tokens from the chain")

        # Summons
        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_summon_data",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin summon events: {response_msg}"
            )
            return None

        tokens = cast(list, response_msg.state.body.get("tokens", None))

        # Unleashes
        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_events",
            event_name="Unleashed",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin summon events: {response_msg}"
            )
            return None

        unleash_events = cast(list, response_msg.state.body.get("events", None))

        # Add token addresses
        for event in unleash_events:
            for token in tokens:
                if token["token_nonce"] == event["token_nonce"]:
                    token["token_address"] = event["token_address"]

        (
            hearted_memes,
            purged_memes,
            burnable_amount,
        ) = yield from self.get_heart_burn_and_purge_data()

        maga_launched = False
        for token in tokens:
            if token["token_nonce"] == 1 and token.get("unleash_time", 0) != 0:
                maga_launched = True

        for token in tokens:
            token["available_actions"] = self.get_meme_available_actions(
                token, hearted_memes, purged_memes, burnable_amount, maga_launched
            )

        return tokens

    def get_meme_coins_from_subgraph(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""
        self.context.logger.info("Getting meme tokens from the subgraph")

        headers = {
            "Content-Type": "application/json",
        }

        query = {"query": TOKENS_QUERY}

        response = yield from self.get_http_response(  # type: ignore
            method="POST",
            url=self.params.meme_subgraph_url,
            headers=headers,
            content=json.dumps(query).encode(),
        )

        if response.status_code != HTTP_OK:  # type: ignore
            self.context.logger.error(
                f"Error getting agents from subgraph: {response}"  # type: ignore
            )
            return []

        response_json = json.loads(response.body)
        tokens = [
            {
                "block_number": int(t["blockNumber"]),
                "chain": t["chain"],
                "token_address": t["memeToken"],
                "liquidity": int(t["liquidity"]),
                "heart_count": int(t["heartCount"]),
                "is_unleashed": t["isUnleashed"],
                "lp_pair_address": t["lpPairAddress"],
                "owner": t["owner"],
                "timestamp": t["timestamp"],
                "meme_nonce": int(t["memeNonce"]),
                "summon_time": int(t["summonTime"]),
                "token_nonce": int(t["memeNonce"]),
            }
            for t in response_json["data"]["memeTokens"]["items"]
            if t["chain"] == self.get_chain_id()
            # to only include the updated factory contract address's token data
            and int(t["memeNonce"]) > 0
        ]

        for token in tokens:
            token_nonce = token.get("meme_nonce", None)
            token_address = token.get("token_address", None)

            response_msg = yield from self.get_contract_api_response(
                performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
                contract_address=self.get_meme_factory_address(),
                contract_id=str(MemeFactoryContract.contract_id),
                contract_callable="get_meme_summons_info",
                token_nonce=token_nonce,
                token_address=token_address,
                chain_id=self.get_chain_id(),
            )

            # Check that the response is what we expect
            if response_msg.performative != ContractApiMessage.Performative.STATE:
                self.context.logger.error(
                    f"Could not get the memecoin summon data: {response_msg}"
                )
                continue

            summon_data = cast(list, response_msg.state.body.get("token_data", None))

            token["token_name"] = summon_data[0]
            token["token_ticker"] = summon_data[1]
            token["token_supply"] = summon_data[2]
            token["eth_contributed"] = summon_data[3]
            token["summon_time"] = summon_data[4]
            token["unleash_time"] = summon_data[5]
            token["heart_count"] = summon_data[6]
            token["position_id"] = summon_data[7]
            token["is_native_first"] = summon_data[8]
            token["decimals"] = 18

        (
            hearted_memes,
            purged_memes,
            burnable_amount,
        ) = yield from self.get_heart_burn_and_purge_data()

        # We can only burn when the AG3NT token (nonce=1) has been unleashed
        maga_launched = False
        for token in tokens:
            if token["token_nonce"] == 1 and token.get("unleash_time", 0) != 0:
                maga_launched = True

        for token in tokens:
            token["available_actions"] = self.get_meme_available_actions(
                token, hearted_memes, purged_memes, burnable_amount, maga_launched
            )

        return tokens

    def get_meme_coins(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""

        meme_coins: Optional[List] = self.synchronized_data.meme_coins

        if meme_coins:
            return meme_coins

        meme_coins = yield from self.get_meme_coins_from_subgraph()
        return meme_coins

    def get_min_deploy_value(self) -> int:
        """Get min deploy value"""
        if self.get_chain_id() == "base":
            return int(0.01 * 1e18)

        if self.get_chain_id() == "celo":
            return 10

        # Should not happen
        return 0

    def get_tweets_from_db(self) -> Generator[None, None, List[Dict]]:
        """Get tweets"""
        db_data = yield from self._read_kv(keys=("tweets",))

        if db_data is None:
            tweets = []
        else:
            tweets = json.loads(db_data["tweets"] or "[]")

        return tweets

    def get_burnable_amount(self) -> Generator[None, None, int]:
        """Get burnable amount"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_burnable_amount",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the burnable amount: {response_msg}"
            )
            return 0

        burnable_amount = cast(int, response_msg.state.body.get("burnable_amount", 0))
        return burnable_amount

    def get_purged_memes_from_chain(self) -> Generator[None, None, List]:
        """Get purged memes"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_purge_data",
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the purged tokens: {response_msg}"
            )
            return []

        purged_addresses = cast(
            list, response_msg.state.body.get("purged_addresses", [])
        )
        return purged_addresses
