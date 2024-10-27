// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";

interface IBalancer {
    enum SwapKind { GIVEN_IN, GIVEN_OUT }

    struct SingleSwap {
        bytes32 poolId;
        SwapKind kind;
        address assetIn;
        address assetOut;
        uint256 amount;
        bytes userData;
    }

    struct FundManagement {
        address sender;
        bool fromInternalBalance;
        address payable recipient;
        bool toInternalBalance;
    }

    function swap(
        SingleSwap memory singleSwap,
        FundManagement memory funds,
        uint256 limit,
        uint256 deadline
    ) external payable returns (uint256);
}

interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IOracle {
    function latestRoundData() external returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

interface IRollupBridge {
    function bridgeTokens(address token, uint256 amount, bytes memory data) external;
}

interface UniswapV2 {
    function createPair(address tokenA, address tokenB) external returns (address pair);

    function swapExactETHForTokens(uint amountOutMin, address[] calldata path, address to, uint deadline)
        external payable returns (uint[] memory amounts);

    function addLiquidity(
        address tokenA,
        address tokenB,
        uint amountADesired,
        uint amountBDesired,
        uint amountAMin,
        uint amountBMin,
        address to,
        uint deadline
    ) external returns (uint amountA, uint amountB, uint liquidity);
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
    event OLASBridgedForBurn(address indexed olas, uint256 amount);
    event Summoned(address indexed deployer, address indexed memeToken, uint256 ethContributed);
    event Hearted(address indexed user, uint256 amount);
    event Unleashed(address indexed memeToken, address indexed lpPairAddress);
    event Purged(address indexed memeToken, uint256 remainingAmount);

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
    // Balancer Pool Id
    bytes32 public constant BALANCER_POOL_ID = 0x5332584890d6e415a6dc910254d6430b8aab7e69000200000000000000000103;
    // Balancer Vault address
    address public constant BALANCER_VAULT = 0xBA12222222228d8Ba445958a75a0704d566BF2C8;

    // OLAS token address
    address public immutable olas;
    // USDC token address
    address public immutable usdc;
    // WETH token address
    address public immutable weth;
    // Uniswap V2 router address
    address public immutable router;
    // Uniswap V2 factory address
    address public immutable factory;
    // Rollup bridge address
    address public immutable rollupBridge;
    // Oracle address
    address public immutable oracle;

    // Percentage of OLAS to burn (10%)
    uint256 public immutable burnPercentage;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public immutable lpPercentage;
    // Slippage parameter in 1e6 form, since USDC has 6 decimals
    uint256 public immutable slippage;

    struct MemeSummon {
        uint256 ethContributed;
        uint256 summonTime;
        uint256 unleashTime;
    }
    // Number of meme tokens
    uint256 public numTokens;
    mapping(address => MemeSummon) public memeSummons;
    mapping(address => mapping(address => uint256)) public memeHearts;
    address[] public memeTokens;

    constructor(
        address _olas,
        address _usdc,
        address _weth,
        address _router,
        address _factory,
        address _rollupBridge,
        uint256 _burnPercentage,
        uint256 _lpPercentage,
        uint256 _slippage
    ) {
        olas = _olas;
        usdc = _usdc;
        weth = _weth;
        router = _router;
        factory = _factory;
        rollupBridge = _rollupBridge;

        burnPercentage = _burnPercentage;
        lpPercentage = _lpPercentage;
        slippage = _slippage;
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
        memeSummons[memeToken].ethContributed += msg.value;
        memeHearts[address(newToken)][msg.sender] = msg.value;

        // Push token into the global list of tokens
        memeTokens.push(address(newToken));
        numTokens = memeTokens.length;

        emit Summoned(msg.sender, address(newToken), msg.value);
    }

    function heartThisMeme(address memeToken) external payable {
        require(msg.value > 0, "ETH amount must be greater than zero");
        require(memeSummons[memeToken].ethContributed > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(block.timestamp < memeSummons[memeToken].unleashTime, "Meme already unleashed");

        memeSummons[memeToken].ethContributed += msg.value;
        memeHearts[memeToken][msg.sender] += msg.value;

        emit Hearted(msg.sender, msg.value);
    }

    function unleashThisMeme(address memeToken, uint256 olasSpotPrice) external {
        // Check if the meme has been summoned
        require(memeSummons[memeToken].ethContributed > 0, "Meme not yet summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummons[memeToken].summonTime + UNLEASH_PERIOD, "Cannot unleash yet");
        // Check OLAS spot price
        require(olasSpotPrice > 0, "OLAS spot price is incorrect");

        // Calculate the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummons[memeToken].ethContributed;

        // Buy USDC with the the total ETH committed
        uint256 usdcAmount = _buyUSDCUniswap(totalETHCommitted);

        // Buy OLAS with the burn percentage of the total ETH committed
        uint256 burnPercentageOfUSDC = (usdcAmount * burnPercentage) / 100;
        uint256 OLASAmount = _buyOLASBalancer(burnPercentageOfUSDC, olasSpotPrice);

        // Burn OLAS
        _bridgeAndBurn(OLASAmount);

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeToken = Meme(memeToken);
        uint256 totalSupply = memeToken.totalSupply();
        uint256 lpNewTokenAmount = (totalSupply * lpPercentage) / 100;
        uint256 heartersAmount = totalSupply - lpNewTokenAmount;

        // Create Uniswap pair with LP allocation
        address pool = _createUniswapPair(memeToken, usdcAmount, lpNewTokenAmount);

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
        require(block.timestamp < memeSummons[memeToken].summonTime + COLLECT_PERIOD, "Collect only allowed until 48 hours after summon");
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
        require(block.timestamp >= memeSummons[memeToken].summonTime + PURGE_PERIOD, "Purge only allowed from 48 hours after summon");

        Meme memeToken = Meme(memeToken);

        // Burn all remaining tokens in this contract
        uint256 remainingBalance = memeToken.balanceOf(address(this));
        // Check the remaining balance is positive
        require(remainingBalance > 0, "Has been purged or nothing to purge");
        // Burn the remaining balance
        memeToken.burn(remainingBalance);

        emit Purged(memeToken, remainingBalance);
    }

    function _buyUSDCUniswap(uint256 ethAmount) internal returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = usdc;

        // Calculate price by Oracle
        (, int256 answerPrice, , , ) = IOracle(oracle).latestRoundData();
        require(answerPrice > 0, "Oracle price is incorrect");
        // Oracle returns 8 decimals, USDC has 6 decimals, need to additionally divide by 100
        uint256 limit = uint256(answerPrice) * ethAmount * slippage / 1e8;
        // Compare with slippage
        uint256[] memory amounts = IUniswapV2Router02(router).swapExactETHForTokens{ value: ethAmount }(
            limit,
            path,
            address(this),
            block.timestamp
        );

        return amounts[1]; // Return the token amount bought
    }

    function _createUniswapPair(address memeToken, uint256 usdcAmount, uint256 memeTokenAmount) internal returns (address pair) {
        pair = IUniswapV2Factory(factory).createPair(usdc, memeToken);

        IERC20(usdc).approve(router, usdcAmount);
        IERC20(memeToken).approve(router, memeTokenAmount);

        IUniswapV2Router02(router).addLiquidity(
            usdc,
            memeToken,
            usdcAmount,
            memeTokenAmount,
            0, // Accept any amount of USDC
            0, // Accept any amount of meme token
            address(this),
            block.timestamp
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

    function _buyOLASBalancer(uint256 usdcAmount, uint256 olasSpotPrice) internal returns (uint256) {
        // Approve usdc for the Balancer Vault
        IERC20(usdc).approve(BALANCER_VAULT, usdcAmount);

        // Prepare Balancer data
        SingleSwap memory singleSwap = IBalancer.SingleSwap(BALANCER_POOL_ID, IBalancer.SwapKind.GIVEN_IN, usdc, olas,
            usdcAmount, "0x");

        FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false, address(this), false);

        // Get token out limit
        uint256 limit = usdcAmount * olasSpotPrice;
        // Perform swap
        return IBalancer(BALANCER_VAULT).swap(singleSwap, fundManagement, limit, block.timestamp);
    }

    // Allow the contract to receive ETH
    receive() external payable {}
}
