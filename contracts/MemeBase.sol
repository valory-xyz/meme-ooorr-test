// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CustomERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";

contract MemeBase {
    address public olasAddress; // Address of OLAS token
    address public uniswapV2Router;
    address public uniswapV2Factory;
    
    uint256 public burnPercentage = 10; // Percentage of OLAS to burn (10%)
    uint256 public lpPercentage = 90;   // Percentage of OLAS for liquidity pool (90%)

    event TokenDeployed(address tokenAddress, address deployer, uint256 lpTokens, address lpPool);

    constructor(address _olasAddress, address _uniswapV2Router, address _uniswapV2Factory) {
        olasAddress = _olasAddress;
        uniswapV2Router = _uniswapV2Router;
        uniswapV2Factory = _uniswapV2Factory;
    }

    function deploy(
        string memory name_,
        string memory symbol_,
        address[] memory holders_,
        uint256[] memory allocations_,
        uint256 totalSupply_,
        uint256 userAllocation_
    ) external payable {
        require(msg.value > 0, "ETH required to deploy");

        // Buy OLAS from Uniswap with 100% of the sent ETH
        uint256 olasAmount = _buyOLAS(msg.value);

        // Burn 10% of OLAS
        uint256 burnAmount = (olasAmount * burnPercentage) / 100;
        _burnOLAS(burnAmount);

        // Distribute the remaining OLAS to LP
        uint256 lpOLASAmount = olasAmount - burnAmount;
        
        // Deploy new ERC20 token
        CustomERC20 newToken = new CustomERC20(name_, symbol_, holders_, allocations_, totalSupply_);
        
        // Pair the new token with OLAS in Uniswap to create LP
        uint256 lpTokens = (totalSupply_ * lpPercentage) / 100;
        _createUniswapPair(address(newToken), lpOLASAmount, lpTokens);

        // Mint the rest of the user's allocation
        newToken.mint(msg.sender, userAllocation_);

        emit TokenDeployed(address(newToken), msg.sender, lpTokens, address(uniswapV2Factory));
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

    function _burnOLAS(uint256 amount) internal {
        ERC20(olasAddress).transfer(address(0x0), amount);
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

    // Allow the contract to receive ETH
    receive() external payable {}
}
