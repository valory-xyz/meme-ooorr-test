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
        response_message = cast(
            SrrMessage,
            dialogue.reply(  # type: ignore
                performative=SrrMessage.Performative.RESPONSE,
                target_message=srr_message,
                payload=json.dumps({"error": error}),
                error=True,
            ),
        )
        return response_message

    def _handle_done_task(self, task: asyncio.Future) -> None:
        """Process a done receiving task."""
        request = self.task_to_request.pop(task)
        response_message: Optional[Message] = task.result()

        response_envelope = None
        if response_message is not None:
            response_envelope = Envelope(
                to=request.sender,
                sender=request.to,
                message=response_message,
                context=request.context,
            )

        self.response_envelopes.put_nowait(response_envelope)

    # Allowed methods are now the generic ones
    _ALLOWED_METHODS = {
        "create_",
        "read_",
        "update_",
        "delete_",
    }

    # Map generic method names to HTTP verbs
    _METHOD_TO_VERB = {
        "create_": "POST",
        "read_": "GET",
        "update_": "PUT",
        "delete_": "DELETE",
    }

    @retry_with_exponential_backoff()
    async def _make_request(
        self, http_verb: str, url: str, headers: Dict, json_data: Optional[Dict]
    ) -> Tuple[int, bytes]:
        """Makes an HTTP request and handles the response.
        Returns status code and raw body bytes.
        Raises ClientResponseError on 4xx/5xx.
        """
        if self.session is None:
            raise ConnectionError("aiohttp session is not initialized.")

        # Clearer logging for potentially sensitive data (optional)
        log_data = "<data provided>" if json_data else "None"
        self.logger.info(
            f"Making {http_verb} request to {url} with headers: {headers} Data: {log_data}"
        )

        async with self.session.request(
            method=http_verb,
            url=url,
            headers=headers,
            json=json_data,
            # ssl=self.ssl_context # TCPConnector handles SSL
        ) as response:
            # Use raise_for_status() for basic HTTP error checking (4xx, 5xx)
            response.raise_for_status()
            # If successful (2xx), return status code and raw body bytes
            return response.status, await response.read()
            # Other errors like connection errors are handled by the retry decorator

    async def _get_response(self, message: Message, dialogue: Dialogue) -> SrrMessage:
        """Get response from the backend service."""
        request_nonce = dialogue.dialogue_label.dialogue_reference[0]
        response_payload: Optional[Dict] = None
        response_error: Optional[str] = None

        try:
            payload = json.loads(message.payload)
            # Extract the HTTP method and endpoint, passed from the skill
            http_method = payload.get(
                "method", "GET"
            ).upper()  # Default to GET if not provided
            kwargs = payload.get("kwargs", {})
            endpoint = kwargs.get("endpoint")
            # The 'data' kwarg now contains the *full* pre-constructed request body
            json_body = kwargs.get("data")

            self.logger.info(
                f"Received request: Method={http_method}, Endpoint={endpoint}, Body provided: {json_body is not None}"
            )

            if not endpoint:
                raise ValueError("Request received without an endpoint.")

            # Construct full URL and headers
            url = f"{self.base_url}{endpoint}"
            headers = DEFAULT_HEADERS.copy()

            # Make the request using positional args for http_method and url
            status_code, response_bytes = await self._make_request(
                http_method,  # Corresponds to http_verb
                url,  # Corresponds to url
                headers=headers,
                json_data=json_body,  # Pass the pre-constructed body
                # Removed internal state management for auth
            )

            # Process response based on status code
            if 200 <= status_code < 300:
                # Success path
                try:
                    if response_bytes:  # Check if body is not empty
                        response_payload = json.loads(response_bytes.decode())
                    else:  # Handle empty success body (e.g., 204)
                        response_payload = {
                            "status_code": status_code,
                            "message": "Success (No Content)",
                        }
                except json.JSONDecodeError:
                    # Success status but body is not valid JSON
                    self.logger.warning(
                        f"Request to {url} succeeded ({status_code}) but response body is not valid JSON: {response_bytes[:200]}..."
                    )
                    response_payload = {
                        "status_code": status_code,
                        "message": "Success (Invalid JSON Body)",
                        "body_preview": response_bytes.decode(errors="ignore")[:200],
                    }
            else:
                # This part should ideally not be reached if raise_for_status works
                # But as a fallback, handle non-2xx status here
                response_payload = None  # Indicate failure
                response_error = f"Received unexpected non-2xx status: {status_code}"
                self.logger.error(
                    f"{response_error} for {url}. Body: {response_bytes.decode(errors='ignore')[:500]}..."
                )

        except json.JSONDecodeError as e:
            response_error = f"Invalid JSON payload received: {e}"
            self.logger.error(response_error)
        except ValueError as e:
            response_error = f"Value error processing request: {e}"
            self.logger.error(response_error)
        except aiohttp.ClientResponseError as e:  # Specific HTTP error handling
            self.logger.error(
                f"Caught ClientResponseError: Status={e.status}, Message={e.message}, Headers={e.headers}"
            )
            # Try to get more details from the error response body
            error_body_text = ""
            try:
                error_body_bytes = await e.read()
                error_body_text = f", Body: {error_body_bytes.decode(errors='ignore')[:500]}..."  # Decode safely
            except Exception as body_err:
                error_body_text = f", Body: <failed to read: {body_err}>"
            response_error = f"HTTP Error: Status {e.status}, Message: {e.message or '[No Message]'}, Headers: {e.headers}{error_body_text}"  # Ensure non-empty message
            self.logger.error(f"Request to {url} failed: {response_error}")
        except Exception as e:  # Catch-all
            response_error = f"An unexpected error occurred: {e}"
            self.logger.exception(
                response_error
            )  # Log full traceback for unexpected errors

        # Construct and send response message
        response_kwargs = {"performative": SrrMessage.Performative.RESPONSE}
        if response_payload:
            response_kwargs["payload"] = json.dumps({"response": response_payload})
        else:
            response_kwargs["payload"] = json.dumps(
                {"error": response_error or "Unknown error"}
            )

        return dialogue.reply(**response_kwargs)
