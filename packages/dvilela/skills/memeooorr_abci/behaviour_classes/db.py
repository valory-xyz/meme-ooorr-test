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

from typing import Generator, Tuple, Type

from packages.dvilela.skills.memeooorr_abci.behaviour_classes.base import (
    MemeooorrBaseBehaviour,
)
from packages.dvilela.skills.memeooorr_abci.rounds import (
    LoadDatabasePayload,
    LoadDatabaseRound,
)
from packages.valory.skills.abstract_round_abci.base import AbstractRound


class LoadDatabaseBehaviour(
    MemeooorrBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """LoadDatabaseBehaviour"""

    matching_round: Type[AbstractRound] = LoadDatabaseRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            persona, latest_tweet = yield from self.load_db()

            payload = LoadDatabasePayload(
                sender=self.context.agent_address,
                persona=persona,
                latest_tweet=latest_tweet,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def load_db(self) -> Generator[None, None, Tuple[str, str]]:
        """Load the data"""
        db_data = yield from self._read_kv(keys=("persona", "latest_tweet"))

        if db_data is None:
            self.context.logger.error("Error while loading the database")
            persona = yield from self.get_persona()
            latest_tweet = "{}"
            return persona, latest_tweet

        persona = db_data["persona"]
        latest_tweet = db_data["latest_tweet"]

        if not persona:
            persona = yield from self.get_persona()

        if not latest_tweet:
            latest_tweet = "{}"

        self.context.logger.info(
            f"Loaded from the db\npersona={persona}\nlatest_tweet={latest_tweet}"
        )
        return persona, latest_tweet
