// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {PriceOracle} from "./PriceOracle.sol";

interface IUniswapV2 {
    function token0() external view returns (address);
    function getReserves() external view returns (uint112 _reserve0, uint112 _reserve1, uint32 _blockTimestampLast);
}

/// @title UniPriceOracle - a smart contract oracle wrapper for Uni V2 pools
/// @dev This contract acts as an oracle wrapper for a specific Uni V2 pool. It allows:
///      1) Getting the price by any caller
///      2) Validating slippage against the oracle
contract UniPriceOracle is PriceOracle {
    // LP token address
    address public immutable pair;

    constructor(
        address _olas,
        address _nativeToken,
        uint256 _maxSlippage,
        uint256 _minUpdateTimePeriod,
        address _pair
    )
        PriceOracle(_olas, _nativeToken, _maxSlippage, _minUpdateTimePeriod)
    {
        pair = _pair;

        // Get token direction
        address token0 =  IUniswapV2(pair).token0();
        if (token0 != _nativeToken) {
            direction = 1;
        }

        // Initialize price snapshot
        updatePrice();
    }

    /// @dev Gets the current OLAS token price in 1e18 format.
    function getPrice() public virtual override view returns (uint256) {
        uint256[] memory balances = new uint256[](2);
        (balances[0], balances[1], ) = IUniswapV2(pair).getReserves();
        // Native token
        uint256 balanceIn = balances[direction];
        // OLAS
        uint256 balanceOut = balances[(direction + 1) % 2];

        return (balanceOut * 1e18) / balanceIn;
    }
}
