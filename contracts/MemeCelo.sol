// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

/// @title MemeCelo - a smart contract factory for Meme Token creation on Celo.
contract MemeCelo is MemeFactory {
    /// @dev MemeBase constructor
    constructor(FactoryParams memory factoryParams) MemeFactory(factoryParams) {}

    function _launchCampaign(uint256 nativeAmountForOLASBurn) internal override pure returns (uint256) {
        return nativeAmountForOLASBurn;
    }

    function _wrap(uint256) internal virtual override {}
}
