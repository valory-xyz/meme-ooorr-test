const fs = require("fs");
const globalsFile = "globals.json";
const dataFromJSON = fs.readFileSync(globalsFile, "utf8");
const parsedData = JSON.parse(dataFromJSON);

const factoryParams = {
    olas: parsedData.olasAddress,
    nativeToken: parsedData.celoAddress,
    router: parsedData.routerAddress,
    factory: parsedData.factoryAddress,
    oracle: parsedData.oracleAddress,
    maxSlippage: parsedData.maxSlippage,
    minNativeTokenValue: parsedData.minNativeTokenValue
}

module.exports = [
    factoryParams,
    parsedData.l2TokenBridgeAddress
];