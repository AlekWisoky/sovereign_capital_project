// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @notice Minimal interfaces (no external deps)
interface IERC20 {
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    function approve(address, uint256) external returns (bool);
    function allowance(address, address) external view returns (uint256);
}

/// @notice Minimal SafeERC20-style helpers that tolerate non-standard ERC20s.
/// @dev We avoid external deps (OpenZeppelin) on purpose.
library SafeERC20 {
    function _call(address token, bytes memory data) private {
        (bool ok, bytes memory ret) = token.call(data);
        require(ok, "erc20_call_failed");
        // Return data is optional.
        if (ret.length > 0) {
            require(abi.decode(ret, (bool)), "erc20_op_failed");
        }
    }

    function safeTransfer(address token, address to, uint256 amount) internal {
        _call(token, abi.encodeWithSelector(IERC20.transfer.selector, to, amount));
    }

    function safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        _call(token, abi.encodeWithSelector(IERC20.transferFrom.selector, from, to, amount));
    }

    function safeApprove(address token, address spender, uint256 amount) internal {
        _call(token, abi.encodeWithSelector(IERC20.approve.selector, spender, amount));
    }
}

interface IAaveV3Pool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

interface ICurvePool {
    function exchange(int128 i, int128 j, uint256 dx, uint256 min_dy) external returns (uint256);
    function exchange_underlying(int128 i, int128 j, uint256 dx, uint256 min_dy) external returns (uint256);
}

interface ISwapRouterV3 {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

interface IBalancerVault {
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
        address recipient;
        bool toInternalBalance;
    }
    function swap(
        SingleSwap calldata singleSwap,
        FundManagement calldata funds,
        uint256 limit,
        uint256 deadline
    ) external returns (uint256 amountCalculated);

    function flashLoan(
        address recipient,
        address[] calldata tokens,
        uint256[] calldata amounts,
        bytes calldata userData
    ) external;
}

