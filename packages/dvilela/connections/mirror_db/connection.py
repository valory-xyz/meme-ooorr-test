#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2024 David Vilela Freire
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

"""MirrorDB connection."""

import asyncio
import json
import re
import ssl
from functools import wraps
from typing import Any, Dict, List, Optional, Union, cast, Tuple

import aiohttp
import certifi
from aea.configurations.base import PublicId
from aea.connections.base import Connection, ConnectionStates
from aea.mail.base import Envelope
from aea.protocols.base import Address, Message
from aea.protocols.dialogue.base import Dialogue
from aea.protocols.dialogue.base import Dialogue as BaseDialogue

from packages.valory.protocols.srr.dialogues import SrrDialogue
from packages.valory.protocols.srr.dialogues import SrrDialogues as BaseSrrDialogues
from packages.valory.protocols.srr.message import SrrMessage


PUBLIC_ID = PublicId.from_str("dvilela/mirror_db:0.1.0")

# Default headers for JSON requests
DEFAULT_HEADERS = {"Content-Type": "application/json", "accept": "application/json"}


def retry_with_exponential_backoff(max_retries=5, initial_delay=1, backoff_factor=2):  # type: ignore
    """Retry a function with exponential backoff."""

    def decorator(func):  # type: ignore
        @wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore
            connection_instance = args[
                0
            ]  # Assuming the first arg is self (the connection instance)
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except aiohttp.ClientResponseError as e:
                    # Check if the error is rate limiting (e.g., status code 429)
                    # You might need to adjust the status code based on the API
                    if e.status == 429:
                        if attempt < max_retries - 1:
                            connection_instance.logger.warning(
                                f"Rate limit exceeded. Retrying in {delay} seconds..."
                            )
                            await asyncio.sleep(delay)
                            delay *= backoff_factor
                        else:
                            connection_instance.logger.error(
                                "Max retries reached for rate limiting. Could not complete the request."
                            )
                            raise
                    else:
                        # Re-raise other client errors immediately
                        raise
                except aiohttp.ClientConnectionError as e:
                    # Handle connection errors (e.g., DNS resolution, connection refused)
                    if attempt < max_retries - 1:
                        connection_instance.logger.warning(
                            f"Connection error: {e}. Retrying in {delay} seconds..."
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        connection_instance.logger.error(
                            "Max retries reached for connection error. Could not complete the request."
                        )
                        raise
                except Exception as e:
                    # Handle other potential exceptions during the request
                    connection_instance.logger.error(
                        f"An unexpected error occurred: {e}"
                    )
                    raise  # Re-raise unexpected errors

        return wrapper

    return decorator


class SrrDialogues(BaseSrrDialogues):
    """A class to keep track of SRR dialogues."""

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize dialogues.

        :param kwargs: keyword arguments
        """

        def role_from_first_message(  # pylint: disable=unused-argument
            message: Message, receiver_address: Address
        ) -> Dialogue.Role:
            """Infer the role of the agent from an incoming/outgoing first message

            :param message: an incoming/outgoing first message
            :param receiver_address: the address of the receiving agent
            :return: The role of the agent
            """
            return SrrDialogue.Role.CONNECTION

        BaseSrrDialogues.__init__(
            self,
            self_address=str(kwargs.pop("connection_id")),
            role_from_first_message=role_from_first_message,
            **kwargs,
        )


class MirrorDBConnection(Connection):
    """Proxy to the functionality of the mirror DB backend service."""

    connection_id = PUBLIC_ID

    # List of allowed methods that can be called via the SRR protocol
    _ALLOWED_METHODS = {
        "create_",
        "read_",
        "update_",
        "delete_",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the connection."""
        super().__init__(*args, **kwargs)
        self.base_url = self.configuration.config.get("mirror_db_base_url")
        self.session: Optional[aiohttp.ClientSession] = None
        self.dialogues = SrrDialogues(connection_id=PUBLIC_ID)
        self._response_envelopes: Optional[asyncio.Queue] = None
        self.task_to_request: Dict[asyncio.Future, Envelope] = {}
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    @property
    def response_envelopes(self) -> asyncio.Queue:
        """Returns the response envelopes queue."""
        if self._response_envelopes is None:
            raise ValueError(
                "`MirrorDBConnection.response_envelopes` is not yet initialized. Is the connection setup?"
            )
        return self._response_envelopes

    async def connect(self) -> None:
        """Connect to the backend service."""
        self._response_envelopes = asyncio.Queue()
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=self.ssl_context)
        )
        self.state = ConnectionStates.connected

    async def disconnect(self) -> None:
        """Disconnect from the backend service."""
        if self.is_disconnected:
            return

        self.state = ConnectionStates.disconnecting

        for task in self.task_to_request.keys():
            if not task.cancelled():
                task.cancel()
        self._response_envelopes = None

        if self.session is not None:
            await self.session.close()
            self.session = None

        self.state = ConnectionStates.disconnected

    async def receive(
        self, *args: Any, **kwargs: Any
    ) -> Optional[Union["Envelope", None]]:
        """Receive an envelope."""
        return await self.response_envelopes.get()

    async def send(self, envelope: Envelope) -> None:
        """Send an envelope."""
        task = self._handle_envelope(envelope)
        task.add_done_callback(self._handle_done_task)
        self.task_to_request[task] = envelope

    def _handle_envelope(self, envelope: Envelope) -> asyncio.Task:
        """Handle incoming envelopes by dispatching background tasks."""
        message = cast(SrrMessage, envelope.message)
        dialogue = self.dialogues.update(message)
        task = self.loop.create_task(self._get_response(message, dialogue))
        return task

    def prepare_error_message(
        self, srr_message: SrrMessage, dialogue: Optional[BaseDialogue], error: str
    ) -> SrrMessage:
        """Prepare error message"""
        self.logger.error(f"Preparing error response: {error}")
        # Use dialogue directly if BaseDialogue, otherwise find based on message if needed
        if not isinstance(dialogue, BaseDialogue):
            dialogue = self.dialogues.get_dialogue(srr_message)
            if dialogue is None:
                self.logger.error(
                    f"Cannot reply: dialogue not found for message {srr_message}"
                )
                raise ValueError(f"Dialogue not found for message {srr_message}")

        response_message = cast(
            SrrMessage,
            dialogue.reply(  # No longer Optional
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps({"error": error}),
                # error=True, # 'error' is not a valid kwarg for SrrMessage RESPONSE
            ),
        )
        return response_message

    def _handle_done_task(self, task: asyncio.Future) -> None:
        """Process a done receiving task."""
        request = self.task_to_request.pop(task)
        response_message: Optional[Message] = None
        try:
            response_message = task.result()
        except Exception as e:
            self.logger.error(f"Task failed with exception: {e}")

        if response_message is None:
            self.logger.warning(f"No response message generated for request: {request}")
            return

        response_envelope = Envelope(
            to=request.sender,
            sender=request.to,
            message=response_message,
            context=request.context,
        )
        self.response_envelopes.put_nowait(response_envelope)

    # New _get_response using getattr pattern
    async def _get_response(
        self, srr_message: SrrMessage, dialogue: Optional[BaseDialogue]
    ) -> SrrMessage:
        """Get response from the backend service by dispatching to internal methods."""
        self.logger.info(f"in get_response")
        if srr_message.performative != SrrMessage.Performative.REQUEST:
            return self.prepare_error_message(
                srr_message,
                dialogue,
                f"Performative `{srr_message.performative.value}` is not supported.",
            )

        try:
            payload = json.loads(srr_message.payload)
            method_name = payload.get("method")
            kwargs = payload.get("kwargs", {})

            if method_name not in self._ALLOWED_METHODS:
                return self.prepare_error_message(
                    srr_message,
                    dialogue,
                    f"Method '{method_name}' is not allowed or not provided.",
                )

            method_to_call = getattr(self, method_name, None)

            if method_to_call is None or not callable(method_to_call):
                return self.prepare_error_message(
                    srr_message,
                    dialogue,
                    f"Internal connection error: Method '{method_name}' not found or not callable.",
                )

            # Optional endpoint validation (using regex) - Adapt if needed
            endpoint = kwargs.get("endpoint")
            if endpoint is None:
                # Allow missing endpoint for methods that might not need it?
                # For now, assume create_, read_, update_, delete_ always need it.
                # Modify if specific internal methods don't require an endpoint.
                if method_name in ["create_", "read_", "update_", "delete_"]:
                    return self.prepare_error_message(
                        srr_message, dialogue, "Missing endpoint in request kwargs."
                    )

            # Call the internal method (e.g., self.create_(**kwargs))
            # The kwargs passed include endpoint, data, auth etc.
            response_data = await method_to_call(**kwargs)

            response_message = cast(
                SrrMessage,
                dialogue.reply(  # type: ignore
                    performative=SrrMessage.Performative.RESPONSE,
                    target_message=srr_message,
                    payload=json.dumps({"response": response_data}),
                ),
            )
            self.logger.info(f"before return of get_response")
            return response_message

        except json.JSONDecodeError as e:
            return self.prepare_error_message(
                srr_message, dialogue, f"Invalid JSON payload received: {e}"
            )
        except Exception as e:
            self.logger.error(
                f"Exception while calling backend service via method {method_name}: {e}"
            )
            return self.prepare_error_message(
                srr_message, dialogue, f"Exception processing request: {e}"
            )

    async def _raise_for_response(
        self, response: aiohttp.ClientResponse, action: str
    ) -> None:
        """Raise exception with relevant message based on the HTTP status code."""
        if response.status == 200:
            return
        error_content = await response.json()
        detail = error_content.get("detail", error_content)
        raise Exception(f"Error {action}: {detail} (HTTP {response.status})")

    # --- Internal API call methods ---

    @retry_with_exponential_backoff()  # Apply retry here
    async def create_(self, endpoint: str, data: Dict, **kwargs) -> Dict:
        """Create a resource using a POST request."""
        if self.session is None:
            raise ConnectionError("Session not initialized.")
        url = f"{self.base_url}{endpoint}"
        json_body = data  # Use the data kwarg directly as the body
        self.logger.info(
            f"Making POST request to {url} Data: {'<data provided>' if json_body else 'None'}"
        )
        async with self.session.post(
            url, json=json_body, headers=DEFAULT_HEADERS
        ) as response:
            await self._raise_for_response(response, f"creating resource at {endpoint}")
            if response.status == 204:
                return {"status_code": 204, "message": "Created (No Content)"}
            return await response.json()

    @retry_with_exponential_backoff()
    async def read_(self, endpoint: str, **kwargs) -> Dict:
        """Read a resource using a GET request."""
        if self.session is None:
            raise ConnectionError("Session not initialized.")
        url = f"{self.base_url}{endpoint}"
        self.logger.info(f"Making GET request to {url}")
        async with self.session.get(url, headers=DEFAULT_HEADERS) as response:
            await self._raise_for_response(response, f"reading resource at {endpoint}")
            if response.status == 204:
                return {"status_code": 204, "message": "Success (No Content)"}
            return await response.json()

    @retry_with_exponential_backoff()
    async def update_(self, endpoint: str, data: Dict, **kwargs) -> Dict:
        """Update a resource using a PUT request."""
        if self.session is None:
            raise ConnectionError("Session not initialized.")
        url = f"{self.base_url}{endpoint}"
        json_body = data  # Use the data kwarg directly as the body
        self.logger.info(
            f"Making PUT request to {url} Data: {'<data provided>' if json_body else 'None'}"
        )
        async with self.session.put(
            url, json=json_body, headers=DEFAULT_HEADERS
        ) as response:
            await self._raise_for_response(response, f"updating resource at {endpoint}")
            if response.status == 204:
                return {"status_code": 204, "message": "Updated (No Content)"}
            return await response.json()

    @retry_with_exponential_backoff()
    async def delete_(self, endpoint: str, **kwargs) -> Dict:
        """Delete a resource using a DELETE request."""
        if self.session is None:
            raise ConnectionError("Session not initialized.")
        url = f"{self.base_url}{endpoint}"
        self.logger.info(f"Making DELETE request to {url}")
        async with self.session.delete(url, headers=DEFAULT_HEADERS) as response:
            await self._raise_for_response(response, f"deleting resource at {endpoint}")
            if response.status == 204:
                return {"status_code": 204, "message": "Deleted (No Content)"}
            try:
                return await response.json()
            except (
                json.JSONDecodeError
            ):  # Handle if DELETE returns 200 OK but no JSON body
                return {
                    "status_code": response.status,
                    "message": "Deleted (No JSON Body)",
                }
