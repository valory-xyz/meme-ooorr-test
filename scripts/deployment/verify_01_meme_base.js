const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

module.exports = [
    parsedData.olasAddress,
    parsedData.usdcAddress,
    parsedData.wethAddress,
    parsedData.routerAddress,
    parsedData.factoryAddress,
    parsedData.l2StandardBridgeAddress,
    parsedData.balancerVaultAddress,
    parsedData.balancerPoolId,
    parsedData.oracleAddress
];