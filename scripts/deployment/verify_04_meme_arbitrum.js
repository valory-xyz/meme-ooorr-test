const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

module.exports = [
    parsedData.olasAddress,
    parsedData.usdcAddress,
    parsedData.routerAddress,
    parsedData.factoryAddress,
    parsedData.minNativeTokenValue,
    parsedData.wethAddress,
    parsedData.l2TokenBridgeAddress,
    parsedData.oracleAddress,
    parsedData.balancerVaultAddress,
    parsedData.balancerPoolId
];