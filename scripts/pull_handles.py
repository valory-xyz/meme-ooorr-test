from web3 import Web3
import json
import requests
import os
import dotenv

dotenv.load_dotenv(override=True)

w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_RPC")))

with open("ServiceRegistryL2.json", "r") as inf:
    abi = json.load(inf)

contract_address = "0x3C1fF68f5aa342D296d4DEe4Bb1cACCA912D95fE"

contract = w3.eth.contract(address=contract_address, abi=abi)

n_services = contract.functions.totalSupply().call()

for i in range(1, n_services + 1):
    _, _, config_hash, _, _, _, _ = contract.functions.mapServices(i).call()
    ipfs_hash = "f01701220" + config_hash.hex()
    response = requests.get(f"https://gateway.autonolas.tech/ipfs/{ipfs_hash}")
    print(response.json()["description"])


