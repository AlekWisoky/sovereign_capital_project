from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade
from victor_ai_bot.runtime_services.runtime_multiruntime_state_facade import (
    RuntimeMultiruntimeStateFacade,
)


def _candidate(oid: str, profit_usd: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=oid,
        route_id=f"route-{oid}",
        strategy="flash_arb",
        can_execute=True,
        meta={
            "profitability": {
                "revalidated": True,
                "stale": False,
                "valid": True,
                "authoritative": True,
                "profit_after_costs_wei": str(profit_usd),
                "profit_after_costs_usd_micro": profit_usd * 1_000_000,
                "expected_profit_usd": float(profit_usd),
            },
            "execution_route_plan": {
                "executable": True,
                "selected_venues": ["univ3"],
            },
            "execution_route_runtime": {
                "ready": True,
                "degraded": False,
                "reason_codes": [],
            },
            "execution_capture": {
                "execution_ready": True,
                "route_capacity_usd": 10_000.0,
                "capital_required_usd": 1_000.0,
                "selected_provider": "provider-a",
                "provider_capacity_usd": 10_000.0,
            },
            "capital_admission": {
                "allowed": True,
                "reason_code": "ok",
                "details": {
                    "institutionalSizing": {
                        "valid": True,
                        "sizing": {
                            "execution_allowed": True,
                            "requested_notional_usd": 1_000.0,
                            "capital_authority_available": True,
                        },
                    },
                    "flashloanSizing": {"allowed": True},
                },
            },
        },
    )


class _Runtime:
    def __init__(self, candidate, *, action="trade", auto=True):
        self._opps = [candidate]
        self._pending = {}
        self._exec_task = None
        self.calls = []
        self._action = action
        self._auto_trading = auto
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)
        self.cfg = SimpleNamespace(execution=SimpleNamespace(auto_trading=auto))

    async def summary(self):
        return {
            "auto_trade_gate": {"allowed": True, "reason_code": "ok"},
            "auto_trade_recovery": {"ready": True, "blocked": False, "reason_code": "ok"},
        }

    def _safe_decide_opportunities(self, opps, **kwargs):
        return SimpleNamespace(
            action=self._action,
            opp_id=opps[0].id,
            portfolio=[opps[0].id],
            size_mult=1.0,
            borrow_mult=1.0,
        )

    def _gas_budget_remaining_wei(self):
        return 1_000_000

    def _apply_omar_to_candidate(self, candidate, decision, *, current_block):
        return candidate, decision

    async def _execute_auto(self, opp, bn, decision=None):
        self.calls.append((opp.id, bn, decision.opp_id))


@pytest.mark.asyncio
async def test_global_dispatch_targets_selected_runtime_without_changing_active_chain():
    ethereum = _Runtime(_candidate("eth-best", 40))
    base = _Runtime(_candidate("base", 20))
    bundle = SimpleNamespace(
        _runtimes={"ethereum": ethereum, "base": base},
        _active_chain="base",
        GLOBAL_AUTO_SELECT=True,
        _global_auto_task=None,
    )

    dispatched = await RuntimeMultiruntimeStateFacade.dispatch_selected_auto_trade(
        bundle, current_block=123
    )
    await asyncio.sleep(0)

    assert dispatched is True
    assert bundle._active_chain == "base"
    assert ethereum.calls == [("eth-best", 123, "eth-best")]
    assert base.calls == []


@pytest.mark.asyncio
async def test_global_dispatch_never_selects_blocked_or_unavailable_candidate():
    ethereum = _Runtime(_candidate("eth", 40), action="skip")
    base = _Runtime(_candidate("base", 20))
    bundle = SimpleNamespace(
        _runtimes={"ethereum": ethereum, "base": base},
        _active_chain="base",
        GLOBAL_AUTO_SELECT=True,
        _global_auto_task=None,
    )

    dispatched = await RuntimeMultiruntimeStateFacade.dispatch_selected_auto_trade(
        bundle, current_block=456
    )
    await asyncio.sleep(0)

    assert dispatched is False
    assert ethereum.calls == []
    assert base.calls == []


class _ActiveRuntime(RuntimeDecisionFacade):
    def __init__(self, owner, *, auto=True):
        self._multiruntime_owner = owner
        self._auto_trading = auto
        self._cb = SimpleNamespace(allow_auto_trading=lambda: True)
        self._opps = [_candidate("local", 1)]
        self._exec_task = None


def test_active_auto_dispatch_hands_off_to_global_selector_when_enabled():
    owner = SimpleNamespace(
        GLOBAL_AUTO_SELECT=True,
        _active_chain="base",
        _runtimes={},
        _global_auto_task=None,
    )
    active = _ActiveRuntime(owner)
    owner._runtimes["base"] = active

    dispatched = active._maybe_dispatch_auto_trade(current_block=789, decision=None)

    assert dispatched is True
    assert owner._global_auto_task is not None
    owner._global_auto_task.cancel()


def test_global_handoff_requires_active_auto_authority():
    owner = SimpleNamespace(
        GLOBAL_AUTO_SELECT=True,
        _active_chain="base",
        _runtimes={},
        _global_auto_task=None,
    )
    active = _ActiveRuntime(owner, auto=False)
    owner._runtimes["base"] = active

    dispatched = active._maybe_dispatch_auto_trade(current_block=789, decision=None)

    assert dispatched is False
    assert owner._global_auto_task is None
