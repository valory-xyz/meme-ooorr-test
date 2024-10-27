// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CustomERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";

contract MemeBase {
    address public olasAddress; // Address of OLAS token
    address public USDCAddress; // Address of USDC token
    address public uniswapV2Router;
    address public uniswapV2Factory;
    address public rollupBridge;

    uint256 public burnPercentage = 10; // Percentage of OLAS to burn (10%)
    uint256 public lpPercentage = 50;   // Percentage of initial supply for liquidity pool (50%)

    uint256 public scheduledBurnAmount;
    uint256 public totalETHHeld;

    mapping(address => [uint256) public memeSummons;
    mapping(address => mapping(address => uint256)) public memeHearts;

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

    function summonThisMeme(
        string memory name_,
        string memory symbol_,
        uint256 totalSupply_,
    ) external payable {
        require(msg.value > 0.1, "Minimum of 0.1 ETH required to deploy");

        require(totalSupply_ >= 1_000_000 * 10**18, "Total supply must be at least 1 million tokens");

        CustomERC20 newToken = new CustomERC20(name_, symbol_, totalSupply_);

        memeSummons[newToken] = msg.value; // also need to safe the block timestamp
        memeHearts[newToken] = {};

        emit Summoned(msg.sender, msg.value, newToken);
    }

    function heartThisMeme(address tokenAddress_) external payable {
        require(msg.value > 0, "ETH amount must be greater than zero");
        require(memeHearts[newToken], "Meme not yet summoned");
        require(memeSummons[tokenAddress_] > 0, "Meme already unleashed");

        memeHearts[tokenAddress_][msg.sender] += msg.value;

        totalETHHeld += msg.value;

        emit Hearted(msg.sender, msg.value);
    }

    function unleashThisMeme(address tokenAddress_) external {
        // ensure this can only be done 24h after summoning
        require(...);

        // get the total ETH committed
        uint256 totalETHCommitted = memeSummons[tokenAddress_];
        for (uint256 i = 0; i < memeHearts[tokenAddress_].length; i++) {
            totalETHCommitted += memeHearts[tokenAddress_][i]
        }

        // Buy OLAS from Uniswap with 10% of the sent ETH;
        // Buy USDC from Uniswap with 90% of the sent ETH;
        uint256 tenPercentOfETH = totalETHCommitted * 0.1;
        uint256 OLASAmount = _buyERC20(tenPercentOfETH, olasAddress);
        uint256 USDCAmount = _buyERC20(totalETHCommitted - tenPercentOfETH, usdcAddress);

        // Schedule OLAS for burning;
        scheduledBurnAmount += OLASAmount;
        emit OLASScheduledForBurn(OLASAmount);

        // Calculate LP token allocation (50% of total supply)
        uint256 lpNewTokenAmount = (totalSupply_ * lpPercentage) / 100;
        uint256 heartersAmount = totalSupply_ - lpNewTokenAmount;

        // create the Uniswap pair
        _createUniswapPair(address(newToken), USDCAmount, lpNewTokenAmount);

        // distribute the remaining 50% proportional to the ETH committed to the specific meme 

        emit Unleashed(address(uniswapV2Factory));
    }


    function _buyOLAS(uint256 ethAmount,address token) internal returns (uint256) {
        address;
        path[0] = IUniswapV2Router02(uniswapV2Router).WETH();
        path[1] = token;

        uint256[] memory amounts = IUniswapV2Router02(uniswapV2Router).swapExactETHForTokens{ value: ethAmount }(
            0, // Accept any amount of token
            path,
            address(this),
            block.timestamp
        );

        return amounts[1]; // Return the token amount bought
    }

    function _createUniswapPair(address tokenAddress, uint256 USDCAmount, uint256 tokenAmount) internal {
        address pair = IUniswapV2Factory(uniswapV2Factory).createPair(USDCAddress, tokenAddress);

        ERC20(USDCAddress).approve(uniswapV2Router, USDCAmount);
        ERC20(tokenAddress).approve(uniswapV2Router, tokenAmount);

        IUniswapV2Router02(uniswapV2Router).addLiquidity(
            USDCAddress,
            tokenAddress,
            USDCAmount,
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
