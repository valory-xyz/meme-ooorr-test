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

    // Launch campaign token address
    address public launchCampaignTokenAddress;
    // Launch campaign balance
    uint256 public launchCampaignBalance;

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
            _launchCampaignSetup(accounts, amounts);
        }
    }

    /// @dev Launch campaign initialization function.
    /// @param accounts Original accounts.
    /// @param amounts Corresponding original amounts (without subtraction for burn).
    function _launchCampaignSetup(address[] memory accounts, uint256[] memory amounts) private {
        require(accounts.length == amounts.length);

        // Create a launch campaign token
        launchCampaignTokenAddress = address(new Meme("Agent Token II", "AGNT II", DECIMALS, 1_000_000_000 ether));

        // To match original summon events (purposefully placed here to match order of original events)
        emit Summoned(accounts[0], launchCampaignTokenAddress, amounts[0]);

        // Record all the accounts and amounts
        uint256 totalAmount;
        for (uint256 i = 0; i < accounts.length; ++i) {
            totalAmount += amounts[i];
            memeHearters[launchCampaignTokenAddress][accounts[i]] = amounts[i];
            // to match original hearter events
            emit Hearted(accounts[i], launchCampaignTokenAddress, amounts[i]);
        }
        require(totalAmount == CONTRIBUTION_AGNT, "Total amount must match original contribution amount");
        // Adjust amount for already collected burned tokens
        uint256 adjustedAmount = (totalAmount * 9) / 10;
        require(adjustedAmount == LIQUIDITY_AGNT, "Total amount adjusted for burn allocation must match liquidity amount");

        // summonTime is set to zero such that no one is able to heart this token
        memeSummons[launchCampaignTokenAddress] = MemeSummon(CONTRIBUTION_AGNT, 0, 0, 0, 0, false);

        // Push token into the global list of tokens
        memeTokens.push(launchCampaignTokenAddress);
        numTokens = memeTokens.length;
    }

    /// @dev AGNT token launch campaign unleash.
    function _MAGA() private { 
        Meme memeTokenInstance = Meme(launchCampaignTokenAddress);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 memeAmountForLP = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - memeAmountForLP;

        // Create Uniswap pair with LP allocation
        (uint256 positionId, uint256 liquidity, bool isNativeFirst) =
            _createUniswapPair(launchCampaignTokenAddress, LIQUIDITY_AGNT, memeAmountForLP);

        MemeSummon storage memeSummon = memeSummons[launchCampaignTokenAddress];

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;
        // Record position token Id
        memeSummon.positionId = positionId;
        // Record token order in the pool
        if (isNativeFirst) {
            memeSummon.isNativeFirst = isNativeFirst;
        }

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[launchCampaignTokenAddress][msg.sender];
        if (hearterContribution > 0) {
            _collect(launchCampaignTokenAddress, heartersAmount, hearterContribution, CONTRIBUTION_AGNT);
        }

        emit Unleashed(msg.sender, launchCampaignTokenAddress, positionId, liquidity, 0);
    }

    function _launchCampaign(uint256 nativeAmountForOLASBurn) internal override returns (uint256 adjustedNativeAmountForAscendance) {
        // Launch campaign logic:
        // Make Agents.Fun Great Again (MAGA)
        if (launchCampaignBalance < LIQUIDITY_AGNT) {
            // Get the difference of the required liquidity amount and launch campaign balance
            uint256 diff = LIQUIDITY_AGNT - launchCampaignBalance;
            // Take full nativeAmountForOLASBurn or a missing part to fulfil the launch campaign amount
            if (diff > nativeAmountForOLASBurn) {
                launchCampaignBalance += nativeAmountForOLASBurn;
                adjustedNativeAmountForAscendance = 0;
            } else {
                adjustedNativeAmountForAscendance = nativeAmountForOLASBurn - diff;
                launchCampaignBalance += diff;
            }

            // Call MAGA if the balance has reached
            if (launchCampaignBalance >= LIQUIDITY_AGNT) {
                _MAGA();
            }
        }
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
