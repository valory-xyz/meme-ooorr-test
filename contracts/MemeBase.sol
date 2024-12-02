// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory, Meme} from "./MemeFactory.sol";

// Balancer interface
interface IBalancer {
    enum SwapKind { GIVEN_IN, GIVEN_OUT }

    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    /// @dev Swaps tokens on Balancer.
    function swap(SingleSwap memory singleSwap, FundManagement memory funds, uint256 limit, uint256 deadline)
        external payable returns (uint256);
}

// Bridge interface
interface IBridge {
    /// @dev Initiates a withdrawal from L2 to L1 to a target account on L1.
    /// @param l2Token Address of the L2 token to withdraw.
    /// @param to Recipient account on L1.
    /// @param amount Amount of the L2 token to withdraw.
    /// @param minGasLimit Minimum gas limit to use for the transaction.
    /// @param extraData Extra data attached to the withdrawal.
    function withdrawTo(address l2Token, address to, uint256 amount, uint32 minGasLimit, bytes calldata extraData) external;
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);

    function totalSupply() external returns (uint256);

    function decimals() external returns (uint8);
}

// Redemption MemeBase interface
interface IMemeBase {
    function memeTokens(uint256) external returns (address);
    function memeSummons(address) external returns (MemeFactory.MemeSummon memory);
    function LP_PERCENTAGE() external returns (uint256);
}

interface IWETH {
    function deposit() external payable;
}

