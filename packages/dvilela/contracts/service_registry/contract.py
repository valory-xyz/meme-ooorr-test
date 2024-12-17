# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2023-2024 Valory AG
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

"""This module contains the class to connect to an Service Registry contract."""

import logging
from typing import Dict, List

from aea.configurations.base import PublicId
from aea.contracts.base import Contract
from aea_ledger_ethereum import EthereumApi


PUBLIC_ID = PublicId.from_str("dvilela/service_registry:0.1.0")

_logger = logging.getLogger(
    f"aea.packages.{PUBLIC_ID.author}.contracts.{PUBLIC_ID.name}.contract"
)


class ServiceRegistryContract(Contract):
    """The Service registry contract."""

    contract_id = PUBLIC_ID

    @classmethod
    def get_services_data(
        cls,
        ledger_api: EthereumApi,
        contract_address: str,
    ) -> Dict:
        """Get the data from the Summoned event."""
        contract_instance = cls.get_instance(ledger_api, contract_address)

        # Get the number of registered services
        n_services = contract_instance.functions.totalSupply().call()
        _logger.info(f"Got {n_services} services")

        services_data = []
        for i in range(1, n_services + 1):
            _logger.info(f"Reading service {i}")
            service_data = contract_instance.functions.mapServices(i).call()
            services_data.append(
                {
                    "security_deposit": service_data[0],
                    "multisig_address": service_data[1],
                    "ipfs_hash": "f01701220" + service_data[2].hex(),
                    "threshold": service_data[3],
                    "max_num_agent_instances": service_data[4],
                    "num_agent_instances": service_data[5],
                    "state": service_data[6],
                }
            )

        return {"services_data": services_data}
