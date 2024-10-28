# Meme-ooorr
An autonomous [Olas](https://olas.network/) AI agent that loves a meme (coin)!

## Agent Development

### System requirements

- Python `>=3.10`
- [Tendermint](https://docs.tendermint.com/v0.34/introduction/install.html) `==0.34.19`
- [IPFS node](https://docs.ipfs.io/install/command-line/#official-distributions) `==0.6.0`
- [Pip](https://pip.pypa.io/en/stable/installation/)
- [Poetry](https://python-poetry.org/)
- [Docker Engine](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Set Docker permissions so you can run containers as non-root user](https://docs.docker.com/engine/install/linux-postinstall/)


### Run you own agent

#### Get the code

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

#### Prepare the data

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

    ```
    bash run_service.sh
    ```

3. Look at the service logs for one of the agents (on another terminal):

    ```
    docker logs -f memeooorr_abci_0
    ```


## Contract Development

### Prerequisites
- This repository follows the standard [`Hardhat`](https://hardhat.org/tutorial/) development process.
- The code is written on Solidity starting from version `0.8.28`.
- The standard versions of Node.js along with Yarn are required to proceed further (confirmed to work with Yarn `1.22.19`, npx/npm `10.9.0` and node `v20.14.0`).

### Install the dependencies
The project has submodules to get the dependencies. Make sure you run `git clone --recursive` or init the submodules yourself.
The dependency list is managed by the `package.json` file, and the setup parameters are stored in the `hardhat.config.js` file.
Simply run the following command to install the project:
```
yarn install
```

### Core components
The contracts, packages, scripts and tests are located in the following folders respectively:
```
contracts
packages
scripts
test
```

### Compile the code and run
Compile the code:
```
npx hardhat compile
```
Run the tests:
```
npx hardhat test
```

## Acknowledgements
The registries contracts were inspired and based on the following sources:
- [Rari-Capital](https://github.com/Rari-Capital/solmate). Last known audited version: `eaa7041378f9a6c12f943de08a6c41b31a9870fc`;