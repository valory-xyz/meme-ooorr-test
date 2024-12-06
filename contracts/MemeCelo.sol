// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

/// @title MemeCelo - a smart contract factory for Meme Token creation on Celo.
contract MemeCelo is MemeFactory {
    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue
    ) MemeFactory(_olas, _nativeToken, _uniV3PositionManager, _buyBackBurner, _minNativeTokenValue) {}

    /// @dev Launch campaign logic.
    function _launchCampaign() internal virtual override {}

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @param nativeAmountForOLASBurn Amount of native token to conver to OLAS and burn.
    /// @return adjustedNativeAmountForAscendance Adjusted amount of native token to conver to OLAS and burn.
    function _updateLaunchCampaignBalance(uint256 nativeAmountForOLASBurn) internal override pure returns (uint256 adjustedNativeAmountForAscendance) {
        return nativeAmountForOLASBurn;
    }

    function _wrap(uint256) internal virtual override {}
}
