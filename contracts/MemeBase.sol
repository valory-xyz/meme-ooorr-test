// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";
import "@uniswap/v2-periphery/contracts/interfaces/IUniswapV2Router02.sol";
import "@uniswap/v2-core/contracts/interfaces/IUniswapV2Factory.sol";

interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IRollupBridge {
    function bridgeTokens(address token, uint256 amount, bytes memory data) external;
}

/* 
* This contract let's:
* 1) any msg.sender summon a meme.
* 2) within 24h of a meme being summoned, any msg.sender can heart a meme. This requires the msg.sender to send a non-zero ETH value, which gets recorded as a contribution. 
* 3) after 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for the meme and distributes the rest of the tokens to the hearters, proportional to their contributions.
* 4) anyone burn the accumulated OLAS by bridging it to Ethereum where it is burned.
* 10% of the ETH contributed to a meme gets converted into OLAS and scheduled for burning upon unleashing of the meme.
* The remainder of the ETH contributed (90%) is converted to USDC and contributed to an LP, together with 50% of the token supply of the meme.
*/
contract MemeBase {
    // Version number
    string public constant VERSION = "0.1.0";
    // Meme decimals
    uint256 public constant DECIMALS = 18;
    // ETH deposit minimum value
    uint256 public constant MIN_ETH_VALUE = 0.1 ether;
    // Total supply minimum value
    uint256 public constant MIN_TOTAL_SUPPLY = 1_000_000 ether;
    // Unleash period
    uint256 public constant UNLEASH_PERIOD = 24 hours;
    // Collect period
    uint256 public constant COLLECT_PERIOD = 48 hours;
    // Purge period
    uint256 public constant PURGE_PERIOD = 48 hours;

    // OLAS token address
    address public olas;
    // USDC token address
    address public usdc;
    // Uniswap V2 router address
    address public router;
    // Uniswap V2 factory address
    address public factory;
    // Rollup bridge address
    address public rollupBridge;

    // Percentage of OLAS to burn (10%)
    uint256 public immutable burnPercentage;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public immutable lpPercentage;

    struct MemeSummon {
        uint256 ethContributed;
        uint256 summonTime;
        uint256 unleashTime;
    }
    mapping(address => MemeSummon) public memeSummons;
    mapping(address => mapping(address => uint256)) public memeHearts;

    event OLASBridgedForBurn(address indexed olas, uint256 amount);
    event Summoned(address indexed deployer, address indexed memeToken, uint256 ethContributed);
    event Hearted(address indexed user, uint256 amount);
    event Unleashed(address indexed memeToken, address indexed lpPairAddress);
    event Purged(address indexed memeToken, uint256 remainingAmount);

    constructor(
        address _olas,
        address _usdc,
        address _router,
        address _factory,
        address _rollupBridge,
        uint256 _burnPercentage,
        uint256 _lpPercentage
    ) {
        olas = _olas;
        usdc = _usdc;
        router = _router;
        factory = _factory;
        rollupBridge = _rollupBridge;

        burnPercentage = _burnPercentage;
        lpPercentage = _lpPercentage;
    }

    function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        require(msg.value >= MIN_ETH_VALUE, "Minimum of 0.1 ETH required to summon");
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Total supply must be at least 1 million tokens");

        Meme newToken = new Meme(name, symbol, DECIMALS, totalSupply);

        memeSummons[address(newToken)] = MemeSummon({
            ethContributed: msg.value,
            summonTime: block.timestamp
        });
        memeHearts[address(newToken)][msg.sender] = msg.value;

        emit Summoned(msg.sender, address(newToken), msg.value);
    }

    function heartThisMeme(address memeToken) external payable {
        require(msg.value > 0, "ETH amount must be greater than zero");
        require(memeSummons[memeToken].ethContributed > 0, "Meme not yet summoned");
        require(block.timestamp < memeSummons[memeToken].unleashTime, "Meme already unleashed");

        memeSummons[memeToken].ethContributed += msg.value;
        memeHearts[memeToken][msg.sender] += msg.value;

        emit Hearted(msg.sender, msg.value);
    }

    function unleashThisMeme(address memeToken) external {
        // Check if the meme has been summoned
        require(memeSummons[memeToken].ethContributed > 0, "Meme not yet summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummons[memeToken].summonTime + UNLEASH_PERIOD, "Cannot unleash yet");

        // Calculate the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummons[memeToken].ethContributed;

        // Buy USDC with the the total ETH committed
        uint256 USDCAmount = _buyTokenUniswap(totalETHCommitted, usdc);

        // Buy OLAS with the burn percentage of the total ETH committed
        uint256 burnPercentageOfUSDC = (USDCAmount * burnPercentage) / 100;
        uint256 OLASAmount = _buyTokenBalancer(burnPercentageOfUSDC, olas);

        // Burn OLAS
        _bridgeAndBurn(OLASAmount);

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeToken = Meme(memeToken);
        uint256 totalSupply = memeToken.totalSupply();
        uint256 lpNewTokenAmount = (totalSupply * lpPercentage) / 100;
        uint256 heartersAmount = totalSupply - lpNewTokenAmount;

        // Create Uniswap pair with LP allocation
        address pool = _createUniswapPair(memeToken, USDCAmount, lpNewTokenAmount);

        // Distribute the remaining proportional to the ETH committed by each supporter
        // Contributors need to withdraw manually
        if (memeHearts[memeToken][msg.sender] > 0) {
            uint256 userContribution = memeHearts[memeToken][msg.sender];
            uint256 allocation = (heartersAmount * userContribution) / totalETHCommitted;
            memeHearts[memeToken][msg.sender] = 0;
            memeToken.transfer(msg.sender, allocation);
        }

        // Record the actual meme unleash time
        memeSummons[memeToken].unleashTime = block.timestamp;

        emit Unleashed(memeToken, pool);
    }

    function collect(address memeToken) external {
        // Check if the meme can be collected
        require(block.timestamp < memeSummons[memeToken].summonTime + COLLECT_PERIOD, "Collect only allowed until 48 hours after summon.");
        Meme memeToken = Meme(memeToken);
        uint256 totalETHCommitted = memeSummons[memeToken].ethContributed;
        uint256 totalSupply = memeToken.totalSupply();
        uint256 lpNewTokenAmount = (totalSupply * lpPercentage) / 100;
        uint256 heartersAmount = totalSupply - lpNewTokenAmount;
        if (memeHearts[memeToken][msg.sender] > 0) {
            uint256 userContribution = memeHearts[memeToken][msg.sender];
            uint256 allocation = (heartersAmount * userContribution) / totalETHCommitted;
            memeHearts[memeToken][msg.sender] = 0;
            memeToken.transfer(msg.sender, allocation);
        }
    }

    function purge(address memeToken) external {
        // Check if the meme has been unleashed
        require(memeSummons[memeToken].unleashTime > 0, "Meme not unleashed");
        // Check if enough time has passed since the meme was summoned
        require(block.timestamp >= memeSummons[memeToken].summonTime + PURGE_PERIOD, "Purge only allowed from 48 hours after unleash.");

        Meme memeToken = Meme(memeToken);

        // Burn all remaining tokens in this contract
        uint256 remainingBalance = memeToken.balanceOf(address(this));
        // Check the remaining balance is positive
        require(remainingBalance > 0, "Has been purged or nothing to purge");
        // Burn the remaining balance
        memeToken.burn(remainingBalance);

        emit Purged(memeToken, remainingBalance);
    }

    function _buyTokenUniswap(uint256 ethAmount, address token) internal returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = IUniswapV2Router02(router).WETH();
        path[1] = token;

        uint256[] memory amounts = IUniswapV2Router02(router).swapExactETHForTokens{ value: ethAmount }(
            0, // Accept any amount of token
            path,
            address(this),
            block.timestamp + 1000
        );

        return amounts[1]; // Return the token amount bought
    }

    function _createUniswapPair(address memeToken, uint256 USDCAmount, uint256 memeTokenAmount) internal returns (address pair) {
        pair = IUniswapV2Factory(factory).createPair(usdc, memeToken);

        IERC20(usdc).approve(router, USDCAmount);
        IERC20(memeToken).approve(router, memeTokenAmount);

        IUniswapV2Router02(router).addLiquidity(
            usdc,
            memeToken,
            USDCAmount,
            memeTokenAmount,
            0, // Accept any amount of USDC
            0, // Accept any amount of meme token
            address(this),
            block.timestamp + 1000
        );
    }

    function _bridgeAndBurn(uint256 OLASAmount) internal {
        // Approve bridge to use OLAS
        IERC20(olas).approve(rollupBridge, OLASAmount);

        // Data for the mainnet to execute OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", OLASAmount);

        // Bridge OLAS to mainnet
        IRollupBridge(rollupBridge).bridgeTokens(olas, OLASAmount, data);

        emit OLASBridgedForBurn(olas, OLASAmount);
    }

    function burnFees() external {

    }

    // Allow the contract to receive ETH
    receive() external payable {}
}
