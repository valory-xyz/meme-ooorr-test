// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory, Meme} from "./MemeFactory.sol";

interface IWETH {
    function deposit() external payable;
}

/// @title MemeBase - a smart contract factory for Meme Token creation on Base.
contract MemeBase is MemeFactory {
    // AGNT data:
    // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F17
    // Previous token address: 0x7484a9fB40b16c4DFE9195Da399e808aa45E9BB9
    // Full collected amount: 141569842100000000000
    uint256 public constant CONTRIBUTION_AGNT = 141569842100000000000;
    // Liquidity amount: collected amount - 10% for burn = 127412857890000000000
    uint256 public constant LIQUIDITY_AGNT = 127412857890000000000;
    // Block time of original summon
    uint256 public constant SUMMON_AGNT = 22902993;

    // Launch campaign nonce
    uint256 public immutable launchCampaignNonce;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _nativeToken,
        address _uniV3PositionManager,
        address _buyBackBurner,
        uint256 _minNativeTokenValue,
        address[] memory accounts,
        uint256[] memory amounts
    ) MemeFactory(_olas, _nativeToken, _uniV3PositionManager, _buyBackBurner, _minNativeTokenValue) {
        if (accounts.length > 0) {
            launchCampaignNonce = _nonce;
            _launchCampaignSetup(accounts, amounts);
            _nonce = launchCampaignNonce + 1;
            launchAmountTarget = LIQUIDITY_AGNT;
        }
    }

    /// @dev Launch campaign initialization function.
    /// @param accounts Original accounts.
    /// @param amounts Corresponding original amounts (without subtraction for burn).
    function _launchCampaignSetup(address[] memory accounts, uint256[] memory amounts) private {
        require(accounts.length == amounts.length);

        // Initiate meme token map values
        // unleashTime is set to 1 such that no one is able to heart this token
        memeSummons[launchCampaignNonce] = MemeSummon("Agent Token II", "AGNT II", 1_000_000_000 ether,
            CONTRIBUTION_AGNT, SUMMON_AGNT, 1, 0, 0, false);

        // To match original summon events (purposefully placed here to match order of original events)
        emit Summoned(accounts[0], launchCampaignNonce, amounts[0]);

        // Record all the accounts and amounts
        uint256 totalAmount;
        for (uint256 i = 0; i < accounts.length; ++i) {
            totalAmount += amounts[i];
            memeHearters[launchCampaignNonce][accounts[i]] = amounts[i];
            // to match original hearter events
            emit Hearted(accounts[i], launchCampaignNonce, amounts[i]);
        }
        require(totalAmount == CONTRIBUTION_AGNT, "Total amount must match original contribution amount");
        // Adjust amount for already collected burned tokens
        uint256 adjustedAmount = (totalAmount * 9) / 10;
        require(adjustedAmount == LIQUIDITY_AGNT, "Total amount adjusted for burn allocation must match liquidity amount");
    }

    /// @dev AGNT token launch campaign unleash.
    /// @notice Make Agents.Fun Great Again
    /// Unleashes a new version of AGNT, called `AGNT II`, that has the same 
    /// LP setup (same amount of AGNT II and ETH), as the original AGN was meant to have.
    /// Hearters of the original AGNT now have 24 hours to collect their `AGNT II`.
    function _MAGA() private {

        // Get meme summon info
        MemeSummon storage memeSummon = memeSummons[launchCampaignNonce];

        _unleashThisMeme(launchCampaignNonce, memeSummon, LIQUIDITY_AGNT, CONTRIBUTION_AGNT, 0);

        // // Create a launch campaign token
        // address memeToken = _createThisMeme(launchCampaignNonce, memeSummon.name, memeSummon.symbol, memeSummon.totalSupply);

        // uint256 memeAmountForLP = (memeSummon.totalSupply * LP_PERCENTAGE) / 100;
        // uint256 heartersAmount = memeSummon.totalSupply - memeAmountForLP;

        // // Check for non-zero token address
        // require(memeToken != address(0), "Token creation failed");

        // // Record meme token address
        // memeTokenNonces[memeToken] = launchCampaignNonce;

        // // Create Uniswap pair with LP allocation
        // (uint256 positionId, uint256 liquidity, bool isNativeFirst) =
        //     _createUniswapPair(memeToken, LIQUIDITY_AGNT, memeAmountForLP);

        // // Push token into the global list of tokens
        // memeTokens.push(memeToken);
        // numTokens = memeTokens.length;

        // // Record the actual meme unleash time
        // memeSummon.unleashTime = block.timestamp;
        // // Record the hearters distribution amount for this meme
        // memeSummon.heartersAmount = heartersAmount;
        // // Record position token Id
        // memeSummon.positionId = positionId;
        // // Record token order in the pool
        // if (isNativeFirst) {
        //     memeSummon.isNativeFirst = isNativeFirst;
        // }

        // // Allocate to the token hearter unleashing the meme
        // uint256 hearterContribution = memeHearters[launchCampaignNonce][msg.sender];
        // if (hearterContribution > 0) {
        //     _collectMemeToken(memeToken, launchCampaignNonce, heartersAmount, hearterContribution,
        //         CONTRIBUTION_AGNT);
        // }

        // emit Unleashed(msg.sender, memeToken, positionId, liquidity, 0);
    }

    // /// @dev Allows diverting first x collected funds to a launch campaign.
    // /// @param nativeAmountForOLASBurn Amount of native token to conver to OLAS and burn.
    // /// @return adjustedNativeAmountForAscendance Adjusted amount of native token to conver to OLAS and burn.
    // function _updateLaunchCampaignBalance(uint256 nativeAmountForOLASBurn) internal override returns (uint256 adjustedNativeAmountForAscendance) {
    //     if (launchCampaignBalance < LIQUIDITY_AGNT) {
    //         // Get the difference of the required liquidity amount and launch campaign balance
    //         uint256 diff = LIQUIDITY_AGNT - launchCampaignBalance;
    //         // Take full nativeAmountForOLASBurn or a missing part to fulfil the launch campaign amount
    //         if (diff > nativeAmountForOLASBurn) {
    //             launchCampaignBalance += nativeAmountForOLASBurn;
    //             adjustedNativeAmountForAscendance = 0;
    //         } else {
    //             adjustedNativeAmountForAscendance = nativeAmountForOLASBurn - diff;
    //             launchCampaignBalance += diff;
    //         }
    //     }
    // }

    /// @dev Allows diverting first x collected funds to a launch campaign.
    /// @param amount Amount of native token to convert to OLAS and burn.
    /// @return adjustedAmount Adjusted amount of native token to convert to OLAS and burn.
    function _launchCampaign(uint256 amount) internal override returns (uint256 adjustedAmount) {
        // // Call MAGA if the balance has reached
        // if (launchCampaignBalance >= LIQUIDITY_AGNT && _launched == 0){
        _MAGA();
        adjustedAmount = amount - LIQUIDITY_AGNT;
        //     _launched = 1;
        // }
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
