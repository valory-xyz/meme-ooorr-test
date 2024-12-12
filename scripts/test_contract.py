
import typing
from packages.dvilela.contracts.meme_factory.contract import (
    MemeFactoryContract,
)
from aea.contracts.base import Contract
from aea_ledger_ethereum.ethereum import EthereumApi
import dotenv
import os

dotenv.load_dotenv(override=True)

SUMMON_BLOCK_DELTA = 100000

ContractType = typing.TypeVar("ContractType")


def load_contract(ctype: ContractType) -> ContractType:
    """Load contract."""
    *parts, _ = ctype.__module__.split(".")
    path = "/".join(parts)
    return Contract.from_dir(directory=path)


ledger_api = EthereumApi(address=os.getenv("BASE_LEDGER_RPC_ALCHEMY"))
meme_factory_address = os.getenv("MEME_FACTORY_ADDRESS")
erc20_contract = typing.cast(
    typing.Type[MemeFactoryContract], load_contract(MemeFactoryContract)
)

from_block = ledger_api.api.eth.block_number - SUMMON_BLOCK_DELTA

data = erc20_contract.get_events(
    ledger_api, meme_factory_address, "Summoned", from_block
)

print(data)