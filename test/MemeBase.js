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
    const defaultDeposit = parsedData.minNativeTokenValue;
    const defaultHash = "0x" + "5".repeat(64);
    const payload = "0x";
    const oneDay = 86400;
    const twoDays = 2 * oneDay;
    const slippage = 10;

    signers = await ethers.getSigners();
    deployer = signers[0];

    console.log("Getting redemption data");
    const redemptionsFile = "scripts/deployment/memebase_redemption.json";
    dataFromJSON = fs.readFileSync(redemptionsFile, "utf8");
    const redemptionsData = JSON.parse(dataFromJSON);
    console.log("Number of entries:", redemptionsData.length);
    
    const accounts = new Array();
    const amounts = new Array();
    for (let i = 0; i < redemptionsData.length; i++) {
        accounts.push(redemptionsData[i]["hearter"]);
        amounts.push(redemptionsData[i]["amount"].toString());
    }

    const Oracle = await ethers.getContractFactory("BalancerPriceOracle");
    const oracle = await Oracle.deploy(parsedData.olasAddress, parsedData.wethAddress, parsedData.maxSlippageOracle,
        parsedData.minUpdateTimePeriod, parsedData.balancerVaultAddress, parsedData.balancerPoolId);
    await oracle.deployed();

    const factoryParams = {
        olas: parsedData.olasAddress,
        nativeToken: parsedData.wethAddress,
        uniV2router: parsedData.routerAddress,
        uniV2factory: parsedData.factoryAddress,
        oracle: oracle.address,
        maxSlippage: parsedData.maxSlippageMeme,
        minNativeTokenValue: parsedData.minNativeTokenValue
    }

    const MemeBase = await ethers.getContractFactory("MemeBase");
    const memeBase = await MemeBase.deploy(factoryParams, parsedData.l2TokenBridgeAddress,
        parsedData.balancerVaultAddress, parsedData.balancerPoolId, accounts, amounts);
    await memeBase.deployed();

    // Summon a new meme token
    await memeBase.summonThisMeme(name, symbol, totalSupply, {value: defaultDeposit});
    // 0-th token is the redemptionOne
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
    await memeBase.scheduleOLASForAscendance(olasAmount, slippage);
};

main()
    .then(() => process.exit(0))
    .catch(error => {
        console.error(error);
        process.exit(1);
    });
