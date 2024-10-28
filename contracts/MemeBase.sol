// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";

// Balancer interface
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

    /// @dev Swaps tokens on Balancer.
    function swap(SingleSwap memory singleSwap, FundManagement memory funds, uint256 limit, uint256 deadline)
        external payable returns (uint256);
}

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

// Oracle interface
interface IOracle {
    /// @dev Gets latest round token price data.
    function latestRoundData()
        external returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

// Bridge interface
interface IBridge {
    /// @dev Initiates a withdrawal from L2 to L1 to a target account on L1.
    /// @param l2Token Address of the L2 token to withdraw.
    /// @param to Recipient account on L1.
    /// @param amount Amount of the L2 token to withdraw.
    /// @param minGasLimit Minimum gas limit to use for the transaction.
    /// @param extraData Extra data attached to the withdrawal.
    function withdrawTo(address l2Token, address to, uint256 amount, uint32 minGasLimit, bytes calldata extraData) external;
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Creates an LP pair.
    function createPair(address tokenA, address tokenB) external returns (address pair);

    /// @dev Swaps exact amount of ETH for a specified token.
    function swapExactETHForTokens(uint256 amountOutMin, address[] calldata path, address to, uint256 deadline)
        external payable returns (uint256[] memory amounts);

    /// @dev Adds liquidity to the LP consisting of tokenA and tokenB.
    function addLiquidity(address tokenA, address tokenB, uint256 amountADesired, uint256 amountBDesired,
        uint256 amountAMin, uint256 amountBMin, address to, uint256 deadline)
        external returns (uint256 amountA, uint256 amountB, uint256 liquidity);
}

/// @title MemeBase - a smart contract factory for Meme Token creation
/// @dev This contract let's:
///      1) Any msg.sender summon a meme.
///      2) Within 24h of a meme being summoned, any msg.sender can heart a meme. This requires the msg.sender to send
///         a non-zero ETH value, which gets recorded as a contribution.
///      3) After 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for
///         the meme and distributes the rest of the tokens to the hearters, proportional to their contributions.
///      4) Anyone is able to burn the accumulated OLAS by bridging it to Ethereum where it is burned.
/// @notice 10% of the ETH contributed to a meme gets converted into OLAS and scheduled for burning upon unleashing of
///         the meme. The remainder of the ETH contributed (90%) is converted to USDC and contributed to an LP,
///         together with 50% of the token supply of the meme.
contract MemeBase {
    event OLASBridgedForBurn(address indexed olas, uint256 amount);
    event Summoned(address indexed summoner, address indexed memeToken, uint256 ethContributed);
    event Hearted(address indexed hearter, uint256 amount);
    event Unleashed(address indexed unleasher, address indexed memeToken, address indexed lpPairAddress, uint256 liquidity);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 remainingAmount);

    // Meme Summon struct
    struct MemeSummon {
        // ETH contributed to the meme launch
        uint256 ethContributed;
        // Summon timestamp
        uint256 summonTime;
        // Unleash timestamp
        uint256 unleashTime;
        // Finalized hearters amount
        uint256 heartersAmount;
    }

    // Version number
    string public constant VERSION = "0.1.0";
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
    // Percentage of OLAS to burn (10%)
    uint256 public constant OLAS_BURN_PERCENTAGE = 10;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public constant LP_PERCENTAGE = 50;
    // Slippage parameter (3%)
    uint256 public constant SLIPPAGE = 97;
    // Token transfer gas limit for L1
    // This is safe as the value is practically bigger than observed ones on numerous chains
    uint32 public constant TOKEN_GAS_LIMIT = 300_000;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Balancer Pool Id
    bytes32 public immutable balancerPoolId;
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
    // L2 token relayer bridge address
    address public immutable l2TokenRelayer;
    // Oracle address
    address public immutable oracle;
    // Balancer Vault address
    address public immutable balancerVault;

    // Number of meme tokens
    uint256 public numTokens;
    // Map of meme token => Meme summon struct
    mapping(address => MemeSummon) public memeSummons;
    // Map of mem token => (map of hearter => ETH balance)
    mapping(address => mapping(address => uint256)) public memeHearters;
    // Set of all meme tokens created by this contract
    address[] public memeTokens;

