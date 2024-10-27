// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./CustomERC20.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/* 
* This contract let's:
* 1) any msg.sender summon a meme.
* 2) within 24h of a meme being summoned, any msg.sender can heart a meme. This requires the msg.sender to send a non-zero ETH value, which gets recorded as a contribution. 
* 3) after 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for the meme and distributes the rest of the tokens to the hearters, proportional to their contributions.
* 4) anyone burn the accumulated OLAS buy bridging it to Ethereum where it is burned.
* 10% of the ETH contributed to a meme gets converted into OLAS and scheduled for burning upon unleashing of the meme.
* The remainder of the ETH contributed (90%) is converted to USDC and contributed to an LP, together with 50% of the token supply of the meme.
*/
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

    struct MemeSummon {
        uint256 ethContributed;
        uint256 timestamp;
    }
    mapping(address => MemeSummon) public memeSummons;
    mapping(address => mapping(address => uint256)) public memeHearts;
    mapping(address => address[]) public memeSupporters;

    event TokenDeployed(address tokenAddress, address deployer, uint256 lpTokens, address lpPool);
    event OLASScheduledForBurn(uint256 amount);
    event OLASBridgedForBurn(uint256 amount);
    event Summoned(address indexed deployer, uint256 ethContributed, address tokenAddress);
    event Hearted(address indexed user, uint256 amount);
    event Unleashed(address lpPairAddress);

    constructor(address _olasAddress, address _USDCAddress, address _uniswapV2Router, address _uniswapV2Factory, address _rollupBridge) {
        olasAddress = _olasAddress;
        USDCAddress = _USDCAddress;
        uniswapV2Router = _uniswapV2Router;
        uniswapV2Factory = _uniswapV2Factory;
        rollupBridge = _rollupBridge;
    }

    function summonThisMeme(
        string memory name_,
        string memory symbol_,
        uint256 totalSupply_
    ) external payable {
        require(msg.value >= 0.1 ether, "Minimum of 0.1 ETH required to summon");
        require(totalSupply_ >= 1_000_000 * 10**18, "Total supply must be at least 1 million tokens");

        CustomERC20 newToken = new CustomERC20(name_, symbol_, totalSupply_, address(this));

        memeSummons[address(newToken)] = MemeSummon({
            ethContributed: msg.value,
            timestamp: block.timestamp
        });
        memeHearts[address(newToken)][msg.sender] = msg.value;
        memeSupporters[address(newToken)].push(msg.sender);

        emit Summoned(msg.sender, msg.value, address(newToken));
    }

    function heartThisMeme(address tokenAddress_) external payable {
        require(msg.value > 0, "ETH amount must be greater than zero");
        require(memeSummons[tokenAddress_].ethContributed > 0, "Meme not yet summoned");
        require(memeSummons[tokenAddress_].timestamp != 0, "Meme already unleashed");

        memeHearts[tokenAddress_][msg.sender] += msg.value;
        memeSupporters[tokenAddress_].push(msg.sender);

        totalETHHeld += msg.value;

        emit Hearted(msg.sender, msg.value);
    }

    function unleashThisMeme(address tokenAddress_) external {
        require(memeSummons[tokenAddress_].timestamp > 0, "Meme not summoned");
        require(block.timestamp >= memeSummons[tokenAddress_].timestamp + 24 hours, "Cannot unleash before 24 hours");

        // Calculate the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummons[tokenAddress_].ethContributed;
        for (uint256 i = 0; i < memeSupporters[tokenAddress_].length; i++) {
            address supporter = memeSupporters[tokenAddress_][i];
            totalETHCommitted += memeHearts[tokenAddress_][supporter];
        }

        // Buy OLAS with 10% of the total ETH committed
        uint256 tenPercentOfETH = (totalETHCommitted * burnPercentage) / 100;
        uint256 OLASAmount = _buyERC20(tenPercentOfETH, olasAddress);

        // Buy USDC with the remaining 90% of the total ETH committed
        uint256 USDCAmount = _buyERC20(totalETHCommitted - tenPercentOfETH, USDCAddress);

        // Schedule OLAS for burning
        scheduledBurnAmount += OLASAmount;
        emit OLASScheduledForBurn(OLASAmount);

        // Calculate LP token allocation (50% of total supply) and distribution to supporters
        CustomERC20 memeToken = CustomERC20(tokenAddress_);
        uint256 totalSupply_ = memeToken.totalSupply();
        uint256 lpNewTokenAmount = (totalSupply_ * lpPercentage) / 100;
        uint256 heartersAmount = totalSupply_ - lpNewTokenAmount;

       // Create Uniswap pair with 50% allocated for LP
        _createUniswapPair(tokenAddress_, USDCAmount, lpNewTokenAmount);

        // Distribute the remaining 50% proportional to the ETH committed by each supporter
        _distributeMemeTokens(tokenAddress_, heartersAmount);

        // Record meme is unleashed;
        memeSummons[tokenAddress_].timestamp = 0;

        emit Unleashed(address(uniswapV2Factory));
    }

    function _buyERC20(uint256 ethAmount, address token) internal returns (uint256) {
        address[] memory path = new address[](2);
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
        address pair = IUniswapV2Factory(uniswapV2Factory).getPair(USDCAddress, tokenAddress);
        if (pair == address(0)) {
            pair = IUniswapV2Factory(uniswapV2Factory).createPair(USDCAddress, tokenAddress);
        }

        IERC20(USDCAddress).approve(uniswapV2Router, USDCAmount);
        IERC20(tokenAddress).approve(uniswapV2Router, tokenAmount);

        IUniswapV2Router02(uniswapV2Router).addLiquidity(
            USDCAddress,
            tokenAddress,
            USDCAmount,
            tokenAmount,
            0, // Accept any amount of USDC
            0, // Accept any amount of meme token
            address(this),
            block.timestamp
        );
    }

    function _distributeMemeTokens(address tokenAddress, uint256 heartersAmount) internal {
        CustomERC20 memeToken = CustomERC20(tokenAddress);

        uint256 totalContribution = memeSummons[tokenAddress].ethContributed;
        for (uint256 i = 0; i < memeSupporters[tokenAddress].length; i++) {
            address supporter = memeSupporters[tokenAddress][i];
            totalContribution += memeHearts[tokenAddress][supporter];
        }

        // Distribute tokens proportionally based on ETH contribution
        for (uint256 i = 0; i < memeSupporters[tokenAddress].length; i++) {
            address supporter = memeSupporters[tokenAddress][i];
            uint256 userContribution = memeHearts[tokenAddress][supporter];
            uint256 allocation = (heartersAmount * userContribution) / totalContribution;
            memeToken.transfer(address(this), supporter, allocation);
        }
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
