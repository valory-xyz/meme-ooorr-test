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
from copy import copy
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple, cast

from aea.protocols.base import Message

from packages.dvilela.connections.genai.connection import (
    PUBLIC_ID as GENAI_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.kv_store.connection import (
    PUBLIC_ID as KV_STORE_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.connections.twikit.connection import (
    PUBLIC_ID as TWIKIT_CONNECTION_PUBLIC_ID,
)
from packages.dvilela.contracts.meme.contract import MemeContract
from packages.dvilela.contracts.meme_factory.contract import MemeFactoryContract
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
AVAILABLE_ACTIONS = ["heart", "unleash", "collect", "purge", "burn"]
MEMEOOORR_DESCRIPTION_PATTERN = r"^Memeooorr (@\w+)$"


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


class MemeooorrBaseBehaviour(BaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
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

    def _call_twikit(self, method: str, **kwargs: Any) -> Generator[None, None, Any]:
        """Send a request message from the skill context."""
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

        return response_json["response"]  # type: ignore

    def _call_genai(
        self,
        prompt: str,
    ) -> Generator[None, None, Optional[str]]:
        """Send a request message from the skill context."""
        srr_dialogues = cast(SrrDialogues, self.context.srr_dialogues)
        srr_message, srr_dialogue = srr_dialogues.create(
            counterparty=str(GENAI_CONNECTION_PUBLIC_ID),
            performative=SrrMessage.Performative.REQUEST,
            payload=json.dumps({"prompt": prompt}),
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

    def get_persona(self) -> str:
        """Get the agent persona"""
        return self.synchronized_data.persona or self.params.persona

    def get_native_balance(self) -> Generator[None, None, Optional[float]]:
        """Get the native balance"""
        self.context.logger.info(
            f"Getting native balance for Safe {self.synchronized_data.safe_contract_address}"
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
            return None

        balance = cast(float, ledger_api_response.state.body["get_balance_result"])
        balance = balance / 10**18  # from wei

        self.context.logger.error(f"Got native balance: {balance}")

        return balance

    def get_meme_available_actions(
        self, meme_address: str, hearted_memes: List[str]
    ) -> Generator[None, None, Optional[List]]:
        """Get the available actions"""

        # Use the contract api to interact with the factory contract
        response_msg = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_address=self.params.meme_factory_address,
            contract_id=str(MemeFactoryContract.contract_id),
            contract_callable="get_summon_data",
            meme_address=meme_address,
            chain_id=self.get_chain_id(),
        )

        # Check that the response is what we expect
        if response_msg.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"Could not get the memecoin summon data: {response_msg}"
            )
            return None

        # Extract the data
        summon_time_ts = cast(int, response_msg.state.body.get("summon_time", 0))
        unleash_time_ts = cast(int, response_msg.state.body.get("unleash_time", 0))

        self.context.logger.info(
            f"Token {meme_address} summon_time_ts={summon_time_ts} unleash_time_ts={unleash_time_ts}"
        )

        # Get the times
        now = datetime.fromtimestamp(self.get_sync_timestamp())
        summon_time = datetime.fromtimestamp(summon_time_ts)
        seconds_since_summon = (now - summon_time).total_seconds()

        available_actions = copy(AVAILABLE_ACTIONS)

        is_unleashed = unleash_time_ts != 0

        # We can unleash if it has not been unleashed
        if is_unleashed:
            available_actions.remove("unleash")

        # We can heart during the first 48h
        if is_unleashed or seconds_since_summon > 48 * 3600:
            available_actions.remove("heart")

        # We use 47.5 to be on the safe side
        if seconds_since_summon < 47.5 * 3600:
            if "unleash" in available_actions:
                available_actions.remove("unleash")
            available_actions.remove("purge")
            available_actions.remove("burn")

            # We can collect if we have hearted this token
            if meme_address not in hearted_memes:
                available_actions.remove("collect")

        return available_actions

    def get_extra_meme_info(self, meme_coins: List) -> Generator[None, None, List]:
        """Get the meme coin names, symbols and other info"""

        enriched_meme_coins = []

        for meme_coin in meme_coins:
            response_msg = yield from self.get_contract_api_response(
                performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
                contract_address=meme_coin["token_address"],
                contract_id=str(MemeContract.contract_id),
                contract_callable="get_token_data",
                chain_id=self.get_chain_id(),
            )

            # Check that the response is what we expect
            if response_msg.performative != ContractApiMessage.Performative.STATE:
                self.context.logger.error(
                    f"Error while getting the token data: {response_msg}"
                )
                continue

            meme_coin["token_name"] = response_msg.state.body.get("name")
            meme_coin["token_ticker"] = response_msg.state.body.get("symbol")
            meme_coin["token_supply"] = response_msg.state.body.get("total_supply")
            meme_coin["decimals"] = response_msg.state.body.get("decimals")

            # Load previously hearted memes
            db_data = yield from self._read_kv(keys=("hearted_memes",))

            if db_data is None:
                self.context.logger.error("Error while loading the database")
                hearted_memes: List[str] = []
            else:
                hearted_memes = db_data["hearted_memes"] or []

            # Get available actions
            available_actions = yield from self.get_meme_available_actions(
                meme_coin["token_address"], hearted_memes
            )
            meme_coin["available_actions"] = available_actions

            enriched_meme_coins.append(meme_coin)

        return enriched_meme_coins

    def get_meme_coins_from_subgraph(self) -> Generator[None, None, Optional[List]]:
        """Get a list of meme coins"""

        url = "https://agentsfun-indexer-production-6ab5.up.railway.app"

        query = {"query": TOKENS_QUERY}

        headers = {"Content-Type": "application/json"}

        # Make the HTTP request
        response = yield from self.get_http_response(
            method="POST", url=url, content=json.dumps(query).encode(), headers=headers
        )

        # Handle HTTP errors
        if response.status_code != HTTP_OK:
            self.context.logger.error(
                f"Error while pulling the memes from subgraph: {response.body!r}"
            )
            return []

        # Load the response
        response_json = json.loads(response.body)
        meme_coins = [
            {
                "token_address": t["id"],
                "liquidity": int(t["liquidity"]),
                "heart_count": int(t["heartCount"]),
                "is_unleashed": t["isUnleashed"],
                "timestamp": t["timestamp"],
            }
            for t in response_json["data"]["memeTokens"]["items"]
            if t["chain"] == "base"  # TODO: adapt to Celo
        ]

        enriched_meme_coins = yield from self.get_extra_meme_info(meme_coins)

        self.context.logger.info(f"Got {len(enriched_meme_coins)} tokens")

        return enriched_meme_coins

    def get_chain_id(self) -> str:
        """Get chain id"""
        return BASE_CHAIN_ID if self.params.home_chain_id == "BASE" else CELO_CHAIN_ID

    def get_packages(self, package_type: str) -> Generator[None, None, Optional[Dict]]:
        """Gets minted packages from the Olas subgraph"""

        self.context.logger.info("Getting packages from Olas subgraph...")

        SUBGRAPH_URL = "https://subgraph.autonolas.tech/subgraphs/name/autonolas"

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

    def get_memeooorr_handles(self) -> Generator[None, None, List[str]]:
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
            if handle != self.params.twitter_username:
                continue

            handles.append(handle)
        return handles
