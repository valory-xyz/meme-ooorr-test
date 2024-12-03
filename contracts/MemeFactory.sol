// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";
import {IUniswapV3} from "./interfaces/IUniswapV3.sol";

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);

    /// @dev Transfers the token amount.
    /// @param to Address to transfer to.
    /// @param amount The amount to transfer.
    /// @return True if the function execution is successful.
    function transfer(address to, uint256 amount) external returns (bool);

    /// @dev Burns tokens.
    /// @param amount Token amount to burn.
    function burn(uint256 amount) external;
}

/// @title MemeFactory - a smart contract factory for Meme Token creation
/// @dev This contract let's:
///      1) Any msg.sender summons a meme by contributing at least 0.01 ETH (or equivalent native asset for other chains).
///      2) Within 24h of a meme being summoned, any msg.sender can heart a meme (thereby becoming a hearter).
///         This requires the msg.sender to send a non-zero ETH value, which gets recorded as a contribution.
///      3) After 24h of a meme being summoned, any msg.sender can unleash the meme. This creates a liquidity pool for
///         the meme and schedules the distribution of the rest of the tokens to the hearters, proportional to their
///         contributions.
///      4) After the meme is being unleashed any hearter can collect their share of the meme token.
///      5) After 24h of a meme being unleashed, any msg.sender can purge the uncollected meme token allocations of hearters.
/// @notice 10% of the ETH contributed to a meme gets retained upon unleashing of the meme, that can later be
///         converted to OLAS and scheduled for burning (on Ethereum mainnet). The remainder of the ETH contributed (90%)
///         is contributed to an LP, together with 50% of the token supply of the meme.
///         The remaining 50% of the meme token supply goes to hearters. The LP token is held forever by MemeBase,
///         guaranteeing lasting liquidity in the meme token.
///
///         Example:
///         - Agent Smith would summonThisMeme with arguments Smiths Army, SMTH, 1_000_000_000 and $500 worth of ETH
///         - Agent Brown would heartThisMeme with $250 worth of ETH
///         - Agent Jones would heartThisMeme with $250 worth of ETH
///         - Any agent, let's say Brown, would call unleashThisMeme. This would:
///             - create a liquidity pool with $SMTH:$ETH, containing 500_000_000 SMTH tokens and $900 worth of ETH
///             - schedule $100 worth of OLAS for burning on Ethereum mainnet
///             - Brown would receive 125_000_000 worth of $SMTH
///         - Agent Smith would collectThisMeme and receive 250_000_000 worth of $SMTH
///         - Agent Jones would forget to collectThisMeme
///         - Any agent would call purgeThisMeme, which would cause Agent Jones's allocation of 125_000_000 worth of
///           $SMTH to be burned.
abstract contract MemeFactory {
    event OLASJourneyToAscendance(uint256 amount);
    event Summoned(address indexed summoner, address indexed memeToken, uint256 nativeTokenContributed);
    event Hearted(address indexed hearter, address indexed memeToken, uint256 amount);
    event Unleashed(address indexed unleasher, address indexed memeToken, uint256 indexed lpTokenId,
        uint256 liquidity, uint256  nativeAmountForOLASBurn);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 remainingAmount);
    event FeesCollected(address indexed feeCollector, address indexed memeToken, uint256 nativeTokenAmount, uint256 memeTokenAmount);

    // Params struct
    struct FactoryParams {
        address olas;
        address nativeToken;
        address uniV3PositionManager;
        address buyBackBurner;
        uint256 minNativeTokenValue;
    }

    // Meme Summon struct
    struct MemeSummon {
        // Native token contributed to the meme launch
        uint256 nativeTokenContributed;
        // Summon timestamp
        uint256 summonTime;
        // Unleash timestamp
        uint256 unleashTime;
        // Finalized hearters amount
        uint256 heartersAmount;
        // UniswapV3 position token Id
        uint256 positionId;
    }

    // Version number
    string public constant VERSION = "0.1.1";
    // Total supply minimum value
    uint256 public constant MIN_TOTAL_SUPPLY = 1_000_000 ether;
    // Unleash delay after token summoning
    uint256 public constant UNLEASH_DELAY = 24 hours;
    // Collect delay after token unleashing
    uint256 public constant COLLECT_DELAY = 24 hours;
    // Percentage of OLAS to burn (10%)
    uint256 public constant OLAS_BURN_PERCENTAGE = 10;
    // Percentage of initial supply for liquidity pool (50%)
    uint256 public constant LP_PERCENTAGE = 50;
    // Uniswap V3 fee tier of 1%
    uint24 public constant FEE_TIER = 10_000;
    /// @dev The minimum tick that corresponds to a selected fee tier
    int24 public constant MIN_TICK = -887200;
    /// @dev The maximum tick that corresponds to a selected fee tier
    int24 public constant MAX_TICK = -MIN_TICK;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Minimum value of native token deposit
    uint256 public immutable minNativeTokenValue;
    // OLAS token address
    address public immutable olas;
    // Native token address (ERC-20 equivalent)
    address public immutable nativeToken;
    // Uniswap V3 position manager address
    address public immutable uniV3PositionManager;
    // BuyBackBurner address
    address public immutable buyBackBurner;

    // Number of meme tokens
    uint256 public numTokens;
    // Native token (ERC-20) scheduled to be converted to OLAS for Ascendance
    uint256 public scheduledForAscendance;
    // Reentrancy lock
    uint256 internal _locked = 1;

    // Map of meme token => Meme summon struct
    mapping(address => MemeSummon) public memeSummons;
    // Map of mem token => (map of hearter => native token balance)
    mapping(address => mapping(address => uint256)) public memeHearters;
    // Map of account => activity counter
    mapping(address => uint256) public mapAccountActivities;
    // Set of all meme tokens created by this contract
    address[] public memeTokens;

    /// @dev MemeFactory constructor
    constructor(FactoryParams memory factoryParams) {
        olas = factoryParams.olas;
        nativeToken = factoryParams.nativeToken;
        uniV3PositionManager = factoryParams.uniV3PositionManager;
        buyBackBurner = factoryParams.buyBackBurner;
        minNativeTokenValue = factoryParams.minNativeTokenValue;
    }

    /// @dev Transfers native token to be later converted to OLAS for burn.
    /// @param amount Native token amount.
    function _transferToLaterBurn(uint256 amount) internal virtual {
        (bool result, ) = buyBackBurner.call{value: amount}("");
        
        require(result, "Transfer failed");

        emit OLASJourneyToAscendance(amount);
    }

    /// @dev Calculates sqrtPriceX96 based on reserves of token0 and token1.
    /// @param reserve0 Reserve of token0.
    /// @param reserve1 Reserve of token1.
    /// @return sqrtPriceX96 The calculated square root price scaled by 2^96.
    function _calculateSqrtPriceX96(address memeToken, uint256 reserve0, uint256 reserve1) public view returns (uint160 sqrtPriceX96) {
        require(reserve0 > 0 && reserve1 > 0, "Reserves must be greater than zero");

        // Ensure correct token order
        (uint256 adjustedAmountA, uint256 adjustedAmountB) = nativeToken < memeToken
            ? (reserve0, reserve1)
            : (reserve1, reserve0);

        // Calculate the price ratio (B/A) scaled by 1e18 to avoid floating point issues
        uint256 priceX96 = (adjustedAmountB * 1e18) / adjustedAmountA;

        // Calculate the square root of the price ratio in X96 format
        return uint160(_sqrt(priceX96) * 2**48);
    }

    // TODO Figure out and maybe use another method?
    /// @dev Square root function using Babylonian method.
    /// @param x Input value.
    /// @return y Square root result.
    function _sqrt(uint256 x) private pure returns (uint256 y) {
        uint256 z = (x + 1) / 2;
        y = x;
        while (z < y) {
            y = z;
            z = (x / z + z) / 2;
        }
    }

    /// @dev Creates native token + meme token LP and adds liquidity.
    /// @param memeToken Meme token address.
    /// @param nativeTokenAmount Native token amount.
    /// @param memeTokenAmount Meme token amount.
    /// @return positionId LP position token Id.
    /// @return liquidity Obtained LP liquidity.
    function _createUniswapPair(
        address memeToken,
        uint256 nativeTokenAmount,
        uint256 memeTokenAmount
    ) internal returns (uint256 positionId, uint256 liquidity) {
        // Ensure token order matches Uniswap convention
        (address token0, address token1, uint256 amount0, uint256 amount1) = nativeToken < memeToken
            ? (nativeToken, memeToken, nativeTokenAmount, memeTokenAmount)
            : (memeToken, nativeToken, memeTokenAmount, nativeTokenAmount);

        // Get or create the pool
        //address pool = IUniswapV3Factory(uniV3Factory).getPool(token0, token1, FEE_TIER);
        // If condition added for clarity, will always evaluate to true in this design
        //if (pool == address(0)) {
        // Initialize the pool with the sqrtPriceX96
        uint160 sqrtPriceX96 = _calculateSqrtPriceX96(memeToken, nativeTokenAmount, memeTokenAmount);
        IUniswapV3(uniV3PositionManager).createAndInitializePoolIfNecessary(token0, token1,
            FEE_TIER, sqrtPriceX96);
        //}

        // Approve tokens for router
        IERC20(token0).approve(uniV3PositionManager, amount0);
        IERC20(token1).approve(uniV3PositionManager, amount1);

        // Add native token + meme token liquidity
        IUniswapV3.MintParams memory params = IUniswapV3.MintParams({
            token0: token0,
            token1: token1,
            fee: FEE_TIER,
            tickLower: MIN_TICK,
            tickUpper: MAX_TICK,
            amount0Desired: amount0,
            amount1Desired: amount1,
            amount0Min: 0, // Accept any amount of token0
            amount1Min: 0, // Accept any amount of token1
            recipient: address(this),
            deadline: block.timestamp
        });

        (positionId, liquidity, , ) = IUniswapV3(uniV3PositionManager).mint(params);
    }

    /// @dev Collects fees from LP position, burns the meme token part and schedules for ascendance the native token part.
    /// @param memeToken Meme token address.
    /// @param positionId LP position ID.
    function _collectFees(address memeToken, uint256 positionId) internal {
        // Fetch the position to get token0 and token1
        (
            ,
            ,
            address token0,
            ,
            ,
            ,
            ,
            ,
            ,
            ,
            ,

        ) = IUniswapV3(uniV3PositionManager).positions(positionId);

        // Determine which token is the meme token and which is the native token
        bool memeIsToken0 = memeToken == token0;

        IUniswapV3.CollectParams memory params = IUniswapV3.CollectParams({
            tokenId: positionId,
            recipient: address(this),
            amount0Max: type(uint128).max,
            amount1Max: type(uint128).max
        });

        // Get the corresponding tokens
        (uint256 amount0, uint256 amount1) =
            IUniswapV3(uniV3PositionManager).collect(params);

        uint256 nativeAmountForOLASBurn;
        uint256 memeAmountToBurn;

        if (memeIsToken0) {
            memeAmountToBurn = amount0;
            nativeAmountForOLASBurn = amount1;
        } else {
            memeAmountToBurn = amount1;
            nativeAmountForOLASBurn = amount0;
        }

        // Burn meme tokens
        IERC20(memeToken).burn(memeAmountToBurn);

        // Account for redemption logic
        // All funds ever collected are already wrapped
        uint256 adjustedNativeAmountForAscendance = _redemptionLogic(nativeAmountForOLASBurn);

        // Schedule native token amount for ascendance
        scheduledForAscendance += adjustedNativeAmountForAscendance;

        emit FeesCollected(msg.sender, memeToken, nativeAmountForOLASBurn, memeAmountToBurn);
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    /// @param heartersAmount Total hearters meme token amount.
    /// @param hearterContribution Hearter contribution.
    /// @param totalNativeTokenCommitted Total native token contributed for the token launch.
    function _collect(
        address memeToken,
        uint256 heartersAmount,
        uint256 hearterContribution,
        uint256 totalNativeTokenCommitted
    ) internal {
        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Allocate corresponding meme token amount to the hearter
        uint256 allocation = (heartersAmount * hearterContribution) / totalNativeTokenCommitted;

        // Zero the allocation
        memeHearters[memeToken][msg.sender] = 0;

        // Transfer meme token amount to the msg.sender
        memeTokenInstance.transfer(msg.sender, allocation);

        emit Collected(msg.sender, memeToken, allocation);
    }

    /// @dev Redemption logic.
    /// @param nativeAmountForOLASBurn Native token amount (wrapped) for burning.
    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal virtual returns (uint256 adjustedNativeAmountForAscendance);

    /// @dev Native token amount to wrap.
    /// @param nativeTokenAmount Native token amount to be wrapped.
    function _wrap(uint256 nativeTokenAmount) internal virtual;

    /// @dev Summons meme token.
    /// @param name Token name.
    /// @param symbol Token symbol.
    /// @param totalSupply Token total supply.
    function summonThisMeme(
        string memory name,
        string memory symbol,
        uint256 totalSupply
    ) external payable {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Check for minimum native token value
        require(msg.value >= minNativeTokenValue, "Minimum native token value is required to summon");
        // Check for minimum total supply
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Minimum total supply is not met");
        // Check for max total supply as to practical limits for the Uniswap LP creation
        require(totalSupply < type(uint128).max, "Maximum total supply overflow");

        // Create a new token
        Meme newTokenInstance = new Meme(name, symbol, DECIMALS, totalSupply);
        address memeToken = address(newTokenInstance);

        // Check for non-zero token address
        require(memeToken != address(0), "Token creation failed");

        // Initiate meme token map values
        memeSummons[memeToken] = MemeSummon(msg.value, block.timestamp, 0, 0, 0);
        memeHearters[memeToken][msg.sender] = msg.value;

        // Push token into the global list of tokens
        memeTokens.push(memeToken);
        numTokens = memeTokens.length;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Summoned(msg.sender, memeToken, msg.value);
        emit Hearted(msg.sender, memeToken, msg.value);

        _locked = 1;
    }

    /// @dev Hearts the meme token with native token contribution.
    /// @param memeToken Meme token address.
    function heartThisMeme(address memeToken) external payable {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Check for zero value
        require(msg.value > 0, "Native token amount must be greater than zero");

        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Get the total native token committed to this meme
        uint256 totalNativeTokenCommitted = memeSummon.nativeTokenContributed;

        // Check that the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not yet summoned");
        // Check if the token has been unleashed
        require(memeSummon.unleashTime == 0, "Meme already unleashed");

        // Update meme token map values
        totalNativeTokenCommitted += msg.value;
        memeSummon.nativeTokenContributed = totalNativeTokenCommitted;
        memeHearters[memeToken][msg.sender] += msg.value;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        emit Hearted(msg.sender, memeToken, msg.value);

        _locked = 1;
    }

    /// @dev Unleashes the meme token.
    /// @param memeToken Meme token address.
    function unleashThisMeme(address memeToken) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get the meme summon info
        MemeSummon storage memeSummon = memeSummons[memeToken];

        // Get the total native token amount committed to this meme
        uint256 totalNativeTokenCommitted = memeSummon.nativeTokenContributed;

        // Check if the meme has been summoned
        require(memeSummon.unleashTime == 0, "Meme already unleashed");
        // Check if the meme has been summoned
        require(memeSummon.summonTime > 0, "Meme not summoned");
        // Check the unleash timestamp
        require(block.timestamp >= memeSummon.summonTime + UNLEASH_DELAY, "Cannot unleash yet");

        // Wrap native token to its ERC-20 version
        // All funds ever contributed to a given meme are wrapped here.
        _wrap(totalNativeTokenCommitted);

        // Put aside native token to buy OLAS with the burn percentage of the total native token amount committed
        uint256 nativeAmountForOLASBurn = (totalNativeTokenCommitted * OLAS_BURN_PERCENTAGE) / 100;

        // Adjust native token amount
        uint256 nativeAmountForLP = totalNativeTokenCommitted - nativeAmountForOLASBurn;

        uint256 adjustedNativeAmountForAscendance = _redemptionLogic(nativeAmountForOLASBurn);

        // Schedule native token amount for ascendance
        scheduledForAscendance += adjustedNativeAmountForAscendance;

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeTokenInstance = Meme(memeToken);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 memeAmountForLP = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - memeAmountForLP;

        // Create Uniswap pair with LP allocation
        (uint256 positionId, uint256 liquidity) = _createUniswapPair(memeToken, nativeAmountForLP, memeAmountForLP);

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;
        // Record position token Id
        memeSummon.positionId = positionId;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        if (hearterContribution > 0) {
            _collect(memeToken, heartersAmount, hearterContribution, totalNativeTokenCommitted);
        }

        emit Unleashed(msg.sender, memeToken, positionId, liquidity, nativeAmountForOLASBurn);

        _locked = 1;
    }

    /// @dev Collects meme token allocation.
    /// @param memeToken Meme token address.
    function collectThisMeme(address memeToken) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if the meme can be collected
        require(block.timestamp <= memeSummon.unleashTime + COLLECT_DELAY, "Collect only allowed until 24 hours after unleash");

        // Get hearter contribution
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        // Check for zero value
        require(hearterContribution > 0, "No token allocation");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Collect the token
        _collect(memeToken, memeSummon.heartersAmount, hearterContribution, memeSummon.nativeTokenContributed);

        _locked = 1;
    }

    /// @dev Purges uncollected meme token allocation.
    /// @param memeToken Meme token address.
    function purgeThisMeme(address memeToken) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Get the meme summon info
        MemeSummon memory memeSummon = memeSummons[memeToken];

        // Check if the meme has been summoned
        require(memeSummon.unleashTime > 0, "Meme not unleashed");
        // Check if enough time has passed since the meme was unleashed
        require(block.timestamp > memeSummon.unleashTime + COLLECT_DELAY, "Purge only allowed from 24 hours after unleash");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Get meme token instance
        Meme memeTokenInstance = Meme(memeToken);

        // Burn all remaining tokens in this contract
        uint256 remainingBalance = memeTokenInstance.balanceOf(address(this));
        // Check the remaining balance is positive
        require(remainingBalance > 0, "Has been purged or nothing to purge");
        // Burn the remaining balance
        memeTokenInstance.burn(remainingBalance);

        emit Purged(memeToken, remainingBalance);

        _locked = 1;
    }

    /// @dev Transfers native token to later be converted to OLAS for burn.
    function scheduleForAscendance() external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        uint256 amount = scheduledForAscendance;
        require(amount > 0, "Nothing to send");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Transfer native token to be converted to OLAS and burnt
        _transferToLaterBurn(amount);

        _locked = 1;
    }

    /// @dev Collects all accumulated LP fees.
    /// @param tokens List of tokens to be iterated over.
    function collectFees(address[] memory tokens) external {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        for (uint256 i = 0; i < tokens.length; ++i) {
            MemeSummon memory memeSummon = memeSummons[tokens[i]];
            _collectFees(tokens[i], memeSummon.positionId);
        }

        _locked = 1;
    }

    /// @dev Allows the contract to receive native token
    receive() external payable {}
}
