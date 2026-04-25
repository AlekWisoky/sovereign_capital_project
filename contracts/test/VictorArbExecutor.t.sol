// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "../src/VictorArbExecutor.sol";
import "./mocks/MockERC20.sol";
import "./mocks/Caller.sol";
import "./mocks/MockSwapRouterV3.sol";
import "./mocks/MockAavePool.sol";
import "./mocks/MockBalancerVault.sol";

contract VictorArbExecutorTest {
    VictorArbExecutor ex;
    MockERC20 token;
    MockERC20 usdc;
    Caller caller;
    MockSwapRouterV3 router;
    MockAavePool aave;
    MockBalancerVault balancer;
    address constant DEST = address(0xBEEF);

    function setUp() public {
        token = new MockERC20("Mock", "MOCK", 18);
        usdc = new MockERC20("USDC", "USDC", 18);
        caller = new Caller();
        router = new MockSwapRouterV3();
        aave = new MockAavePool();
        balancer = new MockBalancerVault();
        ex = new VictorArbExecutor(address(token), address(aave), address(balancer), address(router));
        ex.setWithdrawalAllowed(DEST, true);
        ex.setStableTokens(address(usdc), address(0));
    }

    function _uniLeg(uint256 minOut) internal view returns (VictorArbExecutor.Leg[] memory legs) {
        legs = new VictorArbExecutor.Leg[](1);
        legs[0] = VictorArbExecutor.Leg({
            dex: 1,
            venue: address(router),
            tokenIn: address(token),
            tokenOut: address(token),
            minOut: minOut,
            aux: bytes32(uint256(3000))
        });
    }

    function _balLeg(uint256 minOut) internal view returns (VictorArbExecutor.Leg[] memory legs) {
        legs = new VictorArbExecutor.Leg[](1);
        legs[0] = VictorArbExecutor.Leg({
            dex: 3,
            venue: address(balancer),
            tokenIn: address(token),
            tokenOut: address(token),
            minOut: minOut,
            aux: bytes32(uint256(1))
        });
    }

    function test_onlyOwner_withdraw_and_allowlist() public {
        token.mint(address(ex), 1000 ether);

        (bool ok0,) = address(ex).call(abi.encodeWithSelector(ex.withdraw.selector, address(token), address(0xCAFE), 1 ether));
        require(!ok0, "withdraw should revert when dest not allowlisted");

        ex.withdraw(address(token), DEST, 5 ether);
        require(token.balanceOf(DEST) == 5 ether, "dest should receive tokens");
    }

    function test_onlyOwner_restrictions() public {
        bytes memory data1 = abi.encodeWithSelector(ex.setWithdrawalAllowed.selector, address(0xBEEF), true);
        (bool ok1, bytes memory ret1) = caller.call(address(ex), data1);
        require(!ok1, "non-owner setWithdrawalAllowed should revert");
        require(ret1.length >= 4, "missing revert data");
        require(bytes4(ret1) == VictorArbExecutor.NotOwner.selector, "unexpected revert selector");

        VictorArbExecutor.Leg[] memory legs = new VictorArbExecutor.Leg[](0);
        bytes memory data2 = abi.encodeWithSelector(ex.execute.selector, uint8(1), address(token), 1 ether, 0, DEST, block.timestamp + 1, bytes32(0), legs);
        (bool ok2, bytes memory ret2) = caller.call(address(ex), data2);
        require(!ok2, "non-owner execute should revert");
        require(ret2.length >= 4, "missing revert data");
        require(bytes4(ret2) == VictorArbExecutor.NotOwner.selector, "unexpected revert selector for execute");
    }

    function test_callback_invariants_onlyPools() public {
        (bool ok1,) = address(ex).call(abi.encodeWithSelector(ex.executeOperation.selector, address(token), 1 ether, 0, address(ex), bytes("")));
        require(!ok1, "executeOperation should only be callable by aave pool");

        address[] memory tokens = new address[](1);
        uint256[] memory amounts = new uint256[](1);
        uint256[] memory fees = new uint256[](1);
        tokens[0] = address(token);
        amounts[0] = 1 ether;
        fees[0] = 0;
        (bool ok2,) = address(ex).call(abi.encodeWithSelector(ex.receiveFlashLoan.selector, tokens, amounts, fees, bytes("")));
        require(!ok2, "receiveFlashLoan should only be callable by balancer vault");
    }

    function test_execute_rejects_profitTo_not_allowlisted() public {
        VictorArbExecutor.Leg[] memory legs = new VictorArbExecutor.Leg[](0);
        (bool ok,) = address(ex).call(
            abi.encodeWithSelector(ex.execute.selector, uint8(1), address(token), 1 ether, 0, address(0xABCD), block.timestamp + 1, bytes32(0), legs)
        );
        require(!ok, "execute should revert when profitTo not allowlisted");
    }

    function test_cant_spend_unless_spender_allowed() public {
        token.mint(address(ex), 10 ether);
        ex.setSpenderAllowed(address(router), false);
        (bool ok,) = address(ex).call(
            abi.encodeWithSelector(ex.convertAndWithdraw.selector, address(token), address(usdc), 10 ether, 1 ether, DEST, uint24(3000), block.timestamp + 100)
        );
        require(!ok, "spender not allowlisted should revert");
    }

    function test_convert_and_withdraw_success() public {
        token.mint(address(ex), 10 ether);
        router.setOutBps(10100);
        ex.convertAndWithdraw(address(token), address(usdc), 10 ether, 10 ether, DEST, 3000, block.timestamp + 100);
        require(usdc.balanceOf(DEST) == 101 ether / 10, "converted stable should be withdrawn");
    }

    function test_aave_success_path() public {
        router.setOutBps(10200);
        aave.setPremiumBps(50);
        VictorArbExecutor.Leg[] memory legs = _uniLeg(101 ether);
        ex.execute(1, address(token), 100 ether, 1 ether, DEST, block.timestamp + 100, bytes32(uint256(1)), legs);
        require(token.balanceOf(DEST) == 15 ether / 10, "profit should be paid to destination");
    }

    function test_balancer_success_path() public {
        balancer.setOutBps(10300);
        balancer.setFeeBps(50);
        VictorArbExecutor.Leg[] memory legs = _balLeg(101 ether);
        ex.execute(2, address(token), 100 ether, 1 ether, DEST, block.timestamp + 100, bytes32(uint256(2)), legs);
        require(token.balanceOf(DEST) == 25 ether / 10, "balancer profit should be paid to destination");
    }

    function test_minOut_reverts() public {
        router.setOutBps(9900);
        aave.setPremiumBps(0);
        VictorArbExecutor.Leg[] memory legs = _uniLeg(100 ether);
        (bool ok,) = address(ex).call(
            abi.encodeWithSelector(ex.execute.selector, uint8(1), address(token), 100 ether, 0, DEST, block.timestamp + 100, bytes32(uint256(3)), legs)
        );
        require(!ok, "minOut should revert");
    }

    function test_minProfit_reverts_when_trade_not_profitable() public {
        router.setOutBps(10010);
        aave.setPremiumBps(50);
        VictorArbExecutor.Leg[] memory legs = _uniLeg(100 ether);
        (bool ok,) = address(ex).call(
            abi.encodeWithSelector(ex.execute.selector, uint8(1), address(token), 100 ether, 1, DEST, block.timestamp + 100, bytes32(uint256(4)), legs)
        );
        require(!ok, "min profit should revert when route is not profitable");
    }

    function test_profit_cannot_come_from_preExisting_balance() public {
        token.mint(address(ex), 5 ether);
        aave.setPremiumBps(50);
        VictorArbExecutor.Leg[] memory legs = new VictorArbExecutor.Leg[](0);
        (bool ok,) = address(ex).call(
            abi.encodeWithSelector(ex.execute.selector, uint8(1), address(token), 100 ether, 0, DEST, block.timestamp + 100, bytes32(uint256(5)), legs)
        );
        require(!ok, "pre-existing balance should not count as profit");
    }

    function testFuzz_setMaxSlippageBps(uint16 bps) public {
        if (bps <= 2000) {
            ex.setMaxSlippageBps(bps);
            require(ex.maxSlippageBps() == bps, "slippage should update within cap");
        } else {
            (bool ok,) = address(ex).call(abi.encodeWithSelector(ex.setMaxSlippageBps.selector, bps));
            require(!ok, "slippage above cap should revert");
        }
    }

    function test_executor_version_exposed() public view {
        (uint32 abiVersion, uint32 implVersion) = ex.executorVersion();
        require(abiVersion == 2, "abi version mismatch");
        require(implVersion == 2, "impl version mismatch");
    }

    function test_convert_rejects_non_stable_out() public {
        token.mint(address(ex), 1 ether);
        (bool ok, bytes memory ret) = address(ex).call(
            abi.encodeWithSelector(ex.convertAndWithdraw.selector, address(token), address(token), 1 ether, 1 ether, DEST, uint24(3000), block.timestamp + 100)
        );
        require(!ok, "convert should reject non-stable out token");
        require(ret.length >= 4, "missing revert data");
        require(bytes4(ret) == VictorArbExecutor.BadStable.selector, "unexpected revert selector");
    }

    function test_convert_rejects_expired_deadline() public {
        token.mint(address(ex), 1 ether);
        (bool ok, bytes memory ret) = address(ex).call(
            abi.encodeWithSelector(ex.convertAndWithdraw.selector, address(token), address(usdc), 1 ether, 1 ether, DEST, uint24(3000), block.timestamp - 1)
        );
        require(!ok, "convert should reject expired deadline");
        require(ret.length >= 4, "missing revert data");
        require(bytes4(ret) == VictorArbExecutor.Deadline.selector, "unexpected deadline selector");
    }

    function test_execute_rejects_unknown_provider() public {
        VictorArbExecutor.Leg[] memory legs = new VictorArbExecutor.Leg[](0);
        (bool ok, bytes memory ret) = address(ex).call(
            abi.encodeWithSelector(ex.execute.selector, uint8(9), address(token), 1 ether, 0, DEST, block.timestamp + 1, bytes32(uint256(99)), legs)
        );
        require(!ok, "execute should reject unknown provider");
        require(ret.length >= 4, "missing revert data");
        require(bytes4(ret) == VictorArbExecutor.BadProvider.selector, "unexpected bad provider selector");
    }

}
