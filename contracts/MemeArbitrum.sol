// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeBase, IERC20} from "./MemeBase.sol";

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

/// @title MemeArbitrum - a smart contract factory for Meme Token creation on Arbitrum.
contract MemeArbitrum is MemeBase {
    // OLAS address on L1
    address public immutable olasL1;

    /// @dev MemeArbitrum constructor.
    constructor(
        address _olasL2,
        address _usdc,
        address _router,
        address _factory,
        uint256 _minNativeTokenValue,
        address _weth,
        address _l2TokenRelayer,
        address _oracle,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) MemeBase(_olasL2, _usdc, _router, _factory, _minNativeTokenValue, _weth, _l2TokenRelayer, _oracle, _balancerVault,
        _balancerPoolId) {

        // Calculate OLAS L1 address
        uint160 offset = uint160(0x1111000000000000000000000000000000001111);
        unchecked {
            olasL1 = address(uint160(_olasL2) - offset);
        }
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

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).outboundTransfer(olasL1, OLAS_BURNER, olasAmount, "0x");

        emit OLASJourneyToAscendance(olas, olasAmount);

        return msg.value;
    }
}
