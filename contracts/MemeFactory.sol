// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Meme} from "./Meme.sol";

// ERC20 interface
interface IERC20 {
    /// @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
    /// @param spender Account address that will be able to transfer tokens on behalf of the caller.
    /// @param amount Token amount.
    /// @return True if the function execution is successful.
    function approve(address spender, uint256 amount) external returns (bool);
}

interface IOracle {
    /// @dev Updates time average price.
    function updatePrice() external returns (bool);

    /// @dev Validates price according to slippage.
    function validatePrice(uint256 slippage) external view returns (bool);
}

// UniswapV2 interface
interface IUniswap {
    /// @dev Gets LP pair address.
    function getPair(address tokenA, address tokenB) external returns (address pair);

    /// @dev Adds liquidity to the LP consisting of tokenA and tokenB.
    function addLiquidity(address tokenA, address tokenB, uint256 amountADesired, uint256 amountBDesired,
        uint256 amountAMin, uint256 amountBMin, address to, uint256 deadline)
        external returns (uint256 amountA, uint256 amountB, uint256 liquidity);
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
    event OLASJourneyToAscendance(address indexed olas, uint256 amount);
    event Summoned(address indexed summoner, address indexed memeToken, uint256 nativeTokenContributed);
    event Hearted(address indexed hearter, address indexed memeToken, uint256 amount);
    event Unleashed(address indexed unleasher, address indexed memeToken, address indexed lpPairAddress,
        uint256 liquidity, uint256  nativeAmountForOLASBurn);
    event Collected(address indexed hearter, address indexed memeToken, uint256 allocation);
    event Purged(address indexed memeToken, uint256 remainingAmount);

    // Params struct
    struct FactoryParams {
        address olas;
        address nativeToken;
        address uniV2router;
        address uniV2factory;
        address oracle;
        uint256 maxSlippage;
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
    // L1 OLAS Burner address
    address public constant OLAS_BURNER = 0x51eb65012ca5cEB07320c497F4151aC207FEa4E0;
    // Meme token decimals
    uint8 public constant DECIMALS = 18;

    // Minimum value of native token deposit
    uint256 public immutable minNativeTokenValue;
    // Oracle max slippage for ERC-20 native token <=> OLAS
    uint256 public immutable maxSlippage;
    // OLAS token address
    address public immutable olas;
    // Native token address (ERC-20 equivalent)
    address public immutable nativeToken;
    // Uniswap V2 router address
    address public immutable uniV2router;
    // Uniswap V2 factory address
    address public immutable uniV2factory;
    // Oracle address
    address public immutable oracle;

    // Number of meme tokens
    uint256 public numTokens;
    // Native token (ERC-20) scheduled to be converted to OLAS for Ascendance
    uint256 public scheduledForAscendance;
    // Tokens to be bridged
    uint256 public bridgeAmount;
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
        uniV2router = factoryParams.uniV2router;
        uniV2factory = factoryParams.uniV2factory;
        oracle = factoryParams.oracle;
        maxSlippage = factoryParams.maxSlippage;
        minNativeTokenValue = factoryParams.minNativeTokenValue;
    }

    /// @dev Buys OLAS on DEX.
    /// @param nativeTokenAmount Native token amount.
    /// @return Obtained OLAS amount.
    function _buyOLAS(uint256 nativeTokenAmount) internal virtual returns (uint256);

    /// @dev Bridges OLAS amount back to L1 and burns.
    /// @param OLASAmount OLAS amount.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @param bridgePayload Optional additional bridge payload.
    /// @return msg.value leftovers if partially utilized by the bridge.
    function _bridgeAndBurn(
        uint256 OLASAmount,
        uint256 tokenGasLimit,
        bytes memory bridgePayload
    ) internal virtual returns (uint256);

    /// @dev Creates reference token + meme token LP and adds liquidity.
    /// @param memeToken Meme token address.
    /// @param nativeTokenAmount Native token amount.
    /// @param memeTokenAmount Meme token amount.
    /// @return pair reference token + meme token LP address.
    /// @return liquidity Obtained LP liquidity.
    function _createUniswapPair(
        address memeToken,
        uint256 nativeTokenAmount,
        uint256 memeTokenAmount
    ) internal returns (address pair, uint256 liquidity) {
        // Approve tokens for router
        IERC20(nativeToken).approve(uniV2router, nativeTokenAmount);
        IERC20(memeToken).approve(uniV2router, memeTokenAmount);

        // Add reference token + meme token liquidity
        (, , liquidity) = IUniswap(uniV2router).addLiquidity(
            nativeToken,
            memeToken,
            nativeTokenAmount,
            memeTokenAmount,
            0, // Accept any amount of reference token
            0, // Accept any amount of meme token
            address(this),
            block.timestamp
        );

        // Get the pair address
        pair = IUniswap(uniV2factory).getPair(nativeToken, memeToken);
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

    function _redemptionLogic(uint256 nativeAmountForOLASBurn) internal virtual;

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
        // Check for minimum native token value
        require(msg.value >= minNativeTokenValue, "Minimum native token value is required to summon");
        // Check for minimum total supply
        require(totalSupply >= MIN_TOTAL_SUPPLY, "Minimum total supply is not met");
        // TODO: check for max total supply, must be UNI-compatible of uint112 and check for overflow if max(uint112) * big(heartAmount)

        // Create a new token
        Meme newTokenInstance = new Meme(name, symbol, DECIMALS, totalSupply);
        address memeToken = address(newTokenInstance);

        // Check for non-zero token address
        require(memeToken != address(0), "Token creation failed");

        // Initiate meme token map values
        memeSummons[memeToken] = MemeSummon(msg.value, block.timestamp, 0, 0);
        memeHearters[memeToken][msg.sender] = msg.value;

        // Push token into the global list of tokens
        memeTokens.push(memeToken);
        numTokens = memeTokens.length;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Update prices in oracle
        IOracle(oracle).updatePrice();

        emit Summoned(msg.sender, memeToken, msg.value);
        emit Hearted(msg.sender, memeToken, msg.value);
    }

