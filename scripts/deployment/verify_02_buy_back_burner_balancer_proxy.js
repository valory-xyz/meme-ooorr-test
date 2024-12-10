const { ethers } = require("hardhat");
const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);
const buyBackBurnerAddress = parsedData.buyBackBurnerAddress;
const buyBackBurner = await ethers.getContractAt("BuyBackBurnerProxy", buyBackBurnerAddress);
const proxyPayload = ethers.utils.defaultAbiCoder.encode(["address[]", "bytes32", "uint256"],
     [[parsedData.olasAddress, parsedData.wethAddress, balancerPriceOracle.address,
     parsedData.balancerVaultAddress], parsedData.balancerPoolId, parsedData.maxBuyBackSlippage]);
const proxyData = buyBackBurnerImplementation.interface.encodeFunctionData("initialize", [proxyPayload]);

module.exports = [
    buyBackBurnerAddress,
    proxyData
];