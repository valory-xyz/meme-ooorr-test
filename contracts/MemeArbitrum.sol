// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MemeBase} from "./MemeBase.sol";

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
}
