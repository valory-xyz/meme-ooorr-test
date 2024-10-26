// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CustomERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";

contract MemeBase {
    address public olasAddress; // Address of OLAS token
    address public uniswapV2Router;
    address public uniswapV2Factory;
    address public rollupBridge;

    uint256 public burnPercentage = 10; // Percentage of OLAS to burn (10%)
    uint256 public lpPercentage = 10;   // Percentage of initial supply for liquidity pool (10%)

    uint256 public scheduledBurnAmount;
    uint256 public totalETHReceived;

    mapping(address => uint256) public userEthDeposits;

    event TokenDeployed(address tokenAddress, address deployer, uint256 lpTokens, address lpPool);
    event OLASScheduledForBurn(uint256 amount);
    event OLASBridgedForBurn(uint256 amount);
    event DiceRolled(address indexed user, uint256 amount);

    constructor(address _olasAddress, address _uniswapV2Router, address _uniswapV2Factory, address _rollupBridge) {
        olasAddress = _olasAddress;
        uniswapV2Router = _uniswapV2Router;
        uniswapV2Factory = _uniswapV2Factory;
        rollupBridge = _rollupBridge;
    }

    function deploy(
        string memory name_,
        string memory symbol_
    ) external payable {
        require(msg.value > 0, "ETH required to deploy");

        // Generate a random total supply between 1 million and 21 million
        uint256 totalSupply_ = _generateRandomSupply();

        // Buy OLAS from Uniswap with 100% of the sent ETH
        uint256 olasAmount = _buyOLAS(msg.value);

        // Schedule 10% of OLAS for burning
        uint256 burnAmount = (olasAmount * burnPercentage) / 100;
        _scheduleBurn(burnAmount);

        // Distribute the remaining OLAS to LP
        uint256 lpOLASAmount = olasAmount - burnAmount;

        // Calculate LP token allocation (10% of total supply)
        uint256 lpNewTokenAmount = (totalSupply_ * lpPercentage) / 100;

        // Deploy new ERC20 token
        CustomERC20 newToken = new CustomERC20(name_, symbol_, totalSupply_);

        // Mint 1% of the supply to the deployer
        uint256 deployerAllocation = (totalSupply_ * 1) / 100;
        newToken.mint(msg.sender, deployerAllocation);

        // Mint 10% to LP pool and create the Uniswap pair
        _createUniswapPair(address(newToken), lpOLASAmount, lpNewTokenAmount);

        // Distribute remaining 89% of the supply to the top 1,000 users in `userEthDeposits`
        _distributeToTopDepositors(address(newToken), totalSupply_ - deployerAllocation - lpNewTokenAmount);

        emit TokenDeployed(address(newToken), msg.sender, lpNewTokenAmount, address(uniswapV2Factory));
    }

    function _distributeToTopDepositors(address tokenAddress, uint256 totalDistributionAmount) internal {
        // Step 1: Gather top 1,000 depositors based on their ETH deposits
        address[] memory topDepositors = _getTopDepositors(1000);

        uint256 totalDeposits;
        uint256[] memory weights = new uint256[](topDepositors.length);

        // Step 2: Calculate the weight for each depositor based on their ETH deposit
        for (uint256 i = 0; i < topDepositors.length; i++) {
            uint256 deposit = userEthDeposits[topDepositors[i]];
            weights[i] = deposit;
            totalDeposits += deposit;
        }

        // Step 3: Distribute tokens to top depositors with positive but non-proportional weighting
        for (uint256 i = 0; i < topDepositors.length; i++) {
            uint256 allocation = (totalDistributionAmount * weights[i]) / (totalDeposits + weights[i] / 2); // Adjust the weight for non-proportional distribution
            IERC20(tokenAddress).transfer(topDepositors[i], allocation);
        }
    }

    function _getTopDepositors(uint256 limit) internal view returns (address[] memory) {
        address[] memory topDepositors = new address[](limit);
        uint256[] memory topDeposits = new uint256[](limit);

        // Populate topDepositors based on the ETH deposits
        for (uint256 i = 0; i < limit; i++) {
            uint256 maxDeposit = 0;
            address maxAddress;

            // Find the maximum depositor not yet in the topDepositors array
            for (address user in userEthDeposits) {
                if (userEthDeposits[user] > maxDeposit && !_isInTopDepositors(user, topDepositors)) {
                    maxDeposit = userEthDeposits[user];
                    maxAddress = user;
                }
            }
            // Add the user to the top depositors
            topDepositors[i] = maxAddress;
            topDeposits[i] = maxDeposit;
        }
        return topDepositors;
    }

    function _isInTopDepositors(address user, address[] memory topDepositors) internal pure returns (bool) {
        for (uint256 i = 0; i < topDepositors.length; i++) {
            if (topDepositors[i] == user) {
                return true;
            }
        }
        return false;
    }

    function _generateRandomSupply() internal view returns (uint256) {
        // Define the minimum and maximum supply values
        uint256 minSupply = 1_000_000 * 10**18; // 1 million tokens, scaled to 18 decimals
        uint256 maxSupply = 21_000_000 * 10**18; // 21 million tokens, scaled to 18 decimals
        
        // Generate a pseudo-random number between minSupply and maxSupply
        uint256 randomSupply = minSupply + (uint256(
            keccak256(abi.encodePacked(block.timestamp, block.difficulty, msg.sender))
        ) % (maxSupply - minSupply + 1));
        
        return randomSupply;
    }

    function rollDice() external payable {
        require(msg.value > 0, "ETH amount must be greater than zero");

        // Record the ETH sent by the user
        userEthDeposits[msg.sender] += msg.value;

        // Update the total ETH received
        totalETHReceived += msg.value;

        emit DiceRolled(msg.sender, msg.value);
    }

    function _buyOLAS(uint256 ethAmount) internal returns (uint256) {
        address;
        path[0] = IUniswapV2Router02(uniswapV2Router).WETH();
        path[1] = olasAddress;

        uint256[] memory amounts = IUniswapV2Router02(uniswapV2Router).swapExactETHForTokens{ value: ethAmount }(
            0, // Accept any amount of OLAS
            path,
            address(this),
            block.timestamp
        );

        return amounts[1]; // Return the OLAS amount bought
    }

    function _scheduleBurn(uint256 amount) internal {
        scheduledBurnAmount += amount;
        emit OLASScheduledForBurn(amount);
    }

    function _createUniswapPair(address tokenAddress, uint256 olasAmount, uint256 tokenAmount) internal {
        address pair = IUniswapV2Factory(uniswapV2Factory).getPair(olasAddress, tokenAddress);
        if (pair == address(0)) {
            pair = IUniswapV2Factory(uniswapV2Factory).createPair(olasAddress, tokenAddress);
        }

        ERC20(olasAddress).approve(uniswapV2Router, olasAmount);
        ERC20(tokenAddress).approve(uniswapV2Router, tokenAmount);

        IUniswapV2Router02(uniswapV2Router).addLiquidity(
            olasAddress,
            tokenAddress,
            olasAmount,
            tokenAmount,
            0, // Accept any amount of OLAS
            0, // Accept any amount of new tokens
            address(this),
            block.timestamp
        );
    }

    function bridgeAndBurn() external {
        require(scheduledBurnAmount > 0, "No OLAS scheduled for burn");

        // Approve bridge to use OLAS
        IERC20(olasAddress).approve(rollupBridge, scheduledBurnAmount);

        // Data for the mainnet to execute OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", scheduledBurnAmount);

        // Bridge OLAS to mainnet
        IRollupBridge(rollupBridge).bridgeTokens(olasAddress, scheduledBurnAmount, data);

        emit OLASBridgedForBurn(scheduledBurnAmount);

        // Reset the scheduled burn amount
        scheduledBurnAmount = 0;
    }

    // Allow the contract to receive ETH
    receive() external payable {}
}
