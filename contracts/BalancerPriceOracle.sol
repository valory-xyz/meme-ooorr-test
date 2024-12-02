// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;
import "hardhat/console.sol";
// improved with ChatGPT 4o mini

// ERC20 interface
interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
}

interface IVault {
    function getPoolTokens(bytes32 poolId)
        external
        view
        returns (address[] memory tokens, uint256[] memory balances, uint256 lastChangeBlock);
}

/// @title BalancerPriceOracle - a smart contract oracle for Balancer V2 pools
/// @dev This contract acts as an oracle for a specific Balancer V2 pool. It allows:
///      1) Updating the price by any caller
///      2) Getting the price by any caller
///      3) Validating slippage against the oracle
contract BalancerPriceOracle {
    event PriceUpdated(address indexed sender, uint256 currentPrice, uint256 cumulativePrice);

    struct PriceSnapshot {
        uint256 cumulativePrice; // Time-weighted cumulative price
        uint256 lastUpdated;     // Timestamp of the last update
        uint256 averagePrice;    // Most recent calculated average price
    }

    PriceSnapshot public snapshotHistory;
    // Maximum allowed update slippage in %
    uint256 public immutable maxSlippage;
    // Minimum update time period in seconds
    uint256 public immutable minUpdateTimePeriod;

    address public immutable nativeToken;
    address public immutable olas;
    address public immutable balancerVault;
    bytes32 public immutable balancerPoolId;

    constructor(
        address _olas,
        address _nativeToken,
        address _balancerVault,
        bytes32 _balancerPoolId,
        uint256 _maxSlippage,
        uint256 _minUpdateTimePeriod
    ) {
        require(_maxSlippage <= 100, "Slippage must be <= 100%");
        olas = _olas;
        nativeToken = _nativeToken;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;
        maxSlippage = _maxSlippage;
        minUpdateTimePeriod = _minUpdateTimePeriod;

        updatePrice(); // Initialize price snapshot
    }

    /// @dev Gets the current OLAS token price in 1e18 format.
    function getPrice() public view returns (uint256) {
        (, uint256[] memory balances, ) = IVault(balancerVault).getPoolTokens(balancerPoolId);
        uint256 balanceIn = balances[0]; // WETH
        uint256 balanceOut = balances[1]; // OLAS
        return (balanceOut * 1e18) / balanceIn;
    }

    /// @dev Updates the time-weighted average price.
    function updatePrice() public returns (bool) {
        uint256 currentPrice = getPrice();
        console.log("---------------- updatePrice()  --------------");
        console.log("Current price:", currentPrice);

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

        console.log("Time-weighted average price:", timeWeightedAverage);

        uint256 tradePrice = getPrice();
        console.log("Current trade price:", tradePrice);

        // Validate against slippage thresholds
        uint256 lowerBound = (timeWeightedAverage * (100 - slippage)) / 100;
        uint256 upperBound = (timeWeightedAverage * (100 + slippage)) / 100;

        console.log("lowerBound:", lowerBound);
        console.log("upperBound:", upperBound);

        return tradePrice >= lowerBound && tradePrice <= upperBound;
    }
}