/// @title MemeBase - a smart contract factory for Meme Token creation on Base.
contract MemeBase is MemeFactory {
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;

    // AGNT redemption amount as per:
    // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F17
    // Previous token address: 0x7484a9fB40b16c4DFE9195Da399e808aa45E9BB9
    // Full collected amount: 141569842100000000000
    uint256 public immutable contributionAGNT;
    // Redemption amount: collected amount - 10% for burn = 127412857890000000000
    uint256 public immutable redemptionAmount;
    // Redemption MemeBase address
    address public immutable redemptionMemeBase;

    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
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
        address _l2TokenRelayer,
        address _balancerVault,
        bytes32 _balancerPoolId,
        address _redemptionMemeBase,
        uint256 _redemptionTokenIdx,
        string memory redemptionName,
        string memory redemptionSymbol,
        address[] memory accounts,
        uint256[] memory amounts
    ) MemeFactory(factoryParams) {
        l2TokenRelayer = _l2TokenRelayer;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;

        if (accounts.length > 0) {
            redemptionMemeBase = _redemptionMemeBase;

            // Old AGNT token is the 4th in the global list of old MemeBase tokens
            // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F18
            // Previous token address: 0x7484a9fB40b16c4DFE9195Da399e808aa45E9BB9
            address redemptionMemeToken = IMemeBase(_redemptionMemeBase).memeTokens(_redemptionTokenIdx);

            // Full collected AGNT amount: 141569842100000000000
            // https://basescan.org/address/0x42156841253f428cb644ea1230d4fddfb70f8891#readContract#F17
            MemeFactory.MemeSummon memory memeSummon = IMemeBase(_redemptionMemeBase).memeSummons(redemptionMemeToken);
            contributionAGNT = memeSummon.nativeTokenContributed;

            // Redemption amount: collected amount - 10% for burn = 127412857890000000000
            redemptionAmount = contributionAGNT * 9 / 10;

            // Set up redemption procedure
            uint8 decimals = IERC20(redemptionMemeToken).decimals();
            // Half of the supply has been burnt, thus it needs to be increased
            uint256 totalSupply = 2 * IERC20(redemptionMemeToken).totalSupply();
            // This is a required check if any accounts burns tokens as well
            require(totalSupply == 1_000_000_000 ether, "Total supply has changed");

            _redemptionSetup(redemptionName, redemptionSymbol, decimals, totalSupply, accounts, amounts);
        }
    }

    /// @dev Buys OLAS on Balancer.
    /// @param nativeTokenAmount Native token amount.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 nativeTokenAmount) internal virtual override returns (uint256) {
        // Approve weth for the Balancer Vault
        IERC20(nativeToken).approve(balancerVault, nativeTokenAmount);
        
        // Prepare Balancer data for the WETH-OLAS pool
        IBalancer.SingleSwap memory singleSwap = IBalancer.SingleSwap(balancerPoolId, IBalancer.SwapKind.GIVEN_IN,
            nativeToken, olas, nativeTokenAmount, "0x");
        IBalancer.FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false,
            payable(address(this)), false);

        // Perform swap
        return IBalancer(balancerVault).swap(singleSwap, fundManagement, 0, block.timestamp);
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 olasAmount, uint256 tokenGasLimit, bytes memory)
        internal virtual override returns (uint256)
    {
        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, olasAmount);

        // Check for sufficient minimum gas limit
        if (tokenGasLimit < TOKEN_GAS_LIMIT) {
            tokenGasLimit = TOKEN_GAS_LIMIT;
        }

        // Data for the mainnet validate the OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", olasAmount);

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).withdrawTo(olas, OLAS_BURNER, olasAmount, uint32(tokenGasLimit), data);

        emit OLASJourneyToAscendance(olas, olasAmount);

        return msg.value;
    }

    /// @dev Redemption initialization function.
    /// @param accounts Original accounts.
    /// @param amounts Corresponding original amounts (without subtraction for burn).
    function _redemptionSetup(
        string memory redemptionName,
        string memory redemptionSymbol,
        uint8 decimals,
        uint256 totalSupply,
        address[] memory accounts,
        uint256[] memory amounts
    ) private {
        require(accounts.length == amounts.length);

        // Create a redemption token
        redemptionAddress = address(new Meme(redemptionName, redemptionSymbol, decimals, totalSupply));

        // Record all the accounts and amounts
        uint256 totalAmount;
        for (uint256 i = 0; i < accounts.length; ++i) {
            totalAmount += amounts[i];
            memeHearters[redemptionAddress][accounts[i]] = amounts[i];
            // to match original hearter events
            emit Hearted(accounts[i], redemptionAddress, amounts[i]);
        }
        require(totalAmount == contributionAGNT, "Total amount must match original contribution amount");
        // Adjust amount for already collected burned tokens
        uint256 adjustedAmount = (totalAmount * 9) / 10;
        require(adjustedAmount == redemptionAmount, "Total amount adjusted for burn allocation must match redemption amount");

        // summonTime is set to zero such that no one is able to heart this token
        memeSummons[redemptionAddress] = MemeSummon(contributionAGNT, 0, 0, 0);

        // Push token into the global list of tokens
        memeTokens.push(redemptionAddress);
        numTokens = memeTokens.length;

        // To match original summon events
        emit Summoned(accounts[0], redemptionAddress, amounts[0]);
    }

    /// @dev AGNT token redemption unleash.
    function _redemption() private {
        Meme memeTokenInstance = Meme(redemptionAddress);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 memeAmountForLP = (totalSupply * IMemeBase(redemptionMemeBase).LP_PERCENTAGE()) / 100;
        uint256 heartersAmount = totalSupply - memeAmountForLP;

        // Create Uniswap pair with LP allocation
        (address pool, uint256 liquidity) = _createUniswapPair(redemptionAddress, redemptionAmount, memeAmountForLP);

        MemeSummon storage memeSummon = memeSummons[redemptionAddress];

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[redemptionAddress][msg.sender];
        if (hearterContribution > 0) {
            _collect(redemptionAddress, hearterContribution, heartersAmount, contributionAGNT);
        }

        emit Unleashed(msg.sender, redemptionAddress, pool, liquidity, 0);
    }

    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal override {
        // Redemption collection logic
        if (redemptionBalance < redemptionAmount) {
            // Get the difference of the required redemption amount and redemption balance
            uint256 diff = redemptionAmount - redemptionBalance;
            // Take full nativeAmountForOLASBurn or a missing part to fulfil the redemption amount
            if (diff > nativeAmountForOLASBurn) {
                redemptionBalance += nativeAmountForOLASBurn;
                nativeAmountForOLASBurn = 0;
            } else {
                nativeAmountForOLASBurn -= diff;
                redemptionBalance += diff;
            }

            // Call redemption if the balance has reached
            if (redemptionBalance >= redemptionAmount) {
                _redemption();
            }
        }
    }

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
