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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple, Union, cast

from aea.protocols.base import Message
from twitter_text import parse_tweet  # type: ignore

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
MAX_TWEET_CHARS = 280


TOKENS_QUERY = """
query Tokens {
  memeTokens {
    items {
      blockNumber
      chain
      heartCount
      id
      isUnleashed
      isPurged
      liquidity
      lpPairAddress
      owner
      timestamp
      memeNonce
      summonTime
      unleashTime
      memeToken
      name
      symbol
      hearters
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


def is_tweet_valid(tweet: str) -> bool:
    """Checks a tweet length"""
    return parse_tweet(tweet).asdict()["weightedLength"] <= MAX_TWEET_CHARS


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
        # Track this API call with our unified tracking function
        yield from self.track_twikit_api_usage(method, **kwargs)

        mirror_db_config_data = (
            yield from self._handle_mirror_db_interactions_pre_twikit()
        )

        if mirror_db_config_data is None:
            self.context.logger.error(
                "MirrorDB config data is None after registration attempt. This is unexpected and indicates a potential issue with the registration process."
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
            if (
                "Twitter account is locked or suspended" in response_json["error"]
                or "Twitter account is not logged in" in response_json["error"]
            ):
                self.context.state.env_var_status["needs_update"] = True
                self.context.state.env_var_status["env_vars"][
                    "TWIKIT_USERNAME"
                ] = response_json["error"]
                self.context.state.env_var_status["env_vars"][
                    "TWIKIT_EMAIL"
                ] = response_json["error"]
                self.context.state.env_var_status["env_vars"][
                    "TWIKIT_COOKIES"
                ] = response_json["error"]

            self.context.logger.error(response_json["error"])
            return None

        # Handle MirrorDB interaction if applicable
        yield from self._handle_mirrordb_interaction_post_twikit(
            method, kwargs, response_json, mirror_db_config_data  # type: ignore
        )
        return response_json["response"]  # type: ignore

    def _handle_mirror_db_interactions_pre_twikit(
        self,
    ) -> Generator[None, None, Optional[Dict]]:
        """Handle MirrorDB interactions."""

        # registartion check for mirrorDB
        mirror_db_config_data = yield from self._mirror_db_registration_check()  # type: ignore

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
            # api_key is likely no longer present or needed
            # api_key = mirror_db_config_data.get("api_key")
            # if api_key is None:
            #    self.context.logger.error("api_key is None, which is not expected.")

            # Removed: updating instance vars in connection - state is managed by behaviour
            # yield from self._call_mirrordb("update_agent_id", agent_id=agent_id)
            # yield from self._call_mirrordb("update_api_key", api_key=api_key) # Removed api_key call
            # yield from self._call_mirrordb(
            #     "update_twitter_user_id", twitter_user_id=twitter_user_id
            # )

            try:
                twitter_user_id_from_cookie = yield from self._get_twitter_user_id_from_cookie()  # type: ignore
                twitter_user_id_from_cookie = twitter_user_id_from_cookie.split("u=")[
                    -1
                ]
            except ValueError as e:
                self.context.logger.error(
                    f"Error getting Twitter user ID from cookie: {e}"
                )
                return None

            if twitter_user_id_from_cookie != twitter_user_id:
                self.context.logger.warning(
                    f"Twitter user id from cookie : {twitter_user_id_from_cookie} != Twitter ID stored : {twitter_user_id}"
                )
                self.context.logger.info(
                    "New Twitter account detected! Updating username attribute in MirrorDB."
                )
                # Update the config in KV store first
                yield from self._update_mirror_db_config_with_new_twitter_user_id(
                    new_twitter_user_id=twitter_user_id_from_cookie
                )

                # Update the stored username attribute (Interface 2.0)
                try:
                    # 1. Get the new username from Twikit
                    new_twitter_user_data = (
                        yield from self._get_twitter_user_data()
                    )  # Re-fetch with current cookies
                    new_twitter_username = (
                        new_twitter_user_data.get("screen_name")
                        if new_twitter_user_data
                        else None
                    )

                    if not new_twitter_username:
                        self.context.logger.error(
                            "Failed to get new Twitter username from Twikit. Cannot update attribute."
                        )
                    else:
                        self.context.logger.info(
                            f"New Twitter username detected: {new_twitter_username}"
                        )

                        # 2. Get the username attribute definition ID from KV store
                        kv_data = yield from self._read_kv(
                            keys=("twitter_username_attr_def_id",)
                        )
                        username_attr_def_id_str = (
                            kv_data.get("twitter_username_attr_def_id")
                            if kv_data
                            else None
                        )

                        if not username_attr_def_id_str:
                            self.context.logger.error(
                                "Missing twitter_username_attr_def_id in KV Store. Cannot update attribute."
                            )
                        else:
                            username_attr_def_id = int(username_attr_def_id_str)

                            # 3. Try to GET the existing attribute instance to find its specific attribute_id
                            # We need the specific AgentAttribute ID to PUT an update
                            # Endpoint: GET /api/agents/{agent_id}/attributes/{attr_def_id}/
                            get_endpoint = f"/api/agents/{agent_id}/attributes/{username_attr_def_id}/"
                            existing_attribute = yield from self._call_mirrordb(
                                "GET", endpoint=get_endpoint
                            )

                            attribute_id_to_update = None
                            if (
                                existing_attribute
                                and isinstance(existing_attribute, dict)
                                and "attribute_id" in existing_attribute
                            ):
                                attribute_id_to_update = existing_attribute[
                                    "attribute_id"
                                ]

                            if attribute_id_to_update:
                                self.context.logger.info(
                                    f"Found existing username attribute instance (ID: {attribute_id_to_update}). Updating..."
                                )

                                # 4a. Prepare PUT request to update
                                update_endpoint = (
                                    f"/api/agent-attributes/{attribute_id_to_update}"
                                )
                                update_payload = {"string_value": new_twitter_username}
                                auth_data_update = (
                                    yield from self._sign_mirrordb_request(
                                        update_endpoint, agent_id
                                    )
                                )

                                if auth_data_update:
                                    request_body_update = {
                                        "agent_attr": update_payload,
                                        "auth": auth_data_update,
                                    }
                                    update_response = yield from self._call_mirrordb(
                                        "PUT",
                                        endpoint=update_endpoint,
                                        data=request_body_update,
                                    )
                                    if update_response:
                                        self.context.logger.info(
                                            f"Successfully updated username attribute for agent {agent_id}."
                                        )
                                    else:
                                        self.context.logger.error(
                                            f"Failed to update username attribute for agent {agent_id}."
                                        )
                                else:
                                    self.context.logger.error(
                                        f"Failed to sign username attribute update request for agent {agent_id}."
                                    )
                            else:
                                self.context.logger.warning(
                                    f"Could not find existing username attribute for agent {agent_id} via GET {get_endpoint} or it lacked an ID. Attempting to create it instead. Response: {existing_attribute}"
                                )
                                # 4b. If GET failed or attribute missing, try to POST (create) it
                                create_endpoint = f"/api/agents/{agent_id}/attributes/"
                                create_payload = {
                                    "agent_id": agent_id,
                                    "attr_def_id": username_attr_def_id,
                                    "string_value": new_twitter_username,
                                }
                                auth_data_create = (
                                    yield from self._sign_mirrordb_request(
                                        create_endpoint, agent_id
                                    )
                                )

                                if auth_data_create:
                                    request_body_create = {
                                        "agent_attr": create_payload,
                                        "auth": auth_data_create,
                                    }
                                    create_response = yield from self._call_mirrordb(
                                        "POST",
                                        endpoint=create_endpoint,
                                        data=request_body_create,
                                    )
                                    if create_response:
                                        self.context.logger.info(
                                            f"Successfully created username attribute for agent {agent_id} after update detection."
                                        )
                                    else:
                                        self.context.logger.error(
                                            f"Failed to create username attribute for agent {agent_id} after update detection."
                                        )
                                else:
                                    self.context.logger.error(
                                        f"Failed to sign username attribute creation request for agent {agent_id}."
                                    )

                except (ValueError, TypeError, KeyError, Exception) as e:
                    self.context.logger.error(
                        f"Error during username attribute update process: {e}"
                    )

        return mirror_db_config_data

    def _handle_mirrordb_interaction_post_twikit(  # pylint: disable=too-many-locals, too-many-statements
        self,
        method: str,
        kwargs: Dict[str, Any],
        response_json: Dict[str, Any],
        mirror_db_config_data: Dict[str, Any],
    ) -> Generator[None, None, None]:
        """Handle MirrorDB interaction after Twikit response."""
        # Check if the method is one we need to record
        recordable_methods = {"post", "like_tweet", "retweet", "follow_user"}
        if method not in recordable_methods or mirror_db_config_data is None:
            return  # Only record specific actions if config exists

        agent_id = mirror_db_config_data.get("agent_id")
        if not agent_id:
            self.context.logger.error("Missing agent_id in MirrorDB config.")
            return

        # Retrieve the stored Attribute Definition ID for twitter interactions from KV store
        kv_data = yield from self._read_kv(keys=("twitter_interactions_attr_def_id",))
        attr_def_id_str = (
            kv_data.get("twitter_interactions_attr_def_id") if kv_data else None
        )

        if attr_def_id_str is None:
            self.context.logger.error(
                "Missing twitter_interactions_attr_def_id in KV Store. Cannot record interaction."
            )
            # Optionally, could try to fetch it from MirrorDB here again, but for now we fail.
            return

        try:
            attr_def_id = int(attr_def_id_str)
        except (ValueError, TypeError):
            self.context.logger.error(
                f"Invalid twitter_interactions_attr_def_id format in KV Store: {attr_def_id_str}. Cannot record interaction."
            )
            return

        mirrordb_method = (
            "POST"  # Always creating a new attribute instance per interaction
        )
        mirrordb_endpoint = f"/api/agents/{agent_id}/attributes/"
        interaction_action: Optional[str] = None
        interaction_details: Dict[str, Any] = {}

        if method == "post":
            # Prepare tweet data details
            try:
                tweet_text = kwargs.get("tweets", [{}])[0].get("text")
                twikit_tweet_id = response_json.get("response", [None])[0]
                if not tweet_text or not twikit_tweet_id:
                    self.context.logger.error(
                        f"Missing tweet text or ID from Twikit response/kwargs for post: {kwargs}, {response_json}"
                    )
                    return

                interaction_action = "post"
                interaction_details["tweet_id"] = str(twikit_tweet_id)
                interaction_details["text"] = tweet_text
                # Add user_name if needed: interaction_details["user_name"] = self.params.twitter_username
            except (IndexError, KeyError, TypeError) as e:
                self.context.logger.error(
                    f"Error processing Twikit 'post' data for MirrorDB attribute: {e}"
                )
                return

        elif method in ["like_tweet", "retweet"]:
            # Prepare like/retweet details
            target_tweet_id = kwargs.get("tweet_id")
            if not target_tweet_id:
                self.context.logger.error(
                    f"Missing tweet_id in kwargs for {method}: {kwargs}"
                )
                return
            interaction_action = method.split("_")[0]  # "like" or "retweet"
            interaction_details["tweet_id"] = str(target_tweet_id)

        elif method == "follow_user":
            # Prepare follow details
            target_user_id = kwargs.get("user_id")
            if not target_user_id:
                self.context.logger.error(
                    f"Missing user_id in kwargs for follow: {kwargs}"
                )
                return
            interaction_action = "follow"
            interaction_details["user_id"] = str(target_user_id)

        # Ensure an action was determined
        if interaction_action is None:
            self.context.logger.warning(
                f"Could not determine interaction action for method '{method}'"
            )
            return

        # Construct the JSON value for the attribute
        json_value = {
            "action": interaction_action,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "details": interaction_details,
        }

        # Construct the AgentAttribute payload
        mirrordb_data = {
            "agent_id": agent_id,
            "attr_def_id": attr_def_id,
            "string_value": None,
            "integer_value": None,
            "float_value": None,
            "boolean_value": None,
            "date_value": None,
            "json_value": json_value,
        }

        # --- Signing Logic --- (Signing the attribute creation request)
        auth_data = yield from self._sign_mirrordb_request(mirrordb_endpoint, agent_id)
        if auth_data is None:
            self.context.logger.error(
                f"Failed to generate signature for {mirrordb_method} {mirrordb_endpoint}. Aborting interaction recording."
            )
            return

        # --- Call MirrorDB to create the attribute ---
        self.context.logger.info(
            f"Recording interaction via MirrorDB: {mirrordb_method} {mirrordb_endpoint} Data: {mirrordb_data} Auth: {auth_data is not None}"
        )
        try:
            # Construct the full request body expected by the endpoint
            request_body = {"agent_attr": mirrordb_data, "auth": auth_data}
            mirrordb_response = yield from self._call_mirrordb(
                mirrordb_method,
                endpoint=mirrordb_endpoint,
                # Pass the full request body as the 'data' kwarg
                data=request_body,
                # auth kwarg is no longer needed here
            )
            if mirrordb_response is None:
                self.context.logger.warning(
                    f"MirrorDB interaction recording for method {method} might have failed (returned None)."
                )
            else:
                self.context.logger.info(
                    f"Successfully recorded interaction for method {method}. Response: {mirrordb_response}"
                )
        except Exception as e:
            self.context.logger.error(
                f"Exception during MirrorDB interaction recording for method {method}: {e}"
            )

        # Store attr_def_id in KV Store instead
        success = yield from self._write_kv(
            {"twitter_interactions_attr_def_id": str(attr_def_id)}
        )
        if success:
            self.context.logger.info(
                f"Stored twitter_interactions_attr_def_id={attr_def_id} in KV Store."
            )
        else:
            self.context.logger.error(
                f"Failed to store twitter_interactions_attr_def_id={attr_def_id} in KV Store."
            )

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

    def _get_twitter_user_id_from_cookie(self) -> Generator[None, None, str]:
        """Get the Twitter user ID from the Twikit connection."""
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(TWIKIT_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"method": "get_twitter_user_id", "kwargs": {}}),
        )
        srr_message = cast(SrrMessage, srr_message)
        srr_dialogue = cast(SrrDialogue, srr_dialogue)
        response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

        response_json = json.loads(response.payload)  # type: ignore
        if "error" in response_json:
            raise ValueError(response_json["error"])

        twitter_user_id = response_json.get("response")
        if twitter_user_id is None:
            self.context.logger.error("twitter_user_id is None, which is not expected.")

        return twitter_user_id

    def _call_genai(
        self,
        prompt: str,
        schema: Optional[Dict] = None,
        temperature: Optional[float] = None,
    ) -> Generator[None, None, Optional[str]]:
        """Send a request message from the skill context."""

        payload_data: Dict[str, Any] = {"prompt": prompt}

        if schema is not None:
            payload_data["schema"] = schema

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
        if response is None:
            self.context.logger.error(
                "Received None response from KV Store connection during write."
            )
            return False
        self.context.logger.info(
            f"KV Store write response performative: {response.performative}"
        )
        return response.performative == KvStoreMessage.Performative.SUCCESS

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

    def get_meme_available_actions(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        meme_data: Dict,
        burnable_amount: int,
        maga_launched: bool,
    ) -> Generator[None, None, List[str]]:
        """Get the available actions"""

        # Get the times
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        summon_time = datetime.fromtimestamp(meme_data["summon_time"])
        unleash_time = datetime.fromtimestamp(meme_data["unleash_time"])
        seconds_since_summon = (now - summon_time).total_seconds()
        seconds_since_unleash = (now - unleash_time).total_seconds()
        is_unleashed = meme_data.get("unleash_time", 0) != 0
        is_purged = meme_data.get("is_purged")
        is_hearted = (
            self.synchronized_data.safe_contract_address
            in meme_data.get("hearters", {}).keys()
        )
        token_nonce = meme_data.get("token_nonce")
        collectable_amount = yield from self.get_collectable_amount(
            cast(int, token_nonce)
        )
        is_collectable = collectable_amount > 0

        available_actions: List[str] = []

        # Heart
        if not is_unleashed and meme_data.get("token_nonce", None) != 1:
            available_actions.append("heart")

        # Unleash
        if (
            not is_unleashed
            and seconds_since_summon > 24 * 3600
            and meme_data.get("token_nonce", None) != 1
        ):
            available_actions.append("unleash")

        # Collect
        if (
            is_unleashed
            and seconds_since_unleash < 24 * 3600
            and is_hearted
            and is_collectable
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
        if self.params.home_chain_id.lower() == BASE_CHAIN_ID:
            return "ETH"

        if self.params.home_chain_id.lower() == CELO_CHAIN_ID:
            return "CELO"

        return ""

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

        # Parse the response body
        response_body = json.loads(response.body)  # type: ignore

        # Check if 'data' key exists in the response
        if "data" not in response_body:
            self.context.logger.error(
                f"Expected 'data' key in response, but got: {response_body}"
            )
            return None

        return response_body["data"]

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

    def get_active_twitter_handles(
        self, days: int = 7
    ) -> Generator[None, None, List[str]]:
        """Get Twitter handles of agents with interactions in the last N days using AFMDB 2.0 attributes.

        Assumes MirrorDB API endpoints:
        - GET /api/attributes/definition/{attr_def_id}/instances/
        - GET /api/agents/{agent_id}/attributes/definition/{attr_def_id}/
        """
        self.context.logger.info(
            f"Fetching Twitter handles of agents active in the last {days} days..."
        )
        handles: List[str] = []
        try:
            # 1. Get required attribute definition IDs and agent type ID from KV Store
            required_keys = (
                "twitter_interactions_attr_def_id",
                "twitter_username_attr_def_id",
                "memeooorr_agent_type_id",  # Add agent type ID
            )
            attr_def_ids_data = yield from self._read_kv(keys=required_keys)

            if not attr_def_ids_data or any(
                attr_def_ids_data.get(k) is None for k in required_keys
            ):
                self.context.logger.error(
                    f"Missing required attribute definition IDs or agent type ID in KV Store: {attr_def_ids_data}. Cannot fetch recent handles."
                )
                return handles

            interactions_attr_def_id = attr_def_ids_data[
                "twitter_interactions_attr_def_id"
            ]
            username_attr_def_id = attr_def_ids_data["twitter_username_attr_def_id"]
            agent_type_id = attr_def_ids_data["memeooorr_agent_type_id"]
            self.context.logger.debug(
                f"Using interactions_attr_def_id={interactions_attr_def_id}, username_attr_def_id={username_attr_def_id}, agent_type_id={agent_type_id}"
            )

            # 2. Get all "twitter_interactions" attribute instances using the correct endpoint
            # Endpoint: GET /api/agent-types/{type_id}/attributes/{attr_def_id}/values
            interactions_endpoint = f"/api/agent-types/{agent_type_id}/attributes/{interactions_attr_def_id}/values"
            all_interactions = yield from self._call_mirrordb(
                "GET", endpoint=interactions_endpoint
            )

            if all_interactions is None or not isinstance(all_interactions, list):
                self.context.logger.warning(
                    f"Could not retrieve interaction attributes from MirrorDB endpoint {interactions_endpoint}. Response: {all_interactions}"
                )
                return handles
            self.context.logger.info(
                f"Retrieved {len(all_interactions)} total interaction attributes."
            )

            # 3. Filter interactions by timestamp (last N days)
            recent_agent_ids = set()
            cutoff_time = datetime.utcnow() - timedelta(days=days)

            for interaction in all_interactions:
                try:
                    json_value = interaction.get("json_value")
                    if not isinstance(json_value, dict):
                        self.context.logger.warning(
                            f"Skipping interaction with non-dict json_value: {interaction}"
                        )
                        continue

                    timestamp_str = json_value.get("timestamp")
                    if not timestamp_str:
                        self.context.logger.warning(
                            f"Skipping interaction with missing timestamp: {interaction}"
                        )
                        continue

                    # Handle potential timezone info (e.g., Z for UTC)
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + "+00:00"

                    interaction_time = datetime.fromisoformat(timestamp_str)

                    # Ensure we compare offset-aware with offset-naive correctly (assuming UTC)
                    if interaction_time.tzinfo:
                        interaction_time_utc = interaction_time.astimezone(
                            timezone.utc
                        ).replace(tzinfo=None)
                    else:
                        interaction_time_utc = (
                            interaction_time  # Assume UTC if no timezone
                        )

                    if interaction_time_utc >= cutoff_time:
                        agent_id = interaction.get("agent_id")
                        if agent_id is not None:
                            recent_agent_ids.add(agent_id)

                except (ValueError, TypeError, KeyError) as e:
                    self.context.logger.warning(
                        f"Error processing interaction timestamp or structure: {interaction}. Error: {e}. Skipping."
                    )
                    continue

            self.context.logger.info(
                f"Found {len(recent_agent_ids)} unique agents with recent interactions."
            )

            # 4. For each recent agent_id, get their username attribute
            own_username = self.params.twitter_username
            for agent_id in recent_agent_ids:
                try:
                    # ASSUMPTION: This endpoint exists and returns a single attribute instance or 404.
                    # Response format assumed: { "string_value": "username", ... }
                    username_endpoint = (
                        f"/api/agents/{agent_id}/attributes/{username_attr_def_id}/"
                    )
                    username_attribute = yield from self._call_mirrordb(
                        "GET", endpoint=username_endpoint
                    )

                    if username_attribute and isinstance(username_attribute, dict):
                        username = username_attribute.get("string_value")
                        if username and username != own_username:
                            handles.append(username)
                        elif not username:
                            self.context.logger.warning(
                                f"Found username attribute for agent {agent_id}, but string_value is missing or empty."
                            )
                    else:
                        self.context.logger.warning(
                            f"Could not retrieve username attribute for active agent {agent_id} from endpoint {username_endpoint}. Response: {username_attribute}"
                        )

                except Exception as e:
                    self.context.logger.error(
                        f"Error retrieving username for agent {agent_id}: {e}"
                    )

            self.context.logger.info(
                f"Returning {len(handles)} recent Memeooorr handles (excluding self): {handles}"
            )

        except Exception as e:
            self.context.logger.error(f"Error in get_recent_memeooorr_handles: {e}")

        return handles

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

    def get_collectable_amount(self, token_nonce: int) -> Generator[None, None, int]:
        """Get collectable amount"""
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.get_meme_factory_address(),
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_collectable_amount",
            token_nonce=token_nonce,
            wallet_address=self.synchronized_data.safe_contract_address,
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the collectable amount: {response_msg}"
            )
            return 0

        collectable_amount = cast(
            int, response_msg.state.body.get("collectable_amount", 0)
        )
        self.context.logger.info(
            f"Collectable amount for token {token_nonce}: {collectable_amount}"
        )
        return collectable_amount

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

    def _update_mirror_db_config_with_new_twitter_user_id(
        self, new_twitter_user_id: str
    ) -> Generator[None, None, bool]:
        """Update the mirrod_db_config with the new twitter_user_id."""
        # Read the current configuration
        mirror_db_config_data = yield from self._read_kv(keys=("mirrod_db_config",))
        mirror_db_config_data = mirror_db_config_data.get("mirrod_db_config")  # type: ignore

        # Ensure mirror_db_config_data is parsed as JSON if it is a string
        if isinstance(mirror_db_config_data, str):
            mirror_db_config_data = json.loads(mirror_db_config_data)

        # Check if mirror_db_config_data is a dictionary
        if isinstance(mirror_db_config_data, dict):
            # Update the twitter_user_id
            mirror_db_config_data["twitter_user_id"] = new_twitter_user_id

            # Write the updated configuration back to the KV store
            success = yield from self._write_kv(
                {"mirrod_db_config": json.dumps(mirror_db_config_data)}
            )
            return success

        self.context.logger.error(
            "mirror_db_config_data is not a dictionary. failed to update new twitter_user_id."
        )
        return False

    def _mirror_db_registration_check(
        self,
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Check if the agent_id is registered in the mirrorDB, if not then register with mirrorDB."""
        # Read the current configuration
        mirror_db_config_data = yield from self._read_kv(keys=("mirrod_db_config",))
        mirror_db_config_data = mirror_db_config_data.get("mirrod_db_config")  # type: ignore

        if mirror_db_config_data is None:
            self.context.logger.info("No MirrorDB configuration found. Registering...")
            yield from self._register_with_mirror_db()

            # Re-read after potential registration
            mirror_db_config_data_read = yield from self._read_kv(
                keys=("mirrod_db_config",)
            )
            mirror_db_config_data = mirror_db_config_data_read.get("mirrod_db_config") if mirror_db_config_data_read else None  # type: ignore

        # Ensure mirror_db_config_data is parsed as JSON if it is a string
        if isinstance(mirror_db_config_data, str):
            try:
                mirror_db_config_data = json.loads(mirror_db_config_data)
            except json.JSONDecodeError:
                self.context.logger.error(
                    f"Failed to parse mirror_db_config: {mirror_db_config_data}"
                )
                return None  # Cannot proceed if config is invalid

        elif isinstance(mirror_db_config_data, dict):
            # Already a dict, assume it's okay
            pass
        elif mirror_db_config_data is not None:
            # If it's not None, not a string, not a dict, then it's an unexpected type
            self.context.logger.error(
                f"Unexpected type for mirror_db_config_data: {type(mirror_db_config_data)}. Setting to None."
            )
            mirror_db_config_data = None

        # Ensure the final result is a dict or None
        if not isinstance(mirror_db_config_data, dict):
            self.context.logger.warning(
                f"Final mirror_db_config_data is not a dict: {mirror_db_config_data}. Returning None."
            )
            return None

        return cast(Optional[Dict[str, Any]], mirror_db_config_data)

    def replace_tweet_with_alternative_model(
        self, prompt: str
    ) -> Generator[None, None, Optional[str]]:
        """Replaces a tweet with one generated by the alternative LLM model"""

        model_config = self.params.alternative_model_for_tweets
        self.context.logger.info(f"Alternative LLM model config: {model_config}")

        if not model_config.use:
            self.context.logger.info("Alternative LLM model is disabled")
            return None

        self.context.logger.info("Calling the alternative LLM model")

        payload = {
            "model": model_config.model,
            "max_tokens": model_config.max_tokens,
            "top_p": model_config.top_p,
            "top_k": model_config.top_k,
            "presence_penalty": model_config.presence_penalty,
            "frequency_penalty": model_config.frequency_penalty,
            "temperature": model_config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {model_config.api_key}",
        }

        # Make the HTTP request
        response = yield from self.get_http_response(
            method="POST",
            url=model_config.url,
            headers=headers,
            content=json.dumps(payload).encode(),
        )

        # Handle HTTP errors
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Error while pulling the price from Fireworks: {response}"
            )

        # Load the response
        api_data = json.loads(response.body)

        if "error" in api_data:
            self.context.logger.error(
                f"The alternative model returned an error: {api_data}"
            )
            return None

        try:
            tweet = api_data["choices"][0]["message"]["content"]
        except Exception:  # pylint: disable=broad-except
            self.context.logger.error(
                f"The alternative model response is not valid: {api_data}"
            )
            return None

        if not is_tweet_valid(tweet):
            self.context.logger.error("The alternative tweet is too long.")
            return None

        self.context.logger.info(f"Got new tweet from Fireworks API: {tweet}")

        return tweet

    def track_twikit_api_usage(
        self, method: str, **kwargs: Any
    ) -> Generator[None, None, None]:
        """
        Track Twikit API calls and store analytics in KV store.

        Handles both direct API calls and compound operations that make multiple internal API calls.

        Args:
            method: The Twikit API method being called
            kwargs: Arguments passed to the method, used to determine count for compound operations
        """
        # Get current statistics
        twikit_stats = yield from self._get_twikit_stats()

        # Define read vs write operations
        read_operations = {
            "get_user_by_screen_name",
            "get_twitter_user_id",
            "get_user_timeline",
            "search_tweets",
            "get_tweet",
            "get_user_followers",
            "get_user_following",
            "validate_login",
            "get_user_tweets",
            "search",
        }

        write_operations = {
            "post",
            "post_tweet",
            "like_tweet",
            "retweet",
            "follow_user",
            "upload_media",
            "delete_tweet",
        }

        # Track compound operations that make multiple API calls
        compound_operations: Dict[str, Dict[str, Union[str, int]]] = {
            "filter_suspended_users": {
                "base_method": "get_user_by_screen_name",
                "count_param": "user_names",
                "operation_type": "read",
            },
            "get_user_tweets": {
                "base_method": "get_user_by_screen_name",
                "count": 1,
                "operation_type": "read",
            },
            "post": {
                "base_method": "post_tweet",
                "count_param": "tweets",
                "operation_type": "write",
            },
            "search": {
                "base_method": "search_tweets",
                "count": 1,
                "operation_type": "read",
            },
            "validate_login": {
                "base_method": "verify_credentials",
                "count": 1,
                "operation_type": "read",
            },
        }

        # PART 1: Track the direct method call

        # Determine operation type
        if method in read_operations:
            operation_type = "read"
            twikit_stats["read_operations"] += 1
        elif method in write_operations:
            operation_type = "write"
            twikit_stats["write_operations"] += 1
        elif method in compound_operations:
            operation_type = cast(str, compound_operations[method]["operation_type"])
            # For compound operations, we'll count their internal calls separately below
        else:
            operation_type = "other"
            twikit_stats["other_operations"] = (
                twikit_stats.get("other_operations", 0) + 1
            )

        # Increment total calls counter
        twikit_stats["total_calls"] += 1

        # Record the specific method call with timestamp
        if method not in twikit_stats["methods_called"]:
            twikit_stats["methods_called"][method] = {
                "count": 0,
                "type": operation_type,
                "last_called": None,
                "first_called": datetime.utcnow().isoformat(),
            }

        # Update method statistics
        twikit_stats["methods_called"][method]["count"] += 1
        twikit_stats["methods_called"][method][
            "last_called"
        ] = datetime.utcnow().isoformat()

        # PART 2: Track internal calls for compound operations
        if method in compound_operations:
            mapping = compound_operations[method]
            # Use cast to specify the expected type
            base_method: str = cast(str, mapping["base_method"])
            # Explicitly type the variable and use cast
            internal_operation_type: str = cast(str, mapping["operation_type"])

            # Determine number of internal calls
            internal_call_count = 1  # Default to at least one call
            if "count_param" in mapping and cast(str, mapping["count_param"]) in kwargs:
                param_value = kwargs[cast(str, mapping["count_param"])]
                if isinstance(param_value, list):
                    internal_call_count = len(param_value)
            elif "count" in mapping:
                internal_call_count = cast(int, mapping["count"])

            # Update stats for the internal method calls
            if base_method not in twikit_stats["methods_called"]:
                twikit_stats["methods_called"][base_method] = {
                    "count": 0,
                    "type": internal_operation_type,
                    "last_called": None,
                    "first_called": datetime.utcnow().isoformat(),
                }

            # Update counters for internal calls
            twikit_stats["methods_called"][base_method]["count"] += internal_call_count
            twikit_stats["methods_called"][base_method][
                "last_called"
            ] = datetime.utcnow().isoformat()

            # Update operation type counters
            if internal_operation_type == "read":
                twikit_stats["read_operations"] += internal_call_count
            elif internal_operation_type == "write":
                twikit_stats["write_operations"] += internal_call_count
            else:
                twikit_stats["other_operations"] = (
                    twikit_stats.get("other_operations", 0) + internal_call_count
                )

            twikit_stats["total_calls"] += internal_call_count

        # Update timestamp
        twikit_stats["last_updated"] = datetime.utcnow().isoformat()

        # Save updated stats to KV store
        yield from self._write_kv({"twikit_stats": json.dumps(twikit_stats)})

    def _get_twikit_stats(self) -> Generator[None, None, Dict[str, Any]]:
        """Get the Twikit API call statistics from KV store or initialize new stats."""
        db_data = yield from self._read_kv(keys=("twikit_stats",))

        if (
            db_data is None
            or "twikit_stats" not in db_data
            or db_data["twikit_stats"] is None
        ):
            # Initialize new stats dict
            twikit_stats = {
                "read_operations": 0,
                "write_operations": 0,
                "other_operations": 0,
                "total_calls": 0,
                "methods_called": {},
                "first_tracked": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat(),
            }
        else:
            # Load existing stats
            twikit_stats = json.loads(db_data["twikit_stats"])

        return twikit_stats

    def get_twikit_analytics(self) -> Generator[None, None, Dict[str, Any]]:
        """Get analytics for Twikit API usage.

        Returns:
            Dict containing read operations count, write operations count,
            total calls, and a breakdown of calls by method.
        """
        return (yield from self._get_twikit_stats())

    def _sign_mirrordb_request(
        self, endpoint: str, agent_id: int
    ) -> Generator[None, None, Optional[Dict[str, Any]]]:
        """Signs a MirrorDB request based on timestamp and endpoint."""
        try:
            # Ensure agent_id is not None before proceeding
            if agent_id is None:
                self.context.logger.error("Cannot sign request: agent_id is None.")
                return None

            # Generate timestamp and prepare message to sign
            timestamp = int(datetime.utcnow().timestamp())
            message_to_sign = f"timestamp:{timestamp},endpoint:{endpoint}"

            # Use AEA framework signing
            signature_hex = yield from self.get_signature(
                message_to_sign.encode("utf-8")
            )
            if not signature_hex:
                self.context.logger.error(
                    f"Failed to get signature for message: {message_to_sign}"
                )
                return None

            # Prepare authentication data
            auth_data = {
                "agent_id": agent_id,
                "signature": signature_hex,
                "message": message_to_sign,
            }
            self.context.logger.debug(f"Generated auth data for endpoint {endpoint}")
            return auth_data
        except Exception as e:
            self.context.logger.error(
                f"Exception during MirrorDB request signing for {endpoint}: {e}"
            )
            return None

    def _call_mirrordb(
        self, http_method: str, endpoint: str, **kwargs: Any
    ) -> Generator[None, None, Any]:
        """Send a request message to the MirrorDB connection using generic method names."""
        try:
            # Map HTTP verb to connection method name
            connection_method = self._HTTP_METHOD_TO_CONNECTION_METHOD.get(
                http_method.upper()
            )
            if not connection_method:
                self.context.logger.error(
                    f"Unsupported HTTP method for MirrorDB call: {http_method}"
                )
                return None

            # Construct payload for the connection
            # Pass the generic method name and original kwargs (endpoint, data, auth)
            connection_kwargs = {
                "endpoint": endpoint,
                **kwargs,  # Pass through data, auth, etc.
            }

            # Send the generic method name 'read_', 'create_', etc.
            payload_data = {"method": connection_method, "kwargs": connection_kwargs}

            srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
            srr_message, srr_dialogue = srr_dialogues.create(
                counterparty=str(MIRRORDB_CONNECTION_PUBLIC_ID),
                performative=SrrMessage.Performative.REQUEST,
                payload=json.dumps(payload_data),
            )
            srr_message = cast(SrrMessage, srr_message)
            srr_dialogue = cast(SrrDialogue, srr_dialogue)
            response = yield from self._do_connection_request(srr_message, srr_dialogue)  # type: ignore

            response_json = json.loads(response.payload)  # type: ignore

            if "error" in response_json:
                error_message = response_json["error"]
                # Check if the error is a 404 Not Found, which is expected during registration checks
                is_404 = (
                    isinstance(error_message, str) and "Status 404" in error_message
                )
                if is_404:
                    # Log expected 404s less severely
                    self.context.logger.info(
                        f"Resource not found ({http_method} {endpoint} -> {connection_method}): Expected 404."
                    )
                else:
                    # Log other errors as actual errors
                    self.context.logger.error(
                        f"MirrorDB call ({http_method} {endpoint} -> {connection_method}) failed: {error_message}"
                    )
                return None

            return response_json.get("response")  # type: ignore
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                # Log based on the original HTTP method for clarity
                f"Exception while calling MirrorDB ({http_method} {endpoint} -> {connection_method}): {e}"
            )
            return None

    def _register_with_mirror_db(self) -> Generator[None, None, None]:
        """Register with the MirrorDB service and save the configuration."""
        try:
            # 1. Get Twitter User Data (unchanged)
            twitter_user_data = yield from self._get_twitter_user_data()
            if not twitter_user_data:
                self.context.logger.error(
                    "Failed to get Twitter user data. Registration with MirrorDB aborted."
                )
                return

            twitter_user_id = twitter_user_data.get("id")
            twitter_username = twitter_user_data.get("screen_name")
            twitter_name = twitter_user_data.get("name")

            if not all([twitter_user_id, twitter_username, twitter_name]):
                self.context.logger.error(
                    f"Missing required Twitter data: id={twitter_user_id}, username={twitter_username}, name={twitter_name}"
                )
                return

            # 2. (New) Get Agent Type ID (Assuming type name 'memeooorr')
            agent_type_name = "memeooorr"  # TODO: Make this configurable if needed
            agent_type_response = yield from self._call_mirrordb(
                "GET", endpoint=f"/api/agent-types/name/{agent_type_name}"
            )

            # --- Create Agent Type if it doesn't exist ---
            if agent_type_response is None:
                self.context.logger.info(
                    f"Agent type '{agent_type_name}' not found. Creating..."
                )
                agent_type_create_data = {
                    "type_name": agent_type_name,
                    "description": "Agent type for Memeooorr skill",
                }
                # Agent type creation seems unauthenticated per spec
                agent_type_response = yield from self._call_mirrordb(
                    "POST", endpoint="/api/agent-types/", data=agent_type_create_data
                )
                if agent_type_response is None:
                    self.context.logger.error(
                        f"Failed to create agent type '{agent_type_name}'. Aborting registration."
                    )
                    return
                self.context.logger.info(f"Created agent type: {agent_type_response}")
            # -----------------------------------------------

            if "type_id" not in agent_type_response:
                self.context.logger.error(
                    f"Could not find or create agent type '{agent_type_name}'. Response: {agent_type_response}"
                )
                return

            agent_type_id = agent_type_response["type_id"]
            self.context.logger.info(
                f"Using agent type '{agent_type_name}' with type_id: {agent_type_id}"
            )

            # 3. Create Agent Registry Entry
            agent_registry_data = {
                "agent_name": f"{self.synchronized_data.safe_contract_address}_{datetime.utcnow().isoformat()}",
                "type_id": agent_type_id,
                "eth_address": self.context.agent_address,  # Use agent's eth address
            }
            # --- Signing --- (ASSUMPTION: create_agent_registry does NOT require signing)
            # No signature needed for this initial creation step based on assumption.
            # auth_data_agent = None

            # --- Call ---
            # Pass only the data payload for registry creation
            agent_registry_response = yield from self._call_mirrordb(
                "POST",
                endpoint="/api/agent-registry/",
                data=agent_registry_data,
                # auth=auth_data_agent # Not passing auth based on assumption
            )
            self.context.logger.info(
                f"Agent registry entry created: {agent_registry_response}"
            )

            if (
                agent_registry_response is None
                or "agent_id" not in agent_registry_response
            ):
                self.context.logger.error(
                    "Failed to create agent registry entry or get agent_id."
                )
                return
            agent_id = agent_registry_response["agent_id"]

            # Note: API key handling is removed as per new API structure assumptions.
            # Authentication might be handled differently (e.g., signatures by the connection).
            # The old `create_agent` response included an api_key. The new one doesn't.
            # We will store the agent_id and twitter_user_id, but not an API key unless proven necessary.

            # 5. Save configuration (agent_id, twitter_user_id) locally (KV store)
            # API key is no longer part of the primary config needed from registration.
            config_data = {
                "agent_id": agent_id,
                "twitter_user_id": twitter_user_id,
            }
            self.context.logger.info(f"Saving MirrorDB config data: {config_data}")
            yield from self._write_kv({"mirrod_db_config": json.dumps(config_data)})

            # 6. (New) Get or create Attribute Definition for Interactions
            interaction_attr_def_name = "twitter_interactions"
            interaction_attr_def_response = yield from self._call_mirrordb(
                "GET", endpoint=f"/api/attributes/name/{interaction_attr_def_name}"
            )

            # --- Create Interaction Attribute Definition if it doesn't exist ---
            interaction_attr_def_id = None  # Initialize
            if interaction_attr_def_response is None:
                self.context.logger.info(
                    f"Attribute definition '{interaction_attr_def_name}' not found. Creating..."
                )
                interaction_attr_def_payload = {
                    "type_id": agent_type_id,
                    "attr_name": interaction_attr_def_name,
                    "data_type": "json",  # Assuming JSON to store interaction details
                    "is_required": False,
                    "default_value": "{}",
                }
                interaction_attr_def_endpoint = (
                    f"/api/agent-types/{agent_type_id}/attributes/"
                )

                # --- Signing required ---
                auth_data_inter_attr_def = yield from self._sign_mirrordb_request(
                    interaction_attr_def_endpoint, agent_id
                )
                if auth_data_inter_attr_def is None:
                    self.context.logger.error(
                        f"Failed to sign attribute definition creation request for '{interaction_attr_def_name}'. Aborting."
                    )
                else:
                    # --- Call ---
                    request_body_inter = {
                        "attr_def": interaction_attr_def_payload,
                        "auth": auth_data_inter_attr_def,
                    }
                    interaction_attr_def_response = yield from self._call_mirrordb(
                        "POST",
                        endpoint=interaction_attr_def_endpoint,
                        data=request_body_inter,
                    )
                    if interaction_attr_def_response is None:
                        self.context.logger.error(
                            f"Failed to create attribute definition '{interaction_attr_def_name}'."
                        )
                    # Re-assign response for ID extraction below

            # Extract ID if creation was successful or if it existed
            if (
                interaction_attr_def_response
                and "attr_def_id" in interaction_attr_def_response
            ):
                interaction_attr_def_id = interaction_attr_def_response["attr_def_id"]
                self.context.logger.info(
                    f"Using attribute definition '{interaction_attr_def_name}' with attr_def_id: {interaction_attr_def_id}"
                )
                # Store ID in KV Store
                success = yield from self._write_kv(
                    {"twitter_interactions_attr_def_id": str(interaction_attr_def_id)}
                )
                if success:
                    self.context.logger.info(
                        f"Stored twitter_interactions_attr_def_id={interaction_attr_def_id} in KV Store."
                    )
                else:
                    self.context.logger.error(
                        f"Failed to store twitter_interactions_attr_def_id={interaction_attr_def_id} in KV Store."
                    )
            else:
                self.context.logger.error(
                    f"Could not find or create attribute definition '{interaction_attr_def_name}'. Response: {interaction_attr_def_response}"
                )
                # Decide if registration should fail if interaction tracking is critical

            # 7. (New) Get or create Attribute Definition for Username
            # Store Agent Type ID in KV store for later use
            if agent_type_id:
                success_type_id = yield from self._write_kv(
                    {"memeooorr_agent_type_id": str(agent_type_id)}
                )
                if success_type_id:
                    self.context.logger.info(
                        f"Stored memeooorr_agent_type_id={agent_type_id} in KV Store."
                    )
                else:
                    self.context.logger.error(
                        f"Failed to store memeooorr_agent_type_id={agent_type_id} in KV Store."
                    )

            username_attr_def_name = "twitter_username"
            username_attr_def_response = yield from self._call_mirrordb(
                "GET", endpoint=f"/api/attributes/name/{username_attr_def_name}"
            )

            # --- Create Username Attribute Definition if it doesn't exist ---
            username_attr_def_id = None  # Initialize
            if username_attr_def_response is None:
                self.context.logger.info(
                    f"Attribute definition '{username_attr_def_name}' not found. Creating..."
                )
                username_attr_def_payload = {
                    "type_id": agent_type_id,
                    "attr_name": username_attr_def_name,
                    "data_type": "string",
                    "is_required": True,  # Username should be required for identification
                    "default_value": "",
                }
                username_attr_def_endpoint = (
                    f"/api/agent-types/{agent_type_id}/attributes/"
                )

                # --- Signing required ---
                auth_data_user_attr_def = yield from self._sign_mirrordb_request(
                    username_attr_def_endpoint, agent_id
                )
                if auth_data_user_attr_def is None:
                    self.context.logger.error(
                        f"Failed to sign attribute definition creation request for '{username_attr_def_name}'. Aborting."
                    )
                else:
                    # --- Call ---
                    request_body_user = {
                        "attr_def": username_attr_def_payload,
                        "auth": auth_data_user_attr_def,
                    }
                    username_attr_def_response = yield from self._call_mirrordb(
                        "POST",
                        endpoint=username_attr_def_endpoint,
                        data=request_body_user,
                    )
                    if username_attr_def_response is None:
                        self.context.logger.error(
                            f"Failed to create attribute definition '{username_attr_def_name}'."
                        )

            # Extract ID
            if (
                username_attr_def_response
                and "attr_def_id" in username_attr_def_response
            ):
                username_attr_def_id = username_attr_def_response["attr_def_id"]
                self.context.logger.info(
                    f"Using attribute definition '{username_attr_def_name}' with attr_def_id: {username_attr_def_id}"
                )
                # Store ID in KV Store
                success = yield from self._write_kv(
                    {"twitter_username_attr_def_id": str(username_attr_def_id)}
                )
                if success:
                    self.context.logger.info(
                        f"Stored twitter_username_attr_def_id={username_attr_def_id} in KV Store."
                    )
                else:
                    self.context.logger.error(
                        f"Failed to store twitter_username_attr_def_id={username_attr_def_id} in KV Store."
                    )
            else:
                self.context.logger.error(
                    f"Could not find or create attribute definition '{username_attr_def_name}'. Response: {username_attr_def_response}"
                )
                # Username attribute is likely crucial, consider aborting registration
                return  # Abort if we can't get/create the username attribute def

            # 8. (New) Create Username Attribute Instance for this agent
            if username_attr_def_id is not None and twitter_username is not None:
                username_attr_instance_payload = {
                    "agent_id": agent_id,
                    "attr_def_id": username_attr_def_id,
                    "string_value": twitter_username,
                    # Other value types are None
                    "integer_value": None,
                    "float_value": None,
                    "boolean_value": None,
                    "date_value": None,
                    "json_value": None,
                }
                username_attr_instance_endpoint = f"/api/agents/{agent_id}/attributes/"

                # --- Signing required ---
                auth_data_user_attr_instance = yield from self._sign_mirrordb_request(
                    username_attr_instance_endpoint, agent_id
                )
                if auth_data_user_attr_instance is None:
                    self.context.logger.error(
                        f"Failed to sign attribute instance creation request for '{username_attr_def_name}'."
                    )
                else:
                    # --- Call ---
                    request_body_user_instance = {
                        "agent_attr": username_attr_instance_payload,
                        "auth": auth_data_user_attr_instance,
                    }
                    username_attr_instance_response = yield from self._call_mirrordb(
                        "POST",
                        endpoint=username_attr_instance_endpoint,
                        data=request_body_user_instance,
                    )
                    if username_attr_instance_response is None:
                        self.context.logger.error(
                            f"Failed to create attribute instance for '{username_attr_def_name}' for agent {agent_id}."
                        )
                    else:
                        self.context.logger.info(
                            f"Successfully created attribute instance for '{username_attr_def_name}' for agent {agent_id}."
                        )
            else:
                self.context.logger.error(
                    f"Cannot create username attribute instance: missing attr_def_id ({username_attr_def_id}) or twitter_username ({twitter_username})."
                )

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Exception while registering with MirrorDB: {e}")
