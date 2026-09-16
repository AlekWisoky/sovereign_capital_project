import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot import execution
from victor_ai_bot.execution import execution_outcome_from_result, try_execute_opportunity


ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot'


class SafetyResult(SimpleNamespace):
    ok: bool = True
    flashloan_fee_wei: int = 0
    gas_cost_wei: int = 0
    profit_after_costs_wei: int = 0
    reason: str = ''


class DummyRpc:
    async def estimate_gas(self, tx):
        return 21000

    async def get_nonce(self, addr):
        return 1

    async def send_raw_tx(self, raw):
        return SimpleNamespace(ok=True, result='0xtx', error='')

    async def send_private_tx(self, raw, max_block_number=None):
        return SimpleNamespace(ok=True, result='0xtx', error='')


class DummyOpp:
    def __init__(self):
        leg = SimpleNamespace(
            amount_in='100',
            min_out='120',
            dex='uni',
            venue='venue-a',
            token_in='0xTokenIn',
            token_out='0xTokenOut',
            data='0x',
        )
        self.route = SimpleNamespace(legs=[leg])
        self.min_outs = ['120']
        self.meta = {}
        self.route_id = 'route-1'
        self.expected_profit_raw = '20'

    def copy(self, deep=False):
        clone = DummyOpp()
        clone.meta = dict(self.meta)
        clone.route_id = self.route_id
        clone.expected_profit_raw = self.expected_profit_raw
        clone.min_outs = list(self.min_outs)
        clone.route.legs[0].amount_in = self.route.legs[0].amount_in
        clone.route.legs[0].min_out = self.route.legs[0].min_out
        clone.route.legs[0].dex = self.route.legs[0].dex
        clone.route.legs[0].venue = self.route.legs[0].venue
        clone.route.legs[0].token_in = self.route.legs[0].token_in
        clone.route.legs[0].token_out = self.route.legs[0].token_out
        clone.route.legs[0].data = self.route.legs[0].data
        return clone


def make_cfg(*, dry_run: bool, executor_address: str = '', profit_to: str = ''):
    return SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=dry_run,
            max_submit_per_block=1,
            send_mode='public',
            gas_mode='fast',
            gas_presets={},
            gas_limit=21000,
            private_key_env='EXEC_KEY',
            from_address='0xSender',
            executor_address=executor_address,
            profit_to=profit_to,
            deadline_seconds=30,
            flashloan_fee_bps=9,
            flash_provider='aave',
        ),
        safety=SimpleNamespace(
            minProfitAbs=1,
            minProfitBps=1,
            slippage_bps=50,
            max_borrow_amount='0',
            require_estimate_gas=False,
            require_simulation=False,
            mev_adversarial_eval_enabled=False,
        ),
        chain=SimpleNamespace(chain_id=1),
    )


async def _fake_suggest_gas(rpc, mode=None, presets=None):
    return 1, 1


def _fake_safety(*args, **kwargs):
    return SafetyResult(ok=True, flashloan_fee_wei=1, gas_cost_wei=1, profit_after_costs_wei=25)


@pytest.mark.asyncio
async def test_invalid_profiler_is_safely_ignored(monkeypatch):
    monkeypatch.setattr(execution, 'suggest_gas', _fake_suggest_gas)
    monkeypatch.setattr(execution, 'check_profit_and_repay', _fake_safety)

    result = await try_execute_opportunity(
        DummyRpc(),
        DummyRpc(),
        make_cfg(dry_run=True),
        DummyOpp(),
        current_block=10,
        last_submitted_block=9,
        profiler=object(),
    )

    assert result.ok is True
    assert result.reason == 'dry_run_ok_no_executor'
    assert 'latency_stages_ms' not in (result.plan or {})


@pytest.mark.asyncio
async def test_route_plan_programmer_bug_is_not_swallowed(monkeypatch):
    def boom(*, opp, plan):
        raise NameError('route plan bug')

    monkeypatch.setattr(execution, 'apply_execution_route_plan', boom)

    with pytest.raises(NameError):
        await try_execute_opportunity(
            DummyRpc(),
            DummyRpc(),
            make_cfg(dry_run=True),
            DummyOpp(),
            current_block=10,
            last_submitted_block=9,
            decision=SimpleNamespace(metadata={'execution_route_plan': {'selected_venues': ['venue-a']}}),
        )


@pytest.mark.asyncio
async def test_missing_eth_account_dependency_is_explicitly_degraded(monkeypatch):
    monkeypatch.setattr(execution, 'suggest_gas', _fake_suggest_gas)
    monkeypatch.setattr(execution, 'check_profit_and_repay', _fake_safety)
    monkeypatch.setattr(execution, 'build_execute_calldata', lambda **kwargs: ('0x1234', 'route-1'))
    monkeypatch.setattr(execution, 'Account', None)
    monkeypatch.setenv('EXEC_KEY', '0x' + '11' * 32)

    result = await try_execute_opportunity(
        DummyRpc(),
        DummyRpc(),
        make_cfg(dry_run=False, executor_address='0xExecutor', profit_to='0xProfit'),
        DummyOpp(),
        current_block=10,
        last_submitted_block=9,
    )

    assert result.ok is False
    assert result.reason == 'missing_eth_account_dependency'
    outcome = execution_outcome_from_result(result)
    assert outcome.status == 'degraded'
    assert outcome.degraded_mode == 'disabled'


