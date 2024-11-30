const fs = require("fs");
const globalsFile = "globals.json";
let dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

const redemptionsFile = "scripts/deployment/memebase_redemption.json";
dataFromJSON = fs.readFileSync(redemptionsFile, "utf8");
const redemptionsData = JSON.parse(dataFromJSON);

const accounts = new Array();
const amounts = new Array();
for (let i = 0; i < redemptionsData.length; i++) {
    accounts.push(redemptionsData[i]["hearter"]);
    amounts.push(redemptionsData[i]["amount"].toString());
}

const factoryParams = {
    olas: parsedData.olasAddress,
    nativeToken: parsedData.wethAddress,
    router: parsedData.routerAddress,
    factory: parsedData.factoryAddress,
    oracle: parsedData.oracleAddress,
    maxSlippage: parsedData.maxSlippage,
    minNativeTokenValue: parsedData.minNativeTokenValue
}

module.exports = [
    factoryParams,
    parsedData.l2TokenBridgeAddress,
    parsedData.balancerVaultAddress,
    parsedData.balancerPoolId,
    accounts,
    amounts
];