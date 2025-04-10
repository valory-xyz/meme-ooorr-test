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
import base64
import json
import os
import tempfile
import traceback
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Type

import requests

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.payloads import MechPayload
from packages.dvilela.skills.memeooorr_abci.rounds import (
    FailedMechRequestRound,
    FailedMechResponseRound,
    PostMechResponseRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.io_.store import SupportedFiletype
from packages.valory.skills.mech_interact_abci.states.base import (
    MechInteractionResponse,
)


class PostMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """PostMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = PostMechResponseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""
        mech_for_twitter = False
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"Processing mech response: {self.synchronized_data.mech_responses}"
            )

            # Process response and fetch media using the helper method
            mech_for_twitter = yield from self._process_mech_response_and_fetch_media(
                self.synchronized_data.mech_responses
            )

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=mech_for_twitter,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _process_mech_response_and_fetch_media(
        self, mech_responses: List[MechInteractionResponse]
    ) -> Generator[None, None, bool]:
        """
        Process the mech response, fetch media (video or image) based on the format,

        and save media info. Returns True if media was successfully processed and saved, False otherwise.
        """
        if not mech_responses:
            self.context.logger.error("No mech responses found")
            return False

        media_processed_successfully = False
        try:
            response_data = mech_responses[0]
            if response_data.result is None:
                self.context.logger.error("Mech response result is None")
                return False  # Early return for None result

            result_json = json.loads(response_data.result)

            # Case 1: Video format
            if "video" in result_json:
                video_hash = result_json["video"]
                self.context.logger.info(
                    f"Case 1: Found video hash: {video_hash}. Fetching..."
                )
                video_path = self.fetch_video_data_from_ipfs(video_hash)
                if video_path:
                    self.context.logger.info(
                        f"Video downloaded successfully to: {video_path}"
                    )
                    media_info = {"path": video_path, "type": "video"}
                    yield from self._write_kv(
                        {"latest_media_info": json.dumps(media_info)}
                    )
                    self.context.logger.info(
                        f"Stored media info via _write_kv: {media_info}"
                    )
                    media_processed_successfully = True
                else:
                    self.context.logger.error("Video download failed.")
                    # Keep media_processed_successfully = False

            # Case 2: Image format (via ipfs_link) - use if, not elif
            if not media_processed_successfully and "ipfs_link" in result_json:
                ipfs_link = result_json["ipfs_link"]
                self.context.logger.info(
                    f"Case 2: Found IPFS link: {ipfs_link}. Fetching image..."
                )
                success = yield from self.fetch_image_data_from_ipfs(ipfs_link)
                if success:
                    self.context.logger.info(
                        "Image data fetched and saved successfully."
                    )
                    media_processed_successfully = True
                # No need for else here, flag remains False if fetch fails

            # Case 3: Unrecognized format (implicitly handled if flag is still False)
            if not media_processed_successfully and not (
                "video" in result_json or "ipfs_link" in result_json
            ):
                self.context.logger.info(
                    "Case 3: Mech response format not recognized (no 'video' or 'ipfs_link'). Cannot fetch media."
                )

        except json.JSONDecodeError as e:
            self.context.logger.error(
                f"Error decoding JSON from mech response result: {e}"
            )
            # media_processed_successfully remains False
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Unexpected error processing mech response: {e}")
            self.context.logger.error(traceback.format_exc())
            # media_processed_successfully remains False

        return media_processed_successfully

    def _parse_and_validate_ipfs_image_response(self, response: Any) -> Optional[Dict]:
        """Parse the response from get_from_ipfs for image data and validate its structure."""
        result_data = None
        is_valid = False
        try:
            # Extract 'result' data safely
            if isinstance(response, dict) and "result" in response:
                result_data = response["result"]
            elif isinstance(response, list) and len(response) > 0:
                first_item = response[0]
                if isinstance(first_item, dict) and "result" in first_item:
                    result_data = first_item["result"]

            if result_data is None:
                self.context.logger.error(
                    f"Could not extract 'result' data from IPFS response: {response}"
                )
                # Return None below

            # Parse if string
            elif isinstance(result_data, str):
                result_data = json.loads(result_data)  # Can raise JSONDecodeError

            # Validate structure (only if result_data is now a dict)
            if (
                isinstance(result_data, dict)
                and "artifacts" in result_data
                and result_data["artifacts"]
            ):
                # Basic validation passed
                is_valid = True
            elif (
                result_data is not None
            ):  # If parsing didn't fail but structure is wrong
                self.context.logger.error(
                    f"Invalid structure or missing artifacts in result data: {result_data}"
                )
                # is_valid remains False

        except json.JSONDecodeError as e:
            self.context.logger.error(
                f"Error decoding JSON from IPFS response result: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # is_valid remains False
        except (KeyError, IndexError, TypeError) as e:
            self.context.logger.error(
                f"Error accessing expected data in IPFS response structure: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # is_valid remains False

        # Return validated data or None
        return result_data if is_valid else None

    def fetch_image_data_from_ipfs(self, ipfs_link: str) -> Generator[None, None, bool]:
        """Fetch image from IPFS link and save it to a temporary file."""
        image_path = None
        try:
            self.context.logger.info(f"Fetching image from IPFS link: {ipfs_link}")

            # Validate link and extract hash
            path_parts = ipfs_link.split("/")
            if len(path_parts) < 5:
                self.context.logger.error(f"Invalid IPFS link format: {ipfs_link}")
                return False
            ipfs_hash = path_parts[4]
            self.context.logger.info(f"Extracted IPFS hash: {ipfs_hash}")

            # Fetch initial data
            response = yield from self.get_from_ipfs(
                ipfs_hash=ipfs_hash, filetype=SupportedFiletype.JSON
            )
            if not response:
                self.context.logger.error(
                    "Failed to fetch image: Empty response from get_from_ipfs"
                )
                return False

            # Parse and validate response structure
            result_data = self._parse_and_validate_ipfs_image_response(response)
            if result_data is None:
                # Error logged in helper
                return False

            # Extract image data
            image_base64 = result_data["artifacts"][0].get("base64")
            if not image_base64:
                self.context.logger.error(
                    f"No base64 data found in artifact: {result_data['artifacts'][0]}"
                )
                return False

            image_data = base64.b64decode(image_base64)

            # Save image to temporary file using 'with'
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            with tempfile.NamedTemporaryFile(
                suffix=f"_{timestamp}.png", delete=False
            ) as temp_file:
                temp_file.write(image_data)
                image_path = temp_file.name  # Assign path

            self.context.logger.info(
                f"Successfully saved image to temporary file: {image_path}"
            )

            # Store metadata
            media_info = {"path": image_path, "type": "image"}
            yield from self._write_kv({"latest_media_info": json.dumps(media_info)})
            self.context.logger.info(f"Stored media info: {media_info}")
            return True  # Success!

        except (KeyError, IndexError, TypeError) as e:
            self.context.logger.error(
                f"Error accessing expected data during image processing: {e}"
            )
            self.context.logger.error(traceback.format_exc())
        except IOError as e:  # Catch potential file writing errors
            self.context.logger.error(
                f"Error writing image data to temporary file {image_path}: {e}"
            )
            self.context.logger.error(traceback.format_exc())
        except Exception as e:  # pylint: disable=broad-except
            # Catch any other unexpected error during the overall fetch/processing
            self.context.logger.error(
                f"Unexpected error fetching/processing image data from {ipfs_link}: {e}"
            )
            self.context.logger.error(traceback.format_exc())

        # Cleanup if error occurred after file creation but before success
        if image_path and os.path.exists(image_path):
            self._cleanup_temp_file(image_path, "image processing error")

        return False  # Return False if any exception occurred or checks failed

    def _cleanup_temp_file(self, file_path: Optional[str], reason: str) -> None:
        """Attempt to remove a temporary file and log the outcome."""
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                self.context.logger.info(
                    f"Removed temporary file ({reason}): {file_path}"
                )
            except OSError as rm_err:
                self.context.logger.warning(
                    f"Could not remove temp file {file_path} ({reason}): {rm_err}"
                )
        elif reason == "empty content":
            self.context.logger.info("No temporary file to remove (empty download).")
        # else: file_path is None and reason is likely an error before file creation

    def _download_and_save_video(
        self, response: requests.Response, ipfs_gateway_url: str
    ) -> Optional[str]:
        """Download video stream from response and save to a temporary file."""
        video_path = None
        downloaded_size = 0
        chunk_count = 0
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            with tempfile.NamedTemporaryFile(
                suffix=f"_{timestamp}.mp4", delete=False
            ) as temp_file:
                video_path = temp_file.name  # Assign path *before* writing
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                        downloaded_size += len(chunk)
                        chunk_count += 1
                temp_file.flush()
                os.fsync(temp_file.fileno())

            if downloaded_size == 0:
                self.context.logger.error(
                    f"Received empty content (0 bytes downloaded) from {ipfs_gateway_url}"
                )
                # Cleanup is handled by the caller using _cleanup_temp_file
                return None

            self.context.logger.info(
                f"Successfully fetched video (size: {downloaded_size} bytes, chunks: {chunk_count}) to: {video_path}"
            )
            return video_path

        except IOError as e:
            self.context.logger.error(
                f"File I/O error during video download/save to {video_path}: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # Cleanup handled by the caller
            return None
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(
                f"Unexpected error during video download/save: {e}"
            )
            self.context.logger.error(traceback.format_exc())
            # Cleanup handled by the caller
            return None

    # Synchronous function using requests, ONLY downloads and returns path or None

    # ****************************************************************************
    # ******************************** WARNING ***********************************
    # ****************************************************************************
    # This function uses the 'requests' library directly to fetch video data
    # from an IPFS gateway. This is a deviation from the standard practice of
    # using the built-in IPFS helper functions (like `get_from_ipfs`).
    #
    # REASON: The standard IPFS helpers were consistently failing to retrieve
    # video files correctly, potentially due to issues with handling large files,
    # streaming, or specific gateway interactions for video content type.
    # Using 'requests' provides more direct control over the HTTP request
    # and response handling, which proved necessary to successfully download
    # the video content in this specific case.
    #
    # This approach might be less robust if the IPFS gateway URL changes or if
    # underlying IPFS fetch mechanisms in the framework are updated.
    # Consider revisiting this if the built-in methods become reliable for videos.

    # plan to revisit this and figure out what's wrong with the built-in methods
    # ****************************************************************************
    def fetch_video_data_from_ipfs(  # pylint: disable=too-many-locals
        self, ipfs_hash: str
    ) -> Optional[str]:  # Returns Optional[str], not bool or Generator
        """Fetch video data from IPFS hash using requests library, save locally, and return the path."""
        video_path = None  # Initialize video_path for potential cleanup
        ipfs_gateway_url = f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
        error_reason = "unknown error"  # Default error reason
        try:
            self.context.logger.info(
                f"Attempting synchronous video fetch via requests: {ipfs_hash}"
            )
            self.context.logger.info(f"Using IPFS gateway URL: {ipfs_gateway_url}")

            with requests.get(ipfs_gateway_url, timeout=120, stream=True) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)

                # Use helper to download and save
                video_path = self._download_and_save_video(response, ipfs_gateway_url)

                if video_path is None:
                    # Empty download, error logged in helper
                    self._cleanup_temp_file(
                        video_path, "empty content"
                    )  # video_path will be None here
                    return None

            return video_path  # Return path on success

        except requests.exceptions.Timeout as e:
            self.context.logger.error(
                f"Timeout occurred while fetching {ipfs_gateway_url}: {e}"
            )
            error_reason = "timeout"
        except requests.exceptions.HTTPError as e:
            self.context.logger.error(
                f"HTTP error occurred for {ipfs_gateway_url}: {e.response.status_code} - {e.response.reason}"
            )
            error_reason = "http error"
        except requests.exceptions.RequestException as e:
            self.context.logger.error(
                f"HTTP request failed for {ipfs_gateway_url}: {e}"
            )
            error_reason = "request exception"
        except Exception as e:  # pylint: disable=broad-except
            # Catch any other unexpected error during request setup or handling outside specific cases
            self.context.logger.error(
                f"Unexpected error in fetch_video_data_from_ipfs ({ipfs_hash}): {e}"
            )
            self.context.logger.error(traceback.format_exc())
            error_reason = "unexpected error"  # Overwrite default

        # Centralized cleanup for all error cases
        # video_path might be None if error happened before _download_and_save_video assigned it
        self._cleanup_temp_file(video_path, error_reason)
        return None  # Return None on any failure


class FailedMechRequestBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """FailedMechRequestBehaviour"""

    matching_round: Type[AbstractRound] = FailedMechRequestRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"FailedMechRequest: mech_responses = {self.synchronized_data.mech_responses}"
            )

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=False,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()


class FailedMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """FailedMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = FailedMechResponseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            self.context.logger.info(
                f"FailedMechResponse: mech_responses = {self.synchronized_data.mech_responses}"
            )

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=False,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()