def test_execution_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'execution.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            broad.append('bare except')
            continue
        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
            broad.append('except Exception')
    assert broad == []


@pytest.mark.asyncio
async def test_prepared_route_plan_is_not_applied_twice(monkeypatch):
    calls = {"count": 0}

    def _counting_apply(*, opp, plan):
        calls["count"] += 1
        return opp

    monkeypatch.setattr(execution, 'suggest_gas', _fake_suggest_gas)
    monkeypatch.setattr(execution, 'check_profit_and_repay', _fake_safety)
    monkeypatch.setattr(execution, 'apply_execution_route_plan', _counting_apply)

    opp = DummyOpp()
    route_plan = {"selected_venues": ["venue-a"], "executable": True}
    opp.meta = {
        "execution_route_plan_applied": True,
        "execution_route_plan": route_plan,
        "execution_route_runtime": {"degraded": False},
    }

    result = await try_execute_opportunity(
        DummyRpc(),
        DummyRpc(),
        make_cfg(dry_run=True),
        opp,
        current_block=10,
        last_submitted_block=9,
        decision=SimpleNamespace(metadata={'execution_route_plan': route_plan}),
    )

    assert result.ok is True
    assert result.reason == 'dry_run_ok_no_executor'
    assert calls["count"] == 0


class _RelayRpc:
    async def estimate_gas(self, tx):
        return 21_000

    async def get_nonce(self, addr):
        return 1

    async def send_raw_tx(self, raw):
        return SimpleNamespace(ok=True, result="0xpublic", error="")

    async def send_private_tx(self, raw, max_block_number=None):
        raise AssertionError("private RPC must be reached through RelayClient")


class _RelayAccount:
    address = "0x" + "1" * 40

    @classmethod
    def from_key(cls, key):
        return cls()

    @classmethod
    def sign_transaction(cls, tx, key):
        return SimpleNamespace(raw_transaction=b"signed")


class _RelayOpp:
    route = SimpleNamespace(
        legs=[
            SimpleNamespace(
                amount_in="100",
                min_out="120",
                dex="univ3",
                venue="0x" + "2" * 40,
                token_in="0x" + "3" * 40,
                token_out="0x" + "4" * 40,
                data="0x",
            )
        ]
    )
    min_outs = ["120"]
    meta = {}
    route_id = "route-1"


def _relay_cfg():
    return SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=False,
            max_submit_per_block=1,
            send_mode="private",
            gas_mode="fast",
            gas_presets={},
            gas_limit=21_000,
            private_key_env="EXEC_KEY",
            from_address="0x" + "1" * 40,
            executor_address="0x" + "5" * 40,
            profit_to="0x" + "1" * 40,
            deadline_seconds=30,
            flashloan_fee_bps=9,
            flash_provider="aave",
        ),
        safety=SimpleNamespace(
            minProfitAbs=1,
            minProfitBps=1,
            slippage_bps=50,
            max_borrow_amount="0",
            require_estimate_gas=False,
            require_simulation=False,
            mev_adversarial_eval_enabled=False,
        ),
        chain=SimpleNamespace(chain_id=1),
    )


@pytest.mark.asyncio
async def test_private_execution_routes_through_relay_client(monkeypatch):
    class _Relay:
        calls = []

        def __init__(self, rpc, *, quality_store=None):
            self.rpc = rpc
            self.quality_store = quality_store

        async def send_private_transaction(self, raw_tx_hex, *, max_block=None):
            self.calls.append({
                "raw": raw_tx_hex,
                "max_block": max_block,
                "quality_store": self.quality_store,
            })
            return SimpleNamespace(ok=True, result="0xprivate", error="")

    monkeypatch.setattr(execution, "RelayClient", _Relay)
    monkeypatch.setattr(execution, "Account", _RelayAccount)
    monkeypatch.setattr(execution, "build_execute_calldata", lambda **kwargs: ("0x1234", "route-1"))
    monkeypatch.setattr(
        execution,
        "check_profit_and_repay",
        lambda **kwargs: SimpleNamespace(
            ok=True,
            flashloan_fee_wei=1,
            gas_cost_wei=1,
            profit_after_costs_wei=10,
            reason="ok",
        ),
    )

    async def _gas(*args, **kwargs):
        return 1, 1

    monkeypatch.setattr(execution, "suggest_gas", _gas)
    monkeypatch.setenv("EXEC_KEY", "0x" + "11" * 32)
    quality_store = object()

    result = await try_execute_opportunity(
        _RelayRpc(),
        _RelayRpc(),
        _relay_cfg(),
        _RelayOpp(),
        current_block=100,
        last_submitted_block=99,
        endpoint_quality=quality_store,
    )

    assert result.ok is True
    assert result.tx_hash == "0xprivate"
    assert _Relay.calls == [
        {"raw": "0x7369676e6564", "max_block": 102, "quality_store": quality_store}
    ]
