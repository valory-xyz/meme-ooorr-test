// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeFactory, IOracle} from "./MemeFactory.sol";

// Bridge interface
interface IBridge {
    /// @dev Transfers tokens through Wormhole portal.
    function transferTokens(
        address token,
        uint256 amount,
        uint16 recipientChain,
        bytes32 recipient,
        uint256 arbiterFee,
        uint32 nonce
    ) external payable returns (uint64 sequence);
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Swaps exact amount of ETH for a specified token.
    function swapExactTokensForTokens(uint256 amountOutMin, address[] calldata path, address to, uint256 deadline)
        external payable returns (uint256[] memory amounts);

    /// @dev Swaps an exact amount of input tokens along the route determined by the path. 
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

/// @title MemeCelo - a smart contract factory for Meme Token creation on Celo.
contract MemeCelo is MemeFactory {
    // Wormhole bridging decimals cutoff
    uint256 public constant WORMHOLE_BRIDGING_CUTOFF = 1e10;
    // Ethereum mainnet chain Id in Wormhole format
    uint16 public constant WORMHOLE_ETH_CHAIN_ID = 2;

    // CELO token address
    address public immutable celo;
    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Ubeswap router address
    address public immutable router;

    // Contract nonce
    uint256 public nonce;
    // OLAS leftovers from bridging
    uint256 public olasLeftovers;

    /// @dev MemeBase constructor
    constructor(
        FactoryParams memory factoryParams,
        address _l2TokenRelayer,
        address _router
    ) MemeFactory(factoryParams) {
        l2TokenRelayer = _l2TokenRelayer;
        router = _router;
    }

    /// @dev Buys OLAS on UniswapV2.
    /// @param nativeTokenAmount CELO amount.
    /// @param slippage Slippage value.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 nativeTokenAmount, uint256 slippage) internal virtual override returns (uint256) {
        // Apply slippage protection
        require(IOracle(oracle).validatePrice(slippage), "Slippage limit is breached");

        address[] memory path = new address[](3);
        path[0] = nativeToken;
        path[1] = olas;

        // Approve native token
        IERC20(nativeToken).approve(router, nativeTokenAmount);

        // Swap cUSD for OLAS
        // This will go via two pools - not a problem as Ubeswap has both
        uint256[] memory amounts = IUniswap(router).swapExactTokensForTokens(
            nativeTokenAmount,
            0,
            path,
            address(this),
            block.timestamp
        );

        // Return the OLAS amount bought
        return amounts[1];
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param olasAmount OLAS amount.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 olasAmount, uint256, bytes memory) internal virtual override returns (uint256) {
        // Get OLAS leftovers from previous transfers and adjust the amount to transfer
        olasAmount += olasLeftovers;

        // Round transfer amount to the cutoff value
        uint256 transferAmount = olasAmount / WORMHOLE_BRIDGING_CUTOFF;
        transferAmount *= WORMHOLE_BRIDGING_CUTOFF;

        // Check for zero value
        require(transferAmount > 0, "Amount is too small for bridging");

        // Update OLAS leftovers
        olasLeftovers = olasAmount - transferAmount;

        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, transferAmount);

        // Bridge arguments
        bytes32 olasBurner = bytes32(uint256(uint160(OLAS_BURNER)));
        uint256 localNonce = nonce;

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).transferTokens(olas, transferAmount, WORMHOLE_ETH_CHAIN_ID, olasBurner, 0, uint32(nonce));

        // Adjust nonce
        nonce = localNonce + 1;

        emit OLASJourneyToAscendance(olas, transferAmount);

        return msg.value;
    }

    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal override pure returns (uint256) {
        return nativeAmountForOLASBurn;
    }

    function _wrap(uint256) internal virtual override {}
}
