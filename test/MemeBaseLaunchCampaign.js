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
    const smallDeposit = ethers.utils.parseEther("1");
    const defaultDeposit = ethers.utils.parseEther("1500");
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    // Nonce 0 is reserved for the campaign token
    const nonce = 1;
    // Nonce 2 is spent when the 1st meme token is released
    const nonce2 = 3;

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

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: smallDeposit});

    // Heart a new token by other accounts
    await memeBase.connect(signers[1]).heartThisMeme(nonce, {value: smallDeposit});
    await memeBase.connect(signers[2]).heartThisMeme(nonce, {value: smallDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await memeBase.unleashThisMeme(nonce);

    let scheduledForAscendance = await memeBase.scheduledForAscendance();
    expect(scheduledForAscendance).to.equal(0);

    let launchCampaignBalance = await memeBase.launchCampaignBalance();
    expect(launchCampaignBalance).to.equal(ethers.BigNumber.from(smallDeposit).mul(3).div(10));

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Get first token address
    const memeToken = await memeBase.memeTokens(0);
    console.log("Meme token contract:", memeToken);

    // Purge remaining allocation
    await memeBase.purgeThisMeme(memeToken);

    //// Second test unleashing of a meme that does trigger MAGA

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});

    // Heart a new token by other accounts
    await memeBase.connect(signers[1]).heartThisMeme(nonce2, {value: defaultDeposit});
    await memeBase.connect(signers[2]).heartThisMeme(nonce2, {value: defaultDeposit});

    // Increase time to for 24 hours+
    await helpers.time.increase(oneDay + 10);

    // Unleash the meme token
    await memeBase.unleashThisMeme(nonce2);

    const LIQUIDITY_AGNT = await memeBase.LIQUIDITY_AGNT();
    launchCampaignBalance = await memeBase.launchCampaignBalance();
    expect(launchCampaignBalance).to.equal(LIQUIDITY_AGNT);

    scheduledForAscendance = await memeBase.scheduledForAscendance();
    const expectedScheduledForAscendance = ethers.BigNumber.from(smallDeposit).mul(3).div(10)
        .add(ethers.BigNumber.from(defaultDeposit).mul(3).div(10))
        .sub(ethers.BigNumber.from(launchCampaignBalance));
    expect(scheduledForAscendance).to.equal(expectedScheduledForAscendance);

    // Get campaign token
    const campaignToken = await memeBase.memeTokens(1);
    console.log("Campaign meme contract:", campaignToken);
    // Get meme token
    const memeTokenTwo = await memeBase.memeTokens(2);
    console.log("Meme token two contract:", memeToken);

    // Deployer has already collected
    await expect(
        memeBase.collectThisMeme(memeTokenTwo)
    ).to.be.reverted;

    // Collect by the first signer
    await memeBase.connect(signers[1]).collectThisMeme(memeTokenTwo);

    // Wait for 24 more hours
    await helpers.time.increase(oneDay + 10);

    // Second signer cannot collect
    await expect(
        memeBase.connect(signers[2]).collectThisMeme(memeTokenTwo)
    ).to.be.reverted;

    // Purge remaining allocation
    await memeBase.purgeThisMeme(memeTokenTwo);

    // Wait for 10 more seconds
    await helpers.time.increase(10);

    // Swap to OLAS
    const olasAmount = await memeBase.scheduledForAscendance();
    // First 127.5 ETH are collected towards campaign
    if (olasAmount.gt(0)) {
        await memeBase.scheduleForAscendance();
    }

    // Collect fees
    await memeBase.collectFees([campaignToken, memeToken, memeTokenTwo]);

    // Check the contract balance
    const baseBalance = await ethers.provider.getBalance(memeBase.address);
    expect(baseBalance).to.equal(0);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
