/*global describe, context, beforeEach, it*/
const { expect } = require("chai");
const { ethers } = require("hardhat");
const helpers = require("@nomicfoundation/hardhat-network-helpers");

// This works on a fork only!
const main = async () => {
    const fs = require("fs");
    const globalsFile = "globals.json";
    const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    const parsedData = JSON.parse(dataFromJSON);

    const AddressZero = ethers.constants.AddressZero;
    const HashZero = ethers.constants.HashZero;
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const defaultDeposit = parsedData.minNativeTokenValue;//ethers.utils.parseEther("1");
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;

    signers = await ethers.getSigners();
    deployer = signers[0];

    const Meme = await ethers.getContractFactory("Meme");
    const meme = await Meme.deploy(name, symbol, 18, totalSupply);
    await meme.deployed();

    const celo = await ethers.getContractAt("Meme", parsedData.celoAddress);

    const MemeCelo = await ethers.getContractFactory("MemeCelo");
    const memeCelo = await MemeCelo.deploy(parsedData.olasAddress, parsedData.cusdAddress, parsedData.routerAddress,
        parsedData.factoryAddress, parsedData.minNativeTokenValue, parsedData.celoAddress,
        parsedData.l2TokenBridgeAddress, parsedData.oracleAddress);
    await memeCelo.deployed();

    // Summon a new meme token
    await memeCelo.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});
    const memeToken = await memeCelo.memeTokens(0);
    console.log("New meme contract:", memeToken);

    // Heart a new token by other accounts
    await memeCelo.connect(signers[1]).heartThisMeme(memeToken, {value: defaultDeposit});
    await memeCelo.connect(signers[2]).heartThisMeme(memeToken, {value: defaultDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 100);

    // Unleash the meme token
    await memeCelo.unleashThisMeme(memeToken, 0);

    // Collect by the first signer
    await memeCelo.collectThisMeme(memeToken);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