    /// @dev MemeBase constructor
    constructor(
        address _olas,
        address _usdc,
        address _weth,
        address _router,
        address _factory,
        address _l2TokenRelayer,
        address _oracle,
        address _balancerVault,
        bytes32 _balancerPoolId
    ) {
        olas = _olas;
        usdc = _usdc;
        weth = _weth;
        router = _router;
        factory = _factory;
        l2TokenRelayer = _l2TokenRelayer;
        oracle = _oracle;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;
    }

    /// @dev Buys USDC on UniswapV2 using ETH amount.
    /// @param ethAmount Input ETH amount.
    /// @return USDC amount bought.
    function _buyUSDCUniswap(uint256 ethAmount) internal returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = usdc;

        // Calculate price by Oracle
        (, int256 answerPrice, , , ) = IOracle(oracle).latestRoundData();
        require(answerPrice > 0, "Oracle price is incorrect");

        // Oracle returns 8 decimals, USDC has 6 decimals, need to additionally divide by 100
        // ETH: 18 decimals, USDC leftovers: 2 decimals, percentage: 2 decimals; denominator = 18 + 2 + 2 = 22
        uint256 limit = uint256(answerPrice) * ethAmount * SLIPPAGE / 1e22;
        // Swap ETH for USDC
        uint256[] memory amounts = IUniswap(router).swapExactETHForTokens{ value: ethAmount }(
            limit,
            path,
            address(this),
            block.timestamp
        );

