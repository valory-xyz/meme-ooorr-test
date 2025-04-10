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
from typing import Generator, Optional, Type

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


class PostMechResponseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """PostMechResponseBehaviour"""

    matching_round: Type[AbstractRound] = PostMechResponseRound

    def async_act(self) -> Generator:  # pylint: disable=too-many-statements
        """Do the act, supporting asynchronous execution."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Initialize mech_for_twitter to False by default
            mech_for_twitter = False
            ipfs_link = None
            video_hash = None

            self.context.logger.info(
                f"Mech request was successful, response = {self.synchronized_data.mech_responses}"
            )
            if self.synchronized_data.mech_responses:
                try:
                    # Check if the response contains video and image keys
                    response = self.synchronized_data.mech_responses[0]
                    # Add null check before parsing JSON
                    if response.result is not None:
                        result_json = json.loads(response.result)

                        # Case 1: Check if the result_json has 'video' key
                        if "video" in result_json:
                            video_hash = result_json["video"]
                            self.context.logger.info(
                                "Case 1: Video hash found. Fetching video from IPFS."
                            )
                            self.context.logger.info(f"Video IPFS hash: {video_hash}")
                            # Call the synchronous download function (no yield from)
                            video_path = self.fetch_video_data_from_ipfs(video_hash)
                            # If download succeeded, save path and type asynchronously
                            if video_path:
                                self.context.logger.info(
                                    f"Video downloaded successfully to: {video_path}"
                                )
                                # Now save using _write_kv in the async context
                                media_info = {"path": video_path, "type": "video"}
                                yield from self._write_kv(
                                    {"latest_media_info": json.dumps(media_info)}
                                )
                                self.context.logger.info(
                                    f"Stored media info via _write_kv: {media_info}"
                                )
                                mech_for_twitter = True  # Set flag only after successful download AND save
                            else:
                                self.context.logger.error("Video download failed.")
                                # mech_for_twitter remains False

                        # Case 2: Check if the result_json has an 'ipfs_link' (old format)
                        elif "ipfs_link" in result_json:
                            ipfs_link = result_json["ipfs_link"]
                            self.context.logger.info(
                                "Case 2: IPFS link found. Fetching image from IPFS link."
                            )
                            self.context.logger.info(f"IPFS link: {ipfs_link}")
                            # Fetch image data using the IPFS link
                            success = yield from self.fetch_image_data_from_ipfs(
                                ipfs_link
                            )
                            if success:
                                self.context.logger.info(
                                    "Image data fetched and saved successfully."
                                )
                                mech_for_twitter = True
                            else:
                                self.context.logger.error(
                                    "Failed to fetch or save image data from IPFS link."
                                )
                                # Keep mech_for_twitter False if image fetch fails

                        # Case 3: Neither expected format found
                        else:
                            self.context.logger.info(
                                "Case 3: Mech response format not recognized (no video/image hash pair or ipfs_link). Cannot fetch media."
                            )
                            mech_for_twitter = False
                    else:
                        self.context.logger.error("Mech response result is None")
                        mech_for_twitter = False
                except json.JSONDecodeError as e:
                    self.context.logger.error(
                        f"Error decoding JSON from mech response result: {e}"
                    )
                    mech_for_twitter = False
                except Exception as e:  # pylint: disable=broad-except
                    self.context.logger.error(f"Error processing mech response: {e}")
                    # mech_for_twitter remains False in case of exception
            else:
                self.context.logger.error("No mech responses found")
                # mech_for_twitter remains False if no responses

            sender = self.context.agent_address
            payload = MechPayload(
                sender=sender,
                mech_for_twitter=mech_for_twitter,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def fetch_image_data_from_ipfs(  # pylint: disable=too-many-return-statements
        self, ipfs_link: str
    ) -> Generator[None, None, bool]:
        """Fetch image from IPFS link and save it to a temporary file."""
        try:
            self.context.logger.info(f"Fetching image from IPFS link: {ipfs_link}")

            # Extract the IPFS hash from the URL
            path_parts = ipfs_link.split("/")
            ipfs_hash = path_parts[4]
            self.context.logger.info(f"Extracted IPFS hash: {ipfs_hash}")

            response = yield from self.get_from_ipfs(
                ipfs_hash=ipfs_hash, filetype=SupportedFiletype.JSON
            )

            if response:
                try:
                    # The response from get_from_ipfs is a Python object, might be dict or list
                    # Check if it's a dictionary with 'result' field
                    if isinstance(response, dict) and "result" in response:
                        result_data = response["result"]
                    # Check if it's a list (the actual error case)
                    elif isinstance(response, list) and len(response) > 0:
                        # Take the first item if it's a list
                        result_item = response[0]
                        # Check if the first item has a result field
                        if isinstance(result_item, dict) and "result" in result_item:
                            result_data = result_item["result"]
                        else:
                            self.context.logger.error(
                                f"Unexpected response format: {response}"
                            )
                            return False
                    else:
                        self.context.logger.error(
                            f"Unexpected response format: {response}"
                        )
                        return False

                    # Parse result_data if it's a string
                    if isinstance(result_data, str):
                        result_data = json.loads(result_data)

                    # Process artifacts
                    if "artifacts" in result_data and result_data["artifacts"]:
                        # Get the first artifact's base64 data
                        image_base64 = result_data["artifacts"][0]["base64"]
                        image_data = base64.b64decode(image_base64)

                        # Create a temporary file with a specific suffix for the image
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        with tempfile.NamedTemporaryFile(
                            suffix=f"_{timestamp}.png", delete=False
                        ) as temp_file:
                            temp_file.write(image_data)
                            image_path = temp_file.name

                        self.context.logger.info(
                            f"Successfully saved image to temporary file: {image_path}"
                        )

                        # Store the image path and type in the context
                        media_info = {"path": image_path, "type": "image"}
                        yield from self._write_kv(
                            {"latest_media_info": json.dumps(media_info)}
                        )
                        self.context.logger.info(f"Stored media info: {media_info}")
                        return True

                    self.context.logger.error("No artifacts found in result data")
                    return False

                except Exception as e:  # pylint: disable=broad-except
                    self.context.logger.error(f"Error processing response: {e}")
                    self.context.logger.error(traceback.format_exc())
                    return False

            self.context.logger.error("Failed to fetch image: Empty response")
            return False

        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error fetching image: {e}")
            self.context.logger.error(traceback.format_exc())
            return False

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
    def fetch_video_data_from_ipfs(  # pylint: disable=too-many-return-statements, too-many-locals
        self, ipfs_hash: str
    ) -> Optional[str]:  # Returns Optional[str], not bool or Generator
        """Fetch video data from IPFS hash using requests library, save locally, and return the path."""
        video_path = None  # Initialize
        try:
            self.context.logger.info(
                f"Attempting synchronous video fetch via requests: {ipfs_hash}"
            )
            ipfs_gateway_url = f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}"
            self.context.logger.info(f"Using IPFS gateway URL: {ipfs_gateway_url}")

            with requests.get(ipfs_gateway_url, timeout=120, stream=True) as response:
                response.raise_for_status()
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                with tempfile.NamedTemporaryFile(
                    suffix=f"_{timestamp}.mp4", delete=False
                ) as temp_file:
                    video_path = temp_file.name  # Assign path
                    downloaded_size = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                            downloaded_size += len(chunk)

            if downloaded_size == 0:
                self.context.logger.error(
                    f"Received empty content from {ipfs_gateway_url}"
                )
                # Attempt to remove empty file if created
                if video_path and os.path.exists(video_path):
                    try:
                        os.remove(video_path)
                        self.context.logger.info(
                            f"Removed empty temporary file: {video_path}"
                        )
                    except OSError as rm_err:
                        self.context.logger.warning(
                            f"Could not remove empty temp file {video_path}: {rm_err}"
                        )
                return None  # Return None on failure

            self.context.logger.info(
                f"Successfully fetched video (size: {downloaded_size} bytes) to: {video_path}"
            )
            # DO NOT save to KV store here
            return video_path  # Return path on success

        except requests.exceptions.RequestException as e:
            self.context.logger.error(f"HTTP request failed: {e}")
            self.context.logger.error(traceback.format_exc())
            # Attempt to remove potentially partially created temp file on error
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    self.context.logger.info(
                        f"Removed temporary file due to HTTP error: {video_path}"
                    )
                except OSError as rm_err:
                    self.context.logger.warning(
                        f"Could not remove temp file {video_path} after HTTP error: {rm_err}"
                    )
            return None  # Return None on failure
        except Exception as e:  # pylint: disable=broad-except
            self.context.logger.error(f"Error in fetch_video_data_from_ipfs: {e}")
            self.context.logger.error(traceback.format_exc())
            # Attempt to remove potentially partially created temp file on error
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                    self.context.logger.info(
                        f"Removed temporary file due to error: {video_path}"
                    )
                except OSError as rm_err:
                    self.context.logger.warning(
                        f"Could not remove temp file {video_path} after error: {rm_err}"
                    )
            return None  # Return None on failure


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
