from types import SimpleNamespace
import asyncio

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_can_execute_facade import RuntimeCanExecuteFacade
import victor_ai_bot.runtime_services.runtime_can_execute_facade as mod


EXTRACTED_METHODS = {
    "_annotate_can_execute",
}


class _Runtime(RuntimeCanExecuteFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                gas_mode="normal",
                gas_presets={},
                gas_limit=100_000,
                executor_address="",
                dry_run=True,
                private_key_env="VICTOR_PRIVATE_KEY",
                flashloan_fee_bps=9,
            ),
            chain=SimpleNamespace(
                univ3_swap_router="",
                balancer_vault="",
                weth="0xTokenIn",
                token_universe=["0xTokenIn"],
            ),
            safety=SimpleNamespace(minProfitAbs=1, minProfitBps=1),
        )


def _opp(amount_in, amount_out, dex="univ2"):
    leg = SimpleNamespace(amount_in=amount_in, dex=dex, token_in="0xTokenIn")
    route = SimpleNamespace(legs=[leg])
    return SimpleNamespace(route=route, min_outs=[amount_out], meta={}, can_execute=None)


async def _fake_suggest_gas(_rpc, *, mode, presets):
    return 5, 2


def _fake_profit_ok(**_kwargs):
    return SimpleNamespace(
        ok=True,
        reason="ok",
        flashloan_fee_wei=7,
        gas_cost_wei=500000,
        gas_cost_profit_token_wei=500000,
        profit_after_costs_wei=9,
    )


def test_runtime_bundle_inherits_can_execute_facade():
    assert issubclass(RuntimeBundle, RuntimeCanExecuteFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_annotate_can_execute_marks_invalid_amounts(monkeypatch):
    monkeypatch.setattr(mod, "suggest_gas", _fake_suggest_gas)
    monkeypatch.setattr(mod, "check_profit_and_repay", _fake_profit_ok)
    runtime = _Runtime()
    opp = _opp(0, 10)

    asyncio.run(runtime._annotate_can_execute(SimpleNamespace(), [opp]))

    assert opp.can_execute is False
    assert opp.meta["safety"] == {"ok": False, "reason": "invalid_amounts", "exec_ready": False}


async def _fake_block_number():
    return 321


def test_annotate_can_execute_preserves_readiness_semantics(monkeypatch):
    monkeypatch.setattr(mod, "suggest_gas", _fake_suggest_gas)
    monkeypatch.setattr(mod, "check_profit_and_repay", _fake_profit_ok)
    runtime = _Runtime()
    opp = _opp(100, 120, dex="univ3")

    asyncio.run(runtime._annotate_can_execute(SimpleNamespace(block_number=_fake_block_number), [opp]))

    assert opp.can_execute is True
    assert opp.meta["safety"]["ok"] is True
    assert opp.meta["safety"]["route_ready"] is False
    assert opp.meta["safety"]["exec_ready"] is False
    assert opp.meta["safety"]["missing"] == ["univ3_swap_router"]


def test_annotate_can_execute_blocks_research_token_borrow(monkeypatch):
    monkeypatch.setattr(mod, "suggest_gas", _fake_suggest_gas)
    monkeypatch.setattr(mod, "check_profit_and_repay", _fake_profit_ok)
    runtime = _Runtime()
    opp = _opp(100, 120)
    opp.route.legs[0].token_in = "0xResearchToken"

    asyncio.run(runtime._annotate_can_execute(SimpleNamespace(block_number=_fake_block_number), [opp]))

    assert opp.can_execute is False
    assert opp.meta["safety"]["reason"] == "input_token_not_execution_authorized"
    assert opp.meta["safety"]["execution_authority"] is False