        // Return the USDC amount bought
        return amounts[1];
    }

    /// @dev Buys OLAS on Balancer.
    /// @param usdcAmount USDC amount.
    /// @param olasSpotPrice OLAS spot price.
    /// @return Obtained OLAS amount.
    function _buyOLASBalancer(uint256 usdcAmount, uint256 olasSpotPrice) internal returns (uint256) {
        // Approve usdc for the Balancer Vault
        IERC20(usdc).approve(balancerVault, usdcAmount);

        // Prepare Balancer data
        IBalancer.SingleSwap memory singleSwap = IBalancer.SingleSwap(balancerPoolId, IBalancer.SwapKind.GIVEN_IN, usdc,
            olas, usdcAmount, "0x");
        IBalancer.FundManagement memory fundManagement = IBalancer.FundManagement(address(this), false,
            payable(address(this)), false);

        // Get token out limit
        uint256 limit = usdcAmount * olasSpotPrice;
        // Perform swap
        return IBalancer(balancerVault).swap(singleSwap, fundManagement, limit, block.timestamp);
    }

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param OLASAmount OLAS amount.
    function _bridgeAndBurn(uint256 OLASAmount) internal {
        // Approve bridge to use OLAS
        IERC20(olas).approve(l2TokenRelayer, OLASAmount);

        // Data for the mainnet validate the OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", OLASAmount);

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).withdrawTo(olas, address(0), OLASAmount, TOKEN_GAS_LIMIT, data);

        emit OLASBridgedForBurn(olas, OLASAmount);
    }

    /// @dev Creates USDC + meme token LP and adds liquidity.
    /// @param memeToken Meme token address.
    /// @param usdcAmount USDC amount.
    /// @param memeTokenAmount Meme token amount.
    /// @return pair USDC + meme token LP address.
    /// @return liquidity Obtained LP liquidity.
    function _createUniswapPair(
        address memeToken,
        uint256 usdcAmount,
        uint256 memeTokenAmount
    ) internal returns (address pair, uint256 liquidity) {
        // Create the LP
        pair = IUniswap(factory).createPair(usdc, memeToken);

        // Approve tokens for router
        IERC20(usdc).approve(router, usdcAmount);
        IERC20(memeToken).approve(router, memeTokenAmount);

        // Add USDC + meme token liquidity
        (, , liquidity) = IUniswap(router).addLiquidity(
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

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    /// @param heartersAmount Total hearters meme token amount.
    /// @param hearterContribution Hearter contribution.
    /// @param totalETHCommitted Total ETH contributed for the token launch.
    function _collect(
        address memeToken,
        uint256 heartersAmount,
        uint256 hearterContribution,
        uint256 totalETHCommitted
    ) internal {
        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Allocate corresponding meme token amount to the hearter
        uint256 allocation = (heartersAmount * hearterContribution) / totalETHCommitted;

        // Zero the allocation
        memeHearters[memeToken][msg.sender] = 0;

        // Transfer meme token maount to the msg.sender
        memeTokenInstance.transfer(msg.sender, allocation);

        emit Collected(msg.sender, memeToken, allocation);
    }

    /// @dev Summons meme token.
    /// @param name Token name.
    /// @param symbol Token symbol.
    /// @param totalSupply Token total supply.
    function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        require(msg.value >= MIN_ETH_VALUE, "Minimum ETH value is required to summon");
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Minimum total supply is not met");

        Meme newTokenInstance = new Meme(name, symbol, DECIMALS, totalSupply);
        address memeToken = address(newTokenInstance);

        // Initiate meme token map values
        memeSummons[memeToken] = MemeSummon(msg.value, block.timestamp, 0, 0);
        memeHearters[memeToken][msg.sender] = msg.value;

        // Push token into the global list of tokens
        memeTokens.push(memeToken);
        numTokens = memeTokens.length;

        emit Summoned(msg.sender, memeToken, msg.value);
    }

    /// @dev Hearts the meme token with ETH contribution.
    /// @param memeToken Meme token address.
    function heartThisMeme(address memeToken) external payable {
        // Check for zero value
        require(msg.value > 0, "ETH amount must be greater than zero");

        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Get the total ETH committed to this meme
        uint256 totalETHCommitted = memeSummon.ethContributed;

        // Check that the meme has been summoned
        require(totalETHCommitted > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(block.timestamp < memeSummon.unleashTime, "Meme already unleashed");

        // Update meme token map values
        totalETHCommitted += msg.value;
        memeSummon.ethContributed = totalETHCommitted;
        memeHearters[memeToken][msg.sender] += msg.value;

        emit Hearted(msg.sender, msg.value);
    }

    /// @dev Unleashes the meme token.
    /// @param memeToken Meme token address.
    /// @param olasSpotPrice OLAS spot price.
    function unleashThisMeme(address memeToken, uint256 olasSpotPrice) external {
        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Check if the meme has been summoned
        require(memeSummon.ethContributed > 0, "Meme not yet summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummon.summonTime + UNLEASH_PERIOD, "Cannot unleash yet");
        // Check OLAS spot price
        require(olasSpotPrice > 0, "OLAS spot price is incorrect");

        // Buy USDC with the the total ETH committed
        uint256 usdcAmount = _buyUSDCUniswap(memeSummon.ethContributed);

        // Buy OLAS with the burn percentage of the total ETH committed
        uint256 burnPercentageOfUSDC = (usdcAmount * OLAS_BURN_PERCENTAGE) / 100;
        uint256 OLASAmount = _buyOLASBalancer(burnPercentageOfUSDC, olasSpotPrice);

        // Burn OLAS
        _bridgeAndBurn(OLASAmount);

        // Adjust USDC amount
        usdcAmount -= burnPercentageOfUSDC;

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeTokenInstance = Meme(memeToken);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 lpTokenAmount = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - lpTokenAmount;

        // Create Uniswap pair with LP allocation
        (address pool, uint256 liquidity) = _createUniswapPair(memeToken, usdcAmount, lpTokenAmount);

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;

        // Allocate to the token hearter unleashing the meme
        if (memeHearters[memeToken][msg.sender] > 0) {
            _collect(memeToken, memeHearters[memeToken][msg.sender], heartersAmount, memeSummon.ethContributed);
        }

        emit Unleashed(msg.sender, memeToken, pool, liquidity);
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    function collect(address memeToken) external {
        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme can be collected
        require(block.timestamp < memeSummon.summonTime + COLLECT_PERIOD, "Collect only allowed until 48 hours after summon");

        // Get hearter contribution
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        // Check for zero value
        require(hearterContribution > 0, "No token allocation");

        // Collect the token
        _collect(memeToken, hearterContribution, memeSummon.heartersAmount, memeSummon.ethContributed);
    }

    /// @dev Purges uncollected meme token allocation.
    /// @param memeToken Meme token address.
    function purge(address memeToken) external {
        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme has been unleashed
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if enough time has passed since the meme was summoned
        require(block.timestamp >= memeSummon.summonTime + PURGE_PERIOD, "Purge only allowed from 48 hours after summon");

        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Burn all remaining tokens in this contract
        uint256 remainingBalance = memeTokenInstance.balanceOf(address(this));
        // Check the remaining balance is positive
        require(remainingBalance > 0, "Has been purged or nothing to purge");
        // Burn the remaining balance
        memeTokenInstance.burn(remainingBalance);

        emit Purged(memeToken, remainingBalance);
    }

    /// @dev Allows the contract to receive ETH
    receive() external payable {}
}