    /// @dev Hearts the meme token with native token contribution.
    /// @param memeToken Meme token address.
    function heartThisMeme(address memeToken) external payable {
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

        // Update prices in oracle
        IOracle(oracle).updatePrice();

        emit Hearted(msg.sender, memeToken, msg.value);
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

        // Put aside reference token to buy OLAS with the burn percentage of the total native token amount committed
        uint256 nativeAmountForOLASBurn = (totalNativeTokenCommitted * OLAS_BURN_PERCENTAGE) / 100;

        // Adjust reference token amount
        uint256 nativeAmountForLP = totalNativeTokenCommitted - nativeAmountForOLASBurn;

        _redemptionLogic(nativeAmountForOLASBurn);

        // Schedule native token amount for ascendance
        scheduledForAscendance += nativeAmountForOLASBurn;

        // Calculate LP token allocation according to LP percentage and distribution to supporters
        Meme memeTokenInstance = Meme(memeToken);
        uint256 totalSupply = memeTokenInstance.totalSupply();
        uint256 memeAmountForLP = (totalSupply * LP_PERCENTAGE) / 100;
        uint256 heartersAmount = totalSupply - memeAmountForLP;

        // Wrap native token to its ERC-20 version, where applicable
        _wrap(nativeAmountForLP);

        // Create Uniswap pair with LP allocation
        (address pool, uint256 liquidity) = _createUniswapPair(memeToken, nativeAmountForLP, memeAmountForLP);

        // Record the actual meme unleash time
        memeSummon.unleashTime = block.timestamp;
        // Record the hearters distribution amount for this meme
        memeSummon.heartersAmount = heartersAmount;

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Allocate to the token hearter unleashing the meme
        uint256 hearterContribution = memeHearters[memeToken][msg.sender];
        if (hearterContribution > 0) {
            _collect(memeToken, heartersAmount, hearterContribution, totalNativeTokenCommitted);
        }

        // Update prices in oracle
        IOracle(oracle).updatePrice();

        emit Unleashed(msg.sender, memeToken, pool, liquidity, nativeAmountForOLASBurn);

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

        // Update prices in oracle
        IOracle(oracle).updatePrice();

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

        // Update prices in oracle
        IOracle(oracle).updatePrice();

        emit Purged(memeToken, remainingBalance);

        _locked = 1;
    }

    /// @dev Converts collected reference token to OLAS.
    function scheduleOLASForAscendance(uint256 amount, uint256 slippage) external virtual {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        // Slippage limit requirement
        require(slippage <= maxSlippage, "Slippage limit overflow");

        if (amount > scheduledForAscendance) {
            amount = scheduledForAscendance;
        }
        require(amount > 0, "Nothing to burn");

        // TOFIX:shouldn't this be inside _buyOLAS as its chain specific?
        // Apply slippage protection
        require(IOracle(oracle).validatePrice(slippage), "Slippage limit is breached");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        // Wrap native token to its ERC-20 version, where applicable
        _wrap(amount);

        uint256 OLASAmount = _buyOLAS(amount);

        bridgeAmount += OLASAmount;
        scheduledForAscendance -= amount;

        _locked = 1;
    }


    /// @dev Bridges OLAS to Ethereum mainnet for burn.
    /// @param tokenGasLimit Token gas limit for bridging OLAS to L1.
    /// @param bridgePayload Optional additional bridge payload.
    function sendToHigherHeights(uint256 tokenGasLimit, bytes memory bridgePayload) external payable {
        require(_locked == 1, "Reentrancy guard");
        _locked = 2;

        require(bridgeAmount > 0, "Nothing to bridge");

        // Record msg.sender activity
        mapAccountActivities[msg.sender]++;

        uint256 OLASAmount = bridgeAmount;
        bridgeAmount = 0;
        // Burn OLAS
        uint256 leftovers = _bridgeAndBurn(OLASAmount, tokenGasLimit, bridgePayload);

        // Send leftover amount, if any, back to the sender
        if (leftovers > 0) {
            // If the call fails, ignore to avoid the attack that would prevent this function from executing
            // solhint-disable-next-line avoid-low-level-calls
            tx.origin.call{value: leftovers}("");
        }

        // Update prices in oracle
        IOracle(oracle).updatePrice();

        _locked = 1;
    }

    /// @dev Allows the contract to receive native token
    receive() external payable {}
}
