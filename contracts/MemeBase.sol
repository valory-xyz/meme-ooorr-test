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
    uint256 public constant SLIPPAGE = 97;
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;

    // WETH token address
    address public immutable weth;
    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Oracle address
    address public immutable oracle;
    // Balancer Vault address
    address public immutable balancerVault;
    // Balancer Pool Id
    bytes32 public immutable balancerPoolId;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _usdc,
        address _router,
        address _factory,
        uint256 _minNativeTokenValue,
        address _weth,
        address _l2TokenRelayer,
        address _oracle,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) MemeFactory(_olas, _usdc, _router, _factory, _minNativeTokenValue) {
        weth = _weth;
        l2TokenRelayer = _l2TokenRelayer;
        oracle = _oracle;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;
    }

    /// @dev Buys USDC on UniswapV2 using ETH amount.
    /// @param nativeTokenAmount Input ETH amount.
    /// @return Stable token amount bought.
    function _convertToReferenceToken(uint256 nativeTokenAmount, uint256) internal override returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = referenceToken;

        // Calculate price by Oracle
        (, int256 answerPrice, , , ) = IOracle(oracle).latestRoundData();
        require(answerPrice > 0, "Oracle price is incorrect");

        // Oracle returns 8 decimals, USDC has 6 decimals, need to additionally divide by 100 to account for slippage
        // ETH: 18 decimals, USDC leftovers: 2 decimals, percentage: 2 decimals; denominator = 18 + 2 + 2 = 22
        uint256 limit = uint256(answerPrice) * nativeTokenAmount * SLIPPAGE / 1e22;
        // Swap ETH for USDC
        uint256[] memory amounts = IUniswap(router).swapExactETHForTokens{ value: nativeTokenAmount }(
            limit,
            path,
            address(this),
            block.timestamp
        );

        // Return the USDC amount bought
        return amounts[1];
    }

    /// @dev Buys OLAS on Balancer.
    /// @param referenceTokenAmount USDC amount.
    /// @param limit OLAS minimum amount depending on the desired slippage.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 referenceTokenAmount, uint256 limit) internal override returns (uint256) {
        // Approve usdc for the Balancer Vault
        IERC20(referenceToken).approve(balancerVault, referenceTokenAmount);

        // Prepare Balancer data
        IBalancer.SingleSwap memory singleSwap = IBalancer.SingleSwap(balancerPoolId, IBalancer.SwapKind.GIVEN_IN, referenceToken,
            olas, referenceTokenAmount, "0x");
        IBalancer.FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false,
            payable(address(this)), false);

        // Perform swap
        return IBalancer(balancerVault).swap(singleSwap, fundManagement, limit, block.timestamp);
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param OLASAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 OLASAmount, uint256 tokenGasLimit, bytes memory) internal override returns (uint256) {
        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, OLASAmount);

        // Check for sufficient minimum gas limit
        if (tokenGasLimit < TOKEN_GAS_LIMIT) {
            tokenGasLimit = TOKEN_GAS_LIMIT;
        }

        // Data for the mainnet validate the OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", OLASAmount);

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).withdrawTo(olas, OLAS_BURNER, OLASAmount, uint32(tokenGasLimit), data);

        emit OLASJourneyToAscendance(olas, OLASAmount);

        return msg.value;
    }
}
