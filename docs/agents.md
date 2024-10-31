> :warning: **Warning** <br />
> All commands are assumed to be run from root!

# Agent Development

## System requirements

- Python `>=3.10`
- [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
- [IPFS node](https://docs.ipfs.io/install/command-line/#official-distributions) `==0.6.0`
- [Pip](https://pip.pypa.io/en/stable/installation/)
- [Poetry](https://python-poetry.org/)
- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Set Docker permissions so you can run containers as non-root user](https://docs.docker.com/engine/install/linux-postinstall/)


## Run you own agent

#### Prepare the data

1. Prepare a keys.json file containing wallet address and the private key for the agent.

    ```
    autonomy generate-key ethereum -n 1
    ```

2. Prepare a `ethereum_private_key.txt` file containing the same private key from `keys.json`. Ensure that there is no newline at the end.

3. Deploy a [Safe on Gnosis](https://app.safe.global/welcome) (it's free) and set your agent address as a signer.

4. Create a [Tenderly](https://tenderly.co/) account, an [X account](https://x.com/) and get a a [Gemini API key](https://ai.google.dev/gemini-api/docs/api-key).

6. Make a copy of the env file:

    ```
    cp sample.env .env
    ```

7. Fill in the required environment variables in .env.

8. In the root of your repo, create a file called tenderly_vnets.json with the following content:
    ```
    {
        "base": {
            "network_id": 8453,
            "wallets": {
                "addresses": {
                    "agent_memeooorr": "<your_agent_address>",
                    "safe_memeooorr": "<your_safe_address>",
                    "contract_deployer": "0x8BaD7472acCe7b223Ef085028FBA29357F700501"
                },
                "funds": {
                    "native": 10,
                    "0x54330d28ca3357F294334BDC454a032e7f353416": 100
                }
            }
        }
    }
    ```

9. Create a Base fork on Tenderly, fund your wallets and deploy the MemeBase contract. If you are using a Tenderly free account, you will need to repeat this every 20 blocks:
    ```
    python scripts/rebuild_tenderly.py
    make deploy-contracts
    ```



#### Run a single agent locally

```
bash run_agent.sh
```

#### Run the service (4 agents) via Docker Compose deployment

1. Check that Docker is running:

    ```
    docker
    ```

2. Run the service:


### Get the code

1. Clone this repo:

    ```
    git clone git@github.com:dvilelaf/meme-ooorr.git
    ```

2. Create the virtual environment:

    ```
    cd meme-ooorr
    poetry shell
    poetry install
    ```

3. Sync packages:

    ```
    autonomy packages sync --update-packages
    ```

### Prepare the data

1. Prepare a keys.json file containing wallet address and the private key for the agent.

    ```
    autonomy generate-key ethereum -n 1
    ```

2. Prepare a `ethereum_private_key.txt` file containing the same private key from `keys.json`. Ensure that there is no newline at the end.

3. Deploy a [Safe on Gnosis](https://app.safe.global/welcome) (it's free) and set your agent address as a signer.

4. Create a [Tenderly](https://tenderly.co/) account and from your dashboard create a fork of Base chain (virtual testnet).

5. From Tenderly, fund your agents and Safe with some ETH.

6. Make a copy of the env file:

    ```
    cp sample.env .env
    ```

7. Fill in the required environment variables in .env. You will need to create an [X account](https://x.com/) and a [Gemini API key](https://ai.google.dev/gemini-api/docs/api-key).


### Run a single agent locally

```
bash run_agent.sh
```

### Run the service (4 agents) via Docker Compose deployment

1. Check that Docker is running:

    ```
    docker
    ```

2. Run the service:

    ```
    bash run_service.sh
    ```

3. Look at the service logs for one of the agents (on another terminal):

    ```
    docker logs -f memeooorr_abci_0
    ```
