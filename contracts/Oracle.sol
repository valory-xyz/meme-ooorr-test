// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

// ERC20 interface
interface IERC20 {
	/// @dev Gets the amount of tokens owned by a specified account.
	/// @param account Account address.
	/// @return Amount of tokens owned.
	function balanceOf(address account) external view returns (uint256);
}

contract BalancerPriceGuard {
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
	// Maximum allowed update slippage in percentage
    uint256 public immutable maxSlippage;
	// Min Update time period
	uint256 public immutable minUpdateTimePeriod;

	address public immutable nativeToken;
	address public immutable olas;
	address public immutable pool;

    constructor(address _nativeToken, address _olas, address _pool, uint256 _maxSlippage, uint256 _minUpdateTimePeriod) {
        require(_maxSlippage <= 100, "Slippage must be <= 100%");

		nativeToken = _nativeToken;
		olas = _olas;
		pool = _pool;

		// Default slippage in basis points (e.g., 5 for 5%)
        maxSlippage = _maxSlippage;

		minUpdateTimePeriod = _minUpdateTimePeriod;

		updatePrice();
    }

	/// @dev Gets current OLAS token price in 1e18 format.
    function getPrice() public view returns (uint256) {
		uint256 balanceIn = IERC20(nativeToken).balanceOf(pool);
		uint256 balanceOut = IERC20(olas).balanceOf(pool);

    	// Simple ratio for weighted pools (replace with StableSwap formula for stable pools)
		return balanceOut * 1e18 / balanceIn;
    }	

	/// @dev Updates time average price.
    function updatePrice() public returns (bool) {
		uint256 currentPrice = getPrice();
		PriceSnapshot storage snapshot = snapshotHistory;

		// Check if update is too soon
		if (block.timestamp < snapshotHistory.lastUpdated + minUpdateTimePeriod) {
			return false;
		}

		// Check if price deviation is too high
		uint256 averagePrice = snapshot.averagePrice;
		if (currentPrice < averagePrice - (averagePrice * maxSlippage / 100) ||
			currentPrice > averagePrice + (averagePrice * maxSlippage / 100))
		{
			return false;
		}


		uint256 cumulativePrice = snapshot.cumulativePrice;
		if (snapshot.lastUpdated > 0) {
			// Calculate time-weighted average since the last update
			uint256 elapsedTime = block.timestamp - snapshot.lastUpdated;
			cumulativePrice += snapshot.averagePrice * elapsedTime;
			snapshot.cumulativePrice = cumulativePrice;
		}

		// Update the snapshot with the new price
		snapshot.averagePrice = currentPrice;
		snapshot.lastUpdated = block.timestamp;

		emit PriceUpdated(msg.sender, currentPrice, cumulativePrice);

		return true;
    }

	/// @dev Validates price according to slippage.
    function validatePrice(uint256 slippage) external view returns (bool) {
		if (slippage > 100) {
			return false;
		}

		PriceSnapshot memory snapshot = snapshotHistory;

		// Check for historical price availability
		if (snapshot.lastUpdated == 0) {
			return false;
		}

		uint256 elapsedTime = block.timestamp - snapshot.lastUpdated;
		uint256 timeWeightedAverage = (snapshot.cumulativePrice + snapshot.averagePrice * elapsedTime) / elapsedTime;

		uint256 tradePrice = getPrice();

		// Check if price is too low or too high
		if ((tradePrice < (timeWeightedAverage * (100 - slippage)) / 100) ||
			(tradePrice > (timeWeightedAverage * (100 + slippage)) / 100))
		{
			return false;
		}

		return true;
    }
}
