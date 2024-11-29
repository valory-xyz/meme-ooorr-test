// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract BalancerPriceGuard {
    struct PriceSnapshot {
	    uint256 cumulativePrice; // Time-weighted cumulative price
    	    uint256 lastUpdated;     // Timestamp of the last update
            uint256 averagePrice;    // Most recent calculated average price
    }

    PriceSnapshot public snapshotHistory;
    uint256 public constant maxSlippageUpdate = 10; // Maximum allowed update slippage in percentage

    constructor(uint256 _maxSlippageUpdate) {
        require(_maxSlippage <= 10000, "Slippage must be <= 100%");
        maxSlippageUpdate = _maxSlippageUpdate; // Default slippage in basis points (e.g., 500 for 5%)
	updatePrice(pool, tokenIn, tokenOut); // trusted update 
    }


    function getPrice(address pool, address tokenIn, address tokenOut) public view returns (uint256) {
    	uint256 balanceIn = IERC20(tokenIn).balanceOf(pool);
    	uint256 balanceOut = IERC20(tokenOut).balanceOf(pool);

    	// Simple ratio for weighted pools (replace with StableSwap formula for stable pools)
    	return balanceOut / balanceIn;
    }	

    function updatePrice(address pool, address tokenIn, address tokenOut) external {
	require(block.timestamp >= lastUpdateTime + 15 minutes, "Update too soon");
    	uint256 currentPrice = getPrice(pool, tokenIn, tokenOut);
    	uint256 currentTime = block.timestamp;
	PriceSnapshot storage snapshot = snapshotHistory;
	
	require(
                currentPrice <= snapshot.averagePrice + (snapshot.averagePrice * maxSlippageUpdate / 10000) &&
                currentPrice >= snapshot.averagePrice - (snapshot.averagePrice * maxSlippageUpdate / 10000),
                "Price deviation too high"
                );

	if (snapshot.lastUpdated > 0) {
        	// Calculate time-weighted average since the last update
        	uint256 elapsedTime = currentTime - snapshot.lastUpdated;
        	snapshot.cumulativePrice += snapshot.averagePrice * elapsedTime;
    	}

    	// Update the snapshot with the new price
    	snapshot.averagePrice = currentPrice;
    	snapshot.lastUpdated = currentTime;
	
	// Events

    }


    function validateTrade(
	address pool,
    	address tokenIn,
    	address tokenOut,
    	uint256 maxSlippage
    ) external view returns (bool) {
	PriceSnapshot memory snapshot = snapshotHistory;
	require(snapshot.lastUpdated > 0, "No historical price available");
	
	uint256 elapsedTime = block.timestamp - snapshot.lastUpdated;
    	uint256 timeWeightedAverage = (snapshot.cumulativePrice + snapshot.averagePrice * elapsedTime) / elapsedTime;

	slippageBorderMin = (10000 - maxSlippage)/10000; // 95
	slippageBorderMax = (10000 + maxSlippage)/10000; // 105
    	require(tradePrice >= (timeWeightedAverage * slippageBorderMin) / 100, "Price too low");
    	require(tradePrice <= (timeWeightedAverage * slippageBorderMax) / 100, "Price too high");

    }
}
