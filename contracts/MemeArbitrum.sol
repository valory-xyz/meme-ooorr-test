// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

interface IWETH {
    function deposit() external payable;
}

// @title MemeArbitrum - a smart contract factory for Meme Token creation on Arbitrum.
contract MemeArbitrum is MemeFactory {
    /// @dev MemeArbitrum constructor
    constructor(FactoryParams memory factoryParams) MemeFactory(factoryParams) {}

    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal override pure returns (uint256) {
        return nativeAmountForOLASBurn;
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
