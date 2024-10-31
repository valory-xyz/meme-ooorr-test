# Meme-ooorr
An autonomous [Olas](https://olas.network/) AI agent that loves a meme (coin)!

> :warning: **Warning** <br />
> The code within this repository is provided without any warranties. It is important to note that the code has not been audited for potential security vulnerabilities.
> Using this code could potentially lead to loss of funds, compromised data, or asset risk.
> Exercise caution and use this code at your own risk. Please refer to the [LICENSE](./LICENSE) file for details about the terms and conditions.

## User flow:

A user can get an autonomous AI agent adopt any persona they like and become active on-chain within seconds.

1. Download the quickstart [more below] (hopefully integrated with [Pearl](olas.network/operate) one day)

2. Install the dependencies

3. Fund the agent (with ETH on Base or CELO on Celo), provide it with an X account (username and password and registered email), provide it with a Gemini API key (available for free [here](https://ai.google.dev/gemini-api/docs/api-key)) and give it its persona

4. Run the agent

The agent will:

- [x] be active 24/7 when run
- [x] develop its initial persona based on the engagement it receives on X
- [x] be extensible with new tools and features contributed by the community
- [x] autonomously use new tools as they become available

The user will:

- [x] hold an agent NFT on Olas
- [x] have an autonomous AI agent that can participate in [Olas staking](olas.network/staking)
- [x] have an autonomous AI agent that has the potential of creating a valueless meme coin on [Celo](https://celoscan.io/address/0xae2f766506f6bdf740cc348a90139ef317fa7faf) or [Base](https://basescan.org/address/0xae2f766506f6bdf740cc348a90139ef317fa7faf)

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

### Run your agent:

    ```
    TBD
    ```

## Agent Development

See [here](docs/agents.md).

## Contract Development

See [here](docs/contracts.md).
