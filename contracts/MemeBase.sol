// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory, Meme} from "./MemeFactory.sol";

interface IWETH {
    function deposit() external payable;
}

/// @title MemeBase - a smart contract factory for Meme Token creation on Base.
contract MemeBase is MemeFactory {
    // AGNT redemption amount as per:
    // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F17
    // Previous token address: 0x7484a9fB40b16c4DFE9195Da399e808aa45E9BB9
    // Full collected amount: 141569842100000000000
    uint256 public constant CONTRIBUTION_AGNT = 141569842100000000000;
    // Redemption amount: collected amount - 10% for burn = 127412857890000000000
    uint256 public constant REDEMPTION_AMOUNT = 127412857890000000000;

    // Balancer Vault address
    address public immutable balancerVault;
    // Balancer Pool Id
    bytes32 public immutable balancerPoolId;

    // Redemption token address
    address public redemptionAddress;
    // Redemption balance
    uint256 public redemptionBalance;

    /// @dev MemeBase constructor
    constructor(
        FactoryParams memory factoryParams,
        address _balancerVault,
        bytes32 _balancerPoolId,
        address[] memory accounts,
        uint256[] memory amounts
    ) MemeFactory(factoryParams) {
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;

        if (accounts.length > 0) {
            _redemptionSetup(accounts, amounts);
        }
    }

    /// @dev Redemption initialization function.
    /// @param accounts Original accounts.
    /// @param amounts Corresponding original amounts (without subtraction for burn).
    function _redemptionSetup(address[] memory accounts, uint256[] memory amounts) private {
        require(accounts.length == amounts.length);

        // Create a redemption token
        redemptionAddress = address(new Meme("Agent Token II", "AGNT II", DECIMALS, 1_000_000_000 ether));

        // To match original summon events (purposefully placed here to match order of original events)
        emit Summoned(accounts[0], redemptionAddress, amounts[0]);

        // Record all the accounts and amounts
        uint256 totalAmount;
        for (uint256 i = 0; i < accounts.length; ++i) {
            totalAmount += amounts[i];
            memeHearters[redemptionAddress][accounts[i]] = amounts[i];
            // to match original hearter events
            emit Hearted(accounts[i], redemptionAddress, amounts[i]);
        }
        require(totalAmount == CONTRIBUTION_AGNT, "Total amount must match original contribution amount");
        // Adjust amount for already collected burned tokens
        uint256 adjustedAmount = (totalAmount * 9) / 10;
        require(adjustedAmount == REDEMPTION_AMOUNT, "Total amount adjusted for burn allocation must match redemption amount");

        // summonTime is set to zero such that no one is able to heart this token
        memeSummons[redemptionAddress] = MemeSummon(CONTRIBUTION_AGNT, 0, 0, 0, 0);

        // Push token into the global list of tokens
        memeTokens.push(redemptionAddress);
        numTokens = memeTokens.length;
    }

    /// @dev AGNT token redemption unleash.
    function _redemption() private { 
        Meme memeTokenInstance = Meme(redemptionAddress);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 memeAmountForLP = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - memeAmountForLP;

        // Wrap native token to its ERC-20 version, where applicable
        _wrap(REDEMPTION_AMOUNT);

        // Create Uniswap pair with LP allocation
        (uint256 positionId, uint256 liquidity) = _createUniswapPair(redemptionAddress, REDEMPTION_AMOUNT, memeAmountForLP);

        MemeSummon storage memeSummon = memeSummons[redemptionAddress];

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;
        // Record position token Id
        memeSummon.positionId = positionId;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[redemptionAddress][msg.sender];
        if (hearterContribution > 0) {
            _collect(redemptionAddress, heartersAmount, hearterContribution, CONTRIBUTION_AGNT);
        }

        emit Unleashed(msg.sender, redemptionAddress, positionId, liquidity, 0);
    }

    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal override returns (uint256 adjustedNativeAmountForAscendance) {
        // Redemption collection logic
        if (redemptionBalance < REDEMPTION_AMOUNT) {
            // Get the difference of the required redemption amount and redemption balance
            uint256 diff = REDEMPTION_AMOUNT - redemptionBalance;
            // Take full nativeAmountForOLASBurn or a missing part to fulfil the redemption amount
            if (diff > nativeAmountForOLASBurn) {
                redemptionBalance += nativeAmountForOLASBurn;
                adjustedNativeAmountForAscendance = 0;
            } else {
                adjustedNativeAmountForAscendance = nativeAmountForOLASBurn - diff;
                redemptionBalance += diff;
            }

            // Call redemption if the balance has reached
            if (redemptionBalance >= REDEMPTION_AMOUNT) {
                _redemption();
            }
        }
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
