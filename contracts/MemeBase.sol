// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory} from "./MemeFactory.sol";

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
}

interface IWETH {
    function deposit() external payable;
}

// Oracle interface
interface IOracle {
    /// @dev Gets latest round token price data.
    function latestRoundData()
        external returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Swaps exact amount of ETH for a specified token.
    function swapExactETHForTokens(uint256 amountOutMin, address[] calldata path, address to, uint256 deadline)
        external payable returns (uint256[] memory amounts);
}

/// @title MemeBase - a smart contract factory for Meme Token creation on Base.
contract MemeBase is MemeFactory {
    // Slippage parameter (3%)
    uint256 public constant SLIPPAGE = 3;
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;

    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Balancer Vault address
    address public immutable balancerVault;
    // Balancer Pool Id
    bytes32 public immutable balancerPoolId;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _weth,
        address _router,
        address _factory,
        uint256 _minNativeTokenValue,
        address _l2TokenRelayer,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) MemeFactory(_olas, _weth, _router, _factory, _minNativeTokenValue) {
        l2TokenRelayer = _l2TokenRelayer;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;
    }

    /// @dev Get safe slippage amount from dex.
    /// @return safe amount of tokens to swap on dex with low slippage.
    function _getLowSlippageSafeSwapAmount() internal virtual override returns (uint256) {
        /// check on three-sided USDC, ETH, OLAS pool for correct amount with max 3% slippage
        return 0;
    }


    /// @dev Buys OLAS on Balancer.
    /// @param nativeTokenAmount Native token amount.
    /// @param limit OLAS minimum amount depending on the desired slippage.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 nativeTokenAmount, uint256 limit) internal override returns (uint256) {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();

        // Approve usdc for the Balancer Vault
        IERC20(nativeToken).approve(balancerVault, nativeTokenAmount);
        
        // Prepare Balancer data for the three-sided USDC, ETH, OLAS pool
        IBalancer.SingleSwap memory singleSwap = IBalancer.SingleSwap(balancerPoolId, IBalancer.SwapKind.GIVEN_IN,
            nativeToken, olas, nativeTokenAmount, "0x");
        IBalancer.FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false,
            payable(address(this)), false);

        // Perform swap
        return IBalancer(balancerVault).swap(singleSwap, fundManagement, limit, block.timestamp);
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 olasAmount, uint256 tokenGasLimit, bytes memory) internal override returns (uint256) {
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
}
