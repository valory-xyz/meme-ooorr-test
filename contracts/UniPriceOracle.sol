// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title UniPriceOracle - a smart contract oracle wrapper for Uni V2 pools
/// @dev This contract acts as an oracle wrapper for a specific Uni V2 pool. It allows:
///      1) Getting the price by any caller
///      2) Validating slippage against the oracle
contract UniPriceOracle {
    uint256 public immutable maxSlippage;          // Maximum allowed update slippage in %
    uint256 public immutable minUpdateTimePeriod;  // Minimum update time period in seconds

    address public immutable nativeToken;
    address public immutable olas;

    constructor(
        address _olas,
        address _nativeToken,
        uint256 _maxSlippage
    ) {
        require(_maxSlippage <= 100, "Slippage must be <= 100%");
        olas = _olas;
        nativeToken = _nativeToken;
        maxSlippage = _maxSlippage;
    }

    /// @dev Gets the current OLAS token price in 1e18 format.
    function getPrice() public view returns (uint256) {
        // TODO
    }

    /// @dev Updates the time-weighted average price.
    /// @notice not implemented for uniswap as they maintain their own oracle
    function updatePrice() public returns (bool) {
        return true;
    }

    /// @dev Validates the price according to slippage tolerance.
    /// @param slippage the acceptable slippage tolerance
    function validatePrice(uint256 slippage) external view returns (bool) {
        require(slippage <= 100, "Slippage must be <= 100%");

        // TODO
    }
}