contract VictorArbExecutor {
    using SafeERC20 for address;

    // --- types ---
    struct Leg {
        uint8 dex;            // 1=univ3, 2=curve, 3=balancer
        address venue;        // router/pool/vault
        address tokenIn;
        address tokenOut;
        uint256 minOut;
        bytes32 aux;          // dex-specific params
    }

    // --- config ---
    address public owner;
    address public immutable WETH;
    // Optional stablecoin helpers (for operator UX workflows).
    address public USDC;
    address public USDT;

    // Versioning (prevents silent ABI drift).
    uint32 public constant EXECUTOR_ABI_VERSION = 2;
    uint32 public constant EXECUTOR_IMPL_VERSION = 2;
    IAaveV3Pool public immutable aavePool;
    IBalancerVault public immutable balancerVault;
    ISwapRouterV3 public immutable univ3SwapRouter;

    mapping(address => bool) public spenderAllowed;
    mapping(address => bool) public withdrawalAllowed;

    // --- safety rails ---
    uint16 public maxSlippageBps = 200; // 2% default
    uint256 private _reentrancyLock = 1;

    // Flash-loan in-flight context guard.
    // This replaces a generic nonReentrant guard on callbacks which breaks
    // synchronous flash-loan flows.
    bool private _inFlight;
    bytes32 private _inFlightHash;
    uint8 private _inFlightProvider;

    // --- events ---
    event ArbExecuted(bytes32 indexed routeId, address indexed token, uint256 amountBorrowed, uint256 profit, uint8 provider);
    event Withdrawal(address indexed token, address indexed to, uint256 amount);
    event ConvertedAndWithdrawn(address indexed tokenIn, address indexed tokenOut, uint256 amountIn, uint256 amountOut, address to);
    event SpenderAllowed(address indexed spender, bool allowed);
    event WithdrawalAllowed(address indexed to, bool allowed);

    // --- errors ---
    error NotOwner();
    error Deadline();
    error SpenderNotAllowed();
    error MinOut();
    error MinProfit();
    error BadProvider();
    error Reentrancy();
    error BadInitiator();
    error InFlightMismatch();
    error BadStable();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_reentrancyLock != 1) revert Reentrancy();
        _reentrancyLock = 2;
        _;
        _reentrancyLock = 1;
    }

    constructor(address weth, address _aavePool, address _balVault, address _swapRouter) {
        owner = msg.sender;
        WETH = weth;
        aavePool = IAaveV3Pool(_aavePool);
        balancerVault = IBalancerVault(_balVault);
        univ3SwapRouter = ISwapRouterV3(_swapRouter);

        // Safe defaults: core dependencies are allowed spenders.
        spenderAllowed[_aavePool] = true;
        spenderAllowed[_balVault] = true;
        spenderAllowed[_swapRouter] = true;

        // Safe default: owner can withdraw to itself.
        withdrawalAllowed[msg.sender] = true;
    }

    function setOwner(address newOwner) external onlyOwner {
        owner = newOwner;
    }

    function setSpenderAllowed(address spender, bool allowed) external onlyOwner {
        spenderAllowed[spender] = allowed;
        emit SpenderAllowed(spender, allowed);
    }

    function setWithdrawalAllowed(address to, bool allowed) external onlyOwner {
        withdrawalAllowed[to] = allowed;
        emit WithdrawalAllowed(to, allowed);
    }

    function setMaxSlippageBps(uint16 bps) external onlyOwner {
        // 0..2000 (20%) hard cap
        require(bps <= 2000, "slippage_too_high");
        maxSlippageBps = bps;
    }

    function setStableTokens(address usdc, address usdt) external onlyOwner {
        // Set to zero to disable.
        USDC = usdc;
        USDT = usdt;
    }

    function executorVersion() external pure returns (uint32 abiVersion, uint32 implVersion) {
        return (EXECUTOR_ABI_VERSION, EXECUTOR_IMPL_VERSION);
    }

    function withdraw(address token, address to, uint256 amount) external onlyOwner nonReentrant {
        require(withdrawalAllowed[to], "dest_not_allowed");
        token.safeTransfer(to, amount);
        emit Withdrawal(token, to, amount);
    }

    /// @notice Convert tokenIn -> (USDC/USDT) via UniV3 and withdraw to `to`.
    /// @dev This is an operator UX helper for off-ramping to stables.
    function convertAndWithdraw(
        address tokenIn,
        address tokenOut,
        uint256 amountIn,
        uint256 minOut,
        address to,
        uint24 fee,
        uint256 deadline
    ) external onlyOwner nonReentrant {
        require(withdrawalAllowed[to], "dest_not_allowed");
        if (!(tokenOut == USDC || tokenOut == USDT)) revert BadStable();
        if (block.timestamp > deadline) revert Deadline();

        uint256 amountOut;
        if (tokenIn == tokenOut) {
            require(amountIn >= minOut, "min_out");
            amountOut = amountIn;
        } else {
            _approveIfNeeded(tokenIn, address(univ3SwapRouter), amountIn);
            ISwapRouterV3.ExactInputSingleParams memory p = ISwapRouterV3.ExactInputSingleParams({
                tokenIn: tokenIn,
                tokenOut: tokenOut,
                fee: fee,
                recipient: address(this),
                deadline: deadline,
                amountIn: amountIn,
                amountOutMinimum: minOut,
                sqrtPriceLimitX96: 0
            });
            amountOut = univ3SwapRouter.exactInputSingle(p);
            if (amountOut < minOut) revert MinOut();
        }

        tokenOut.safeTransfer(to, amountOut);
        emit ConvertedAndWithdrawn(tokenIn, tokenOut, amountIn, amountOut, to);
    }

    // --- entrypoint ---
    // provider: 1=Aave, 2=Balancer
    function execute(
        uint8 provider,
        address borrowToken,
        uint256 amountBorrow,
        uint256 minProfit,
        address profitTo,
        uint256 deadline,
        bytes32 routeId,
        Leg[] calldata legs
    ) external onlyOwner {
        if (block.timestamp > deadline) revert Deadline();
        if (!withdrawalAllowed[profitTo]) revert MinProfit(); // reuse error as deny

        bytes memory userData = abi.encode(provider, borrowToken, amountBorrow, minProfit, profitTo, deadline, routeId, legs);

        // Establish in-flight guard before handing control to the flash-loan provider.
        _inFlight = true;
        _inFlightProvider = provider;
        _inFlightHash = keccak256(userData);

        if (provider == 1) {
            aavePool.flashLoanSimple(address(this), borrowToken, amountBorrow, userData, 0);
        } else if (provider == 2) {
            address[] memory tokens = new address[](1);
            uint256[] memory amounts = new uint256[](1);
            tokens[0] = borrowToken;
            amounts[0] = amountBorrow;
            balancerVault.flashLoan(address(this), tokens, amounts, userData);
        } else {
            revert BadProvider();
        }

        // Clear in-flight guard after provider call returns.
        _inFlight = false;
        _inFlightProvider = 0;
        _inFlightHash = bytes32(0);
    }

    // --- Aave callback ---
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool) {
        require(msg.sender == address(aavePool), "only_aave");
        if (initiator != address(this)) revert BadInitiator();

        // In-flight context must match the one established in execute().
        if (!_inFlight || _inFlightProvider != 1 || keccak256(params) != _inFlightHash) revert InFlightMismatch();
        (
            uint8 provider,
            address borrowToken,
            uint256 amountBorrow,
            uint256 minProfit,
            address profitTo,
            uint256 deadline,
            bytes32 routeId,
            Leg[] memory legs
        ) = abi.decode(params, (uint8,address,uint256,uint256,address,uint256,bytes32,Leg[]));
        require(provider == 1, "provider_mismatch");
        require(borrowToken == asset && amountBorrow == amount, "asset_mismatch");
        if (block.timestamp > deadline) revert Deadline();

        uint256 balStart = IERC20(borrowToken).balanceOf(address(this));
        uint256 preExisting = balStart > amount ? (balStart - amount) : 0;
        uint256 repay = amount + premium;
        _runLegs(legs, amount, deadline);
        uint256 bal = IERC20(borrowToken).balanceOf(address(this));
        // Profit assertion is net of flash fee and must not consume pre-existing balance.
        if (bal < preExisting + repay) revert MinProfit();
        uint256 profit = bal - preExisting - repay;
        if (profit < minProfit) revert MinProfit();

        // repay
        _approveIfNeeded(borrowToken, address(aavePool), repay);
        // transfer profit
        borrowToken.safeTransfer(profitTo, profit);
        emit ArbExecuted(routeId, borrowToken, amountBorrow, profit, provider);

        // Clear in-flight context as early as possible (defense-in-depth).
        _inFlight = false;
        _inFlightProvider = 0;
        _inFlightHash = bytes32(0);
        return true;
    }

    // --- Balancer callback ---
    function receiveFlashLoan(
        address[] calldata tokens,
        uint256[] calldata amounts,
        uint256[] calldata feeAmounts,
        bytes calldata userData
    ) external {
        require(msg.sender == address(balancerVault), "only_balancer");
        require(tokens.length == 1 && amounts.length == 1 && feeAmounts.length == 1, "only_single_asset");

        // In-flight context must match the one established in execute().
        if (!_inFlight || _inFlightProvider != 2 || keccak256(userData) != _inFlightHash) revert InFlightMismatch();
        (
            uint8 provider,
            address borrowToken,
            uint256 amountBorrow,
            uint256 minProfit,
            address profitTo,
            uint256 deadline,
            bytes32 routeId,
            Leg[] memory legs
        ) = abi.decode(userData, (uint8,address,uint256,uint256,address,uint256,bytes32,Leg[]));
        require(provider == 2, "provider_mismatch");
        require(borrowToken == tokens[0] && amountBorrow == amounts[0], "asset_mismatch");
        if (block.timestamp > deadline) revert Deadline();

        uint256 balStart = IERC20(borrowToken).balanceOf(address(this));
        uint256 preExisting = balStart > amounts[0] ? (balStart - amounts[0]) : 0;
        uint256 repay = amounts[0] + feeAmounts[0];
        _runLegs(legs, amounts[0], deadline);
        uint256 bal = IERC20(borrowToken).balanceOf(address(this));
        if (bal < preExisting + repay) revert MinProfit();
        uint256 profit = bal - preExisting - repay;
        if (profit < minProfit) revert MinProfit();

        // repay to vault
        borrowToken.safeTransfer(address(balancerVault), repay);
        borrowToken.safeTransfer(profitTo, profit);
        emit ArbExecuted(routeId, borrowToken, amountBorrow, profit, provider);

        // Clear in-flight context as early as possible (defense-in-depth).
        _inFlight = false;
        _inFlightProvider = 0;
        _inFlightHash = bytes32(0);
    }

    // --- internals ---
    function _approveIfNeeded(address token, address spender, uint256 amount) internal {
        if (!spenderAllowed[spender]) revert SpenderNotAllowed();
        uint256 allow = IERC20(token).allowance(address(this), spender);
        if (allow < amount) {
            // Some tokens (e.g., USDT) require allowance reset to 0 first.
            token.safeApprove(spender, 0);
            token.safeApprove(spender, type(uint256).max);
        }
    }

    function _runLegs(Leg[] memory legs, uint256 firstAmountIn, uint256 deadline) internal {
        uint256 amountIn = firstAmountIn;
        for (uint256 i = 0; i < legs.length; i++) {
            Leg memory leg = legs[i];
            if (leg.dex == 1) {
                // univ3: aux low 24 bits are fee
                uint24 fee = uint24(uint256(leg.aux) & 0xFFFFFF);
                _approveIfNeeded(leg.tokenIn, address(univ3SwapRouter), amountIn);
                ISwapRouterV3.ExactInputSingleParams memory p = ISwapRouterV3.ExactInputSingleParams({
                    tokenIn: leg.tokenIn,
                    tokenOut: leg.tokenOut,
                    fee: fee,
                    recipient: address(this),
                    deadline: deadline,
                    amountIn: amountIn,
                    amountOutMinimum: leg.minOut,
                    sqrtPriceLimitX96: 0
                });
                uint256 out = univ3SwapRouter.exactInputSingle(p);
                if (out < leg.minOut) revert MinOut();
                amountIn = out;
            } else if (leg.dex == 2) {
                // curve: aux: i (8 bits) | j (8 bits) | underlying (1 bit at bit 16)
                int128 ci = int128(uint128(uint256(leg.aux) & 0xFF));
                int128 cj = int128(uint128((uint256(leg.aux) >> 8) & 0xFF));
                bool underlying = ((uint256(leg.aux) >> 16) & 0x1) == 1;
                _approveIfNeeded(leg.tokenIn, leg.venue, amountIn);
                uint256 out;
                if (underlying) {
                    out = ICurvePool(leg.venue).exchange_underlying(ci, cj, amountIn, leg.minOut);
                } else {
                    out = ICurvePool(leg.venue).exchange(ci, cj, amountIn, leg.minOut);
                }
                if (out < leg.minOut) revert MinOut();
                amountIn = out;
            } else if (leg.dex == 3) {
                // balancer swap: aux is poolId
                _approveIfNeeded(leg.tokenIn, address(balancerVault), amountIn);
                IBalancerVault.SingleSwap memory s = IBalancerVault.SingleSwap({
                    poolId: leg.aux,
                    kind: IBalancerVault.SwapKind.GIVEN_IN,
                    assetIn: leg.tokenIn,
                    assetOut: leg.tokenOut,
                    amount: amountIn,
                    userData: ""
                });
                IBalancerVault.FundManagement memory f = IBalancerVault.FundManagement({
                    sender: address(this),
                    fromInternalBalance: false,
                    recipient: address(this),
                    toInternalBalance: false
                });
                uint256 out = balancerVault.swap(s, f, leg.minOut, deadline);
                if (out < leg.minOut) revert MinOut();
                amountIn = out;
            } else {
                revert("unknown_dex");
            }
        }
    }
}
