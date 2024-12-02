// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {PriceOracle} from "./PriceOracle.sol";

interface IVault {
    function getPoolTokens(bytes32 poolId) external view
        returns (address[] memory tokens, uint256[] memory balances, uint256 lastChangeBlock);
}

/// @title BalancerPriceOracle - a smart contract oracle for Balancer V2 pools
/// @dev This contract acts as an oracle for a specific Balancer V2 pool. It allows:
///      1) Updating the price by any caller
///      2) Getting the price by any caller
///      3) Validating slippage against the oracle
contract BalancerPriceOracle is PriceOracle {
    // Balancer vault address
    address public immutable balancerVault;
    // Balancer pool Id
    bytes32 public immutable balancerPoolId;

    constructor(
        address _olas,
        address _nativeToken,
        uint256 _maxSlippage,
        uint256 _minUpdateTimePeriod,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) PriceOracle(_olas, _nativeToken, _maxSlippage, _minUpdateTimePeriod)
    {
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;

        // Get token direction
        (address[] memory tokens, , ) = IVault(balancerVault).getPoolTokens(_balancerPoolId);
        if (tokens[0] != _nativeToken) {
            direction = 1;
        }

        // Initialize price snapshot
        updatePrice();
    }

    /// @dev Gets the current OLAS token price in 1e18 format.
    function getPrice() public virtual override view returns (uint256) {
        (, uint256[] memory balances, ) = IVault(balancerVault).getPoolTokens(balancerPoolId);
        // Native token
        uint256 balanceIn = balances[direction];
        // OLAS
        uint256 balanceOut = balances[(direction + 1) % 2];

        return (balanceOut * 1e18) / balanceIn;
    }
}
