/*global describe, context, beforeEach, it*/
const { expect } = require("chai");
const { ethers } = require("hardhat");
const helpers = require("@nomicfoundation/hardhat-network-helpers");

// This works on a fork only!
const main = async () => {
    const fs = require("fs");
    const globalsFile = "globals.json";
    let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
    const parsedData = JSON.parse(dataFromJSON);

    const AddressZero = ethers.constants.AddressZero;
    const HashZero = ethers.constants.HashZero;
    const name = "Meme";
    const symbol = "MM";
    const totalSupply = "1" + "0".repeat(24);
    const defaultDeposit = ethers.utils.parseEther("1500");
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;

    signers = await ethers.getSigners();
    deployer = signers[0];

    console.log("Getting launch campaign data");
    const campaignFile = "scripts/deployment/memebase_campaign.json";
    dataFromJSON = fs.readFileSync(campaignFile, "utf8");
    const campaignData = JSON.parse(dataFromJSON);
    console.log("Number of entries:", campaignData.length);
    
    const accounts = new Array();
    const amounts = new Array();
    for (let i = 0; i < campaignData.length; i++) {
        accounts.push(campaignData[i]["hearter"]);
        amounts.push(campaignData[i]["amount"].toString());
    }

    // BuyBackBurner implementation and proxy
    const BuyBackBurner = await ethers.getContractFactory("BuyBackBurner");
    const buyBackBurnerImplementation = await BuyBackBurner.deploy();
    await buyBackBurnerImplementation.deployed();

    // Initialize buyBackBurner
    const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", []);
    const BuyBackBurnerProxy = await ethers.getContractFactory("BuyBackBurnerProxy");
    const buyBackBurnerProxy = await BuyBackBurnerProxy.deploy(buyBackBurnerImplementation.address, proxyData);
    await buyBackBurnerProxy.deployed();

    const buyBackBurner = await ethers.getContractAt("BuyBackBurner", buyBackBurnerProxy.address);

    const MemeBase = await ethers.getContractFactory("MemeBase");
    const memeBase = await MemeBase.deploy(parsedData.olasAddress, parsedData.wethAddress,
        parsedData.uniV3positionManagerAddress, buyBackBurner.address, parsedData.minNativeTokenValue,
        accounts, amounts);
    await memeBase.deployed();

    // Get campaign token
    const campaignToken = await memeBase.memeTokens(0);
    console.log("Campaign meme contract:", campaignToken);

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});
    // Get meme token address
    const memeToken = await memeBase.memeTokens(1);
    console.log("New meme contract:", memeToken);

    // Heart a new token by other accounts
    await memeBase.connect(signers[1]).heartThisMeme(memeToken, {value: defaultDeposit});
    await memeBase.connect(signers[2]).heartThisMeme(memeToken, {value: defaultDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await memeBase.unleashThisMeme(memeToken);

    // Deployer has already collected
    await expect(
        memeBase.collectThisMeme(memeToken)
    ).to.be.reverted;

    // Collect by the first signer
    await memeBase.connect(signers[1]).collectThisMeme(memeToken);

    // Wait for 24 more hours
    await helpers.time.increase(oneDay + 10);

    // Second signer cannot collect
    await expect(
        memeBase.connect(signers[2]).collectThisMeme(memeToken)
    ).to.be.reverted;

    // Purge remaining allocation
    await memeBase.purgeThisMeme(memeToken);

    // Wait for 10 more seconds
    await helpers.time.increase(10);

    // Swap to OLAS
    const olasAmount = await memeBase.scheduledForAscendance();
    // First 127.5 ETH are collected towards campaign
    if (olasAmount.gt(0)) {
        await memeBase.scheduleForAscendance();
    }

    // Collect fees
    await memeBase.collectFees([campaignToken, memeToken]);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
