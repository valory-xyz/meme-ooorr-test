#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2021-2025 Valory AG
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


"""Updates fetched agent with correct config"""
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv


AGENT_NAME = "memeooorr"

PATH_TO_VAR = {
    # Chains
    # "config/ledger_apis/ethereum/address": "ETHEREUM_LEDGER_RPC",
    # "config/ledger_apis/ethereum/chain_id": "ETHEREUM_LEDGER_CHAIN_ID",
    "config/ledger_apis/base/address": "BASE_LEDGER_RPC",
    "config/ledger_apis/base/chain_id": "BASE_LEDGER_CHAIN_ID",
    # Params
    "models/params/args/setup/all_participants": "ALL_PARTICIPANTS",
    "models/params/args/reset_tendermint_after": "RESET_TENDERMINT_AFTER",
    "models/params/args/reset_pause_duration": "RESET_PAUSE_DURATION",
    "models/params/args/termination_from_block": "TERMINATION_FROM_BLOCK",
    "models/params/args/on_chain_service_id": "ON_CHAIN_SERVICE_ID",
    "models/params/args/minimum_gas_balance": "MINIMUM_GAS_BALANCE",
    "models/params/args/min_feedback_replies": "MIN_FEEDBACK_REPLIES",
    "models/params/args/setup/safe_contract_address": "SAFE_CONTRACT_ADDRESS",
    "models/params/args/feedback_period_min_hours": "FEEDBACK_PERIOD_MIN_HOURS",
    "models/params/args/feedback_period_max_hours": "FEEDBACK_PERIOD_MAX_HOURS",
    "models/params/args/twitter_username": "TWIKIT_USERNAME",
    "models/params/args/persona": "PERSONA",
    "models/params/args/skip_engagement": "SKIP_ENGAGEMENT",
    "models/params/args/staking_token_contract_address": "STAKING_CONTRACT_ADDRESS",
    "models/params/args/staking_activity_checker_contract_address": "ACTIVITY_CHECKER_CONTRACT_ADDRESS",
    # Twikit connection
    "config/twikit_username": "TWIKIT_USERNAME",
    "config/twikit_email": "TWIKIT_EMAIL",
    "config/twikit_password": "TWIKIT_PASSWORD",
    "config/twikit_cookies_path": "TWIKIT_COOKIES_PATH",
    "config/twikit_disable_tweets": "TWIKIT_DISABLE_TWEETS",
    "config/twikit_skip_connection": "TWIKIT_SKIP_CONNECTION",
    # Genai connection
    "config/genai_api_key": "GENAI_API_KEY",
    # DB
    "config/db_path": "DB_PATH",
    # Mirror DB
    "config/mirror_db_base_url": "MIRROR_DB_BASE_URL",
}

CONFIG_REGEX = r"\${.*?:(.*)}"


def find_and_replace(config, path, new_value):
    """Find and replace a variable"""

    # Find the correct section where this variable fits
    section_index = None
    for i, section in enumerate(config):
        value = section
        try:
            for part in path:
                value = value[part]
            section_index = i
        except KeyError:
            continue

    if section_index is None:
        raise ValueError(f"Could not update {path}")

    # To persist the changes in the config variable,
    # access iterating the path parts but the last part
    sub_dic = config[section_index]
    for part in path[:-1]:
        sub_dic = sub_dic[part]

    # Now, get the whole string value
    old_str_value = sub_dic[path[-1]]

    # Extract the old variable value
    match = re.match(CONFIG_REGEX, old_str_value)
    old_var_value = match.groups()[0]

    # Replace the old variable with the secret value in the complete string
    new_str_value = old_str_value.replace(old_var_value, new_value)
    sub_dic[path[-1]] = new_str_value

    return config


def main() -> None:
    """Main"""
    load_dotenv()

    # Load the aea config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "r", encoding="utf-8") as file:
        config = list(yaml.safe_load_all(file))

    # Search and replace all the secrets
    for path, var in PATH_TO_VAR.items():
        try:
            new_value = os.getenv(var)
            if new_value is None:
                print(f"Env var {var} is not set")
                continue
            config = find_and_replace(config, path.split("/"), new_value)
        except Exception as e:
            raise ValueError(f"Could not update {path}") from e

    # Dump the updated config
    with open(Path(AGENT_NAME, "aea-config.yaml"), "w", encoding="utf-8") as file:
        yaml.dump_all(config, file, sort_keys=False)


if __name__ == "__main__":
    main()
