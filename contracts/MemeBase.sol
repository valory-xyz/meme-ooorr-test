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

    function swap(
        SingleSwap memory singleSwap,
        FundManagement memory funds,
        uint256 limit,
        uint256 deadline
    ) external payable returns (uint256);
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
    function latestRoundData() external returns (
        uint80 roundId,
        int256 answer,
        uint256 startedAt,
        uint256 updatedAt,
        uint80 answeredInRound
    );
}

// Bridge interface
interface IBridge {
    /**
     * @custom:legacy
     * @notice Initiates a withdrawal from L2 to L1 to a target account on L1.
     *         Note that if ETH is sent to a contract on L1 and the call fails, then that ETH will
     *         be locked in the L1StandardBridge. ETH may be recoverable if the call can be
     *         successfully replayed by increasing the amount of gas supplied to the call. If the
     *         call will fail for any amount of gas, then the ETH will be locked permanently.
     *         This function only works with OptimismMintableERC20 tokens or ether. Use the
     *         `bridgeERC20To` function to bridge native L2 tokens to L1.
     *
     * @param _l2Token     Address of the L2 token to withdraw.
     * @param _to          Recipient account on L1.
     * @param _amount      Amount of the L2 token to withdraw.
     * @param _minGasLimit Minimum gas limit to use for the transaction.
     * @param _extraData   Extra data attached to the withdrawal.
     */
    function withdrawTo(
        address _l2Token,
        address _to,
        uint256 _amount,
        uint32 _minGasLimit,
        bytes calldata _extraData
    ) external;
}

// UniswapV2 interface
interface IUniswap {
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
    event Summoned(address indexed deployer, address indexed memeToken, uint256 ethContributed);
    event Hearted(address indexed user, uint256 amount);
    event Unleashed(address indexed memeToken, address indexed lpPairAddress);
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

    // Balancer Pool Id (0x5332584890d6e415a6dc910254d6430b8aab7e69000200000000000000000103 on Base)
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
    // Balancer Vault address (0xBA12222222228d8Ba445958a75a0704d566BF2C8 on Base)
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
        address _balancerVault,
        bytes32 _balancerPoolId
    ) {
        olas = _olas;
        usdc = _usdc;
        weth = _weth;
        router = _router;
        factory = _factory;
        l2TokenRelayer = _l2TokenRelayer;
        balancerVault = _balancerVault;
        balancerPoolId = _balancerPoolId;
    }

    function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        require(msg.value >= MIN_ETH_VALUE, "Minimum of 0.1 ETH required to summon");
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Total supply must be at least 1 million tokens");

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

    /// @dev
    function heartThisMeme(address memeToken) external payable {
        // Check for zero value
        require(msg.value > 0, "ETH amount must be greater than zero");
        // Check that the meme has been summoned
        require(memeSummons[memeToken].ethContributed > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(block.timestamp < memeSummons[memeToken].unleashTime, "Meme already unleashed");

        // Update meme token map values
        memeSummons[memeToken].ethContributed += msg.value;
        memeHearters[memeToken][msg.sender] += msg.value;

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
        uint256 burnPercentageOfUSDC = (usdcAmount * OLAS_BURN_PERCENTAGE) / 100;
        uint256 OLASAmount = _buyOLASBalancer(burnPercentageOfUSDC, olasSpotPrice);

        // Burn OLAS
        _bridgeAndBurn(OLASAmount);

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeTokenInstance = Meme(memeToken);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 lpTokenAmount = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - lpTokenAmount;

        // Create Uniswap pair with LP allocation
        address pool = _createUniswapPair(memeToken, usdcAmount, lpTokenAmount);

        // Distribute the remaining proportional to the ETH committed by each supporter
        // Contributors need to colect manually
        if (memeHearters[memeToken][msg.sender] > 0) {
            uint256 hearterContribution = memeHearters[memeToken][msg.sender];
            uint256 allocation = (heartersAmount * hearterContribution) / totalETHCommitted;
            memeHearters[memeToken][msg.sender] = 0;
            memeTokenInstance.transfer(msg.sender, allocation);
        }

        // Record the actual meme unleash time
        memeSummons[memeToken].unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummons[memeToken].heartersAmount = heartersAmount;

        emit Unleashed(memeToken, pool);
    }

    function collect(address memeToken) external {
        // Check if the meme can be collected
        require(block.timestamp < memeSummons[memeToken].summonTime + COLLECT_PERIOD, "Collect only allowed until 48 hours after summon");

        // Get hearter contribution
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        // Check for zero value
        require(hearterContribution > 0, "No token allocation");

        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Get global token info
        uint256 totalETHCommitted = memeSummons[memeToken].ethContributed;
        uint256 heartersAmount = memeSummons[memeToken].heartersAmount;

        // Allocate corresponding meme token amount to the hearter
        uint256 allocation = (heartersAmount * hearterContribution) / totalETHCommitted;
        memeHearters[memeToken][msg.sender] = 0;

        // Transfer tokens to the msg.sender
        memeTokenInstance.transfer(msg.sender, allocation);
    }

    function purge(address memeToken) external {
        // Check if the meme has been unleashed
        require(memeSummons[memeToken].unleashTime > 0, "Meme not unleashed");
        // Check if enough time has passed since the meme was summoned
        require(block.timestamp >= memeSummons[memeToken].summonTime + PURGE_PERIOD, "Purge only allowed from 48 hours after summon");

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

    function _buyUSDCUniswap(uint256 ethAmount) internal returns (uint256) {
        address[] memory path = new address[](2);
        path[0] = weth;
        path[1] = usdc;

        // Calculate price by Oracle
        (, int256 answerPrice, , , ) = IOracle(oracle).latestRoundData();
        require(answerPrice > 0, "Oracle price is incorrect");

        // Oracle returns 8 decimals, USDC has 6 decimals, need to additionally divide by 100
        // ETH: 18 decimals, denominator = 18 + 2 = 20
        uint256 limit = uint256(answerPrice) * ethAmount * SLIPPAGE / 1e20;
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

    function _createUniswapPair(address memeToken, uint256 usdcAmount, uint256 memeTokenAmount) internal returns (address pair) {
        // Create the LP
        pair = IUniswap(factory).createPair(usdc, memeToken);

        // Approve tokens for router
        IERC20(usdc).approve(router, usdcAmount);
        IERC20(memeToken).approve(router, memeTokenAmount);

        // Add USDC + meme token liquidity
        IUniswap(router).addLiquidity(
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
        IERC20(olas).approve(l2TokenRelayer, OLASAmount);

        // Data for the mainnet validate the OLAS burn
        bytes memory data = abi.encodeWithSignature("burn(uint256)", OLASAmount);

        // Bridge OLAS to mainnet to get burned
        IBridge(l2TokenRelayer).withdrawTo(olas, address(0), OLASAmount, TOKEN_GAS_LIMIT, data);

        emit OLASBridgedForBurn(olas, OLASAmount);
    }

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

    // Allow the contract to receive ETH
    receive() external payable {}
}
