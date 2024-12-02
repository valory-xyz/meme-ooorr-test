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
    /// @dev Initiates a token withdrawal from Arbitrum to Ethereum
    /// @param l1Token L1 address of token.
    /// @param to Destination address.
    /// @param amount Amount of tokens withdrawn.
    /// @return Encoded Unique identifier for withdrawal.
    function outboundTransfer(
        address l1Token,
        address to,
        uint256 amount,
        bytes calldata data
    ) external payable returns (bytes memory);
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

// @title MemeArbitrum - a smart contract factory for Meme Token creation on Arbitrum.
contract MemeArbitrum is MemeFactory {
    // OLAS address on L1
    address public immutable olasL1;
    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Balancer Vault address
    address public immutable balancerVault;
    // Balancer Pool Id
    bytes32 public immutable balancerPoolId;

    /// @dev MemeArbitrum constructor
    constructor(
        FactoryParams memory factoryParams,
        address _l2TokenRelayer,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) MemeFactory(factoryParams) {
        l2TokenRelayer = _l2TokenRelayer;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;

        // Calculate OLAS L1 address
        uint160 offset = uint160(0x1111000000000000000000000000000000001111);
        unchecked {
            olasL1 = address(uint160(olas) - offset);
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
    /// @notice OLAS approve is not needed for the bridge since the bridge is the burner of L2 tokens by default.
    /// @param olasAmount OLAS amount.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(uint256 olasAmount, uint256, bytes memory)
        internal virtual override returns (uint256)
    {
        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).outboundTransfer(olasL1, OLAS_BURNER, olasAmount, "0x");

        emit OLASJourneyToAscendance(olas, olasAmount);

        return msg.value;
    }

    function _redemptionLogic(uint256) internal override {}

    function _wrap(uint256 nativeTokenAmount) internal virtual override {
        // Wrap ETH
        IWETH(nativeToken).deposit{value: nativeTokenAmount}();
    }
}
