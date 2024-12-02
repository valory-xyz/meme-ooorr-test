// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title PriceOracle - a generic smart contract oracle wrapper
abstract contract PriceOracle {
    event PriceUpdated(address indexed sender, uint256 currentPrice, uint256 cumulativePrice);

    struct PriceSnapshot {
        // Time-weighted cumulative price
        uint256 cumulativePrice;
        // Timestamp of the last update
        uint256 lastUpdated;
        // Most recent calculated average price
        uint256 averagePrice;
    }

    PriceSnapshot public snapshotHistory;
    // Maximum allowed update slippage in %
    uint256 public immutable maxSlippage;
    // Minimum update time period in seconds
    uint256 public immutable minUpdateTimePeriod;

    // LP token direction
    uint256 public immutable direction;
    // Native token (ERC-20) address
    address public immutable nativeToken;
    // OLAS token address
    address public immutable olas;

    constructor(
        address _olas,
        address _nativeToken,
        uint256 _maxSlippage,
        uint256 _minUpdateTimePeriod
    ) {
        require(_maxSlippage <= 100, "Slippage must be <= 100%");

        olas = _olas;
        nativeToken = _nativeToken;
        maxSlippage = _maxSlippage;
        minUpdateTimePeriod = _minUpdateTimePeriod;
    }

    /// @dev Gets the current OLAS token price in 1e18 format.
    function getPrice() public virtual view returns (uint256);

    /// @dev Updates the time-weighted average price.
    function updatePrice() public returns (bool) {
        uint256 currentPrice = getPrice();

        PriceSnapshot storage snapshot = snapshotHistory;

        if (snapshot.lastUpdated == 0) {
            // Initialize snapshot
            snapshot.cumulativePrice = 0;
            snapshot.averagePrice = currentPrice;
            snapshot.lastUpdated = block.timestamp;
            emit PriceUpdated(msg.sender, currentPrice, 0);
            return true;
        }

        // Check if update is too soon
        if (block.timestamp < snapshotHistory.lastUpdated + minUpdateTimePeriod) {
            return false;
        }

        // Calculate elapsed time since the last update
        uint256 elapsedTime = block.timestamp - snapshot.lastUpdated;

        // Update cumulative price with the previous average over the elapsed time
        snapshot.cumulativePrice += snapshot.averagePrice * elapsedTime;

        // Update the average price to reflect the current price
        uint256 averagePrice = (snapshot.cumulativePrice + (currentPrice * elapsedTime)) /
            ((snapshot.cumulativePrice / snapshot.averagePrice) + elapsedTime);

        // Check if price deviation is too high
        if (currentPrice < averagePrice - (averagePrice * maxSlippage / 100) ||
            currentPrice > averagePrice + (averagePrice * maxSlippage / 100))
        {
            return false;
        }

        snapshot.averagePrice = averagePrice;
        snapshot.lastUpdated = block.timestamp;

        emit PriceUpdated(msg.sender, currentPrice, snapshot.cumulativePrice);
        return true;
    }

    /// @dev Validates the price according to slippage tolerance.
    /// @param slippage the acceptable slippage tolerance
    function validatePrice(uint256 slippage) external view returns (bool) {
        require(slippage <= 100, "Slippage must be <= 100%");

        PriceSnapshot memory snapshot = snapshotHistory;

        // Ensure there is historical price data
        if (snapshot.lastUpdated == 0) return false;

        // Calculate elapsed time
        uint256 elapsedTime = block.timestamp - snapshot.lastUpdated;
        if (elapsedTime == 0) return false;

        // Compute time-weighted average price
        uint256 timeWeightedAverage = (snapshot.cumulativePrice + (snapshot.averagePrice * elapsedTime)) /
            ((snapshot.cumulativePrice / snapshot.averagePrice) + elapsedTime);

        uint256 tradePrice = getPrice();

        // Validate against slippage thresholds
        uint256 lowerBound = (timeWeightedAverage * (100 - slippage)) / 100;
        uint256 upperBound = (timeWeightedAverage * (100 + slippage)) / 100;

        return tradePrice >= lowerBound && tradePrice <= upperBound;
    }
}
