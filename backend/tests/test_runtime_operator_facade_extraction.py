from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_operator_facade import RuntimeOperatorFacade


class _Decision:
    def __init__(self):
        self.mode = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode


class _PnL:
    async def summary(self, window: int = 50) -> dict:
        return {"window": window, "realized": "7"}


class _StateService:
    async def snapshot(self, runtime):
        return {"kind": "snapshot", "chain": "ethereum"}

    async def summary(self, runtime):
        return {"kind": "summary", "opps": 2}

    async def admin_snapshot(self, runtime):
        return {"kind": "admin", "errors": []}


class _Eff:
    def __init__(self, payload=None, fail=False):
        self.payload = payload or {"efficiencyPct": 91.0}
        self.fail = fail

    def snapshot(self):
        if self.fail:
            raise RuntimeError("boom")
        return dict(self.payload)


class _Runtime(RuntimeOperatorFacade):
    def __init__(self):
        self._pnl = _PnL()
        self._ws_clients = []
        self._fioa = None
        self._auto_trading = False
        self.metrics = SimpleNamespace(gas_mode="fast", send_mode="private")
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                auto_trading=False,
                dry_run=True,
                withdraw_mode="txdata",
                gas_mode="fast",
                send_mode="private",
                auto_reinvest_enabled=False,
                reinvest_rate=0,
                base_borrow_amount="0",
                brain_mode="off",
            ),
            safety=SimpleNamespace(
                minProfitAbs="100",
                minProfitBps=10,
                slippage_bps=20,
                max_borrow_amount="1000",
                require_estimate_gas=True,
                require_simulation=True,
                custom="ok",
            ),
        )
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(
                auto_reinvest_enabled=False,
                reinvest_rate_pct=0,
                base_borrow_amount_wei=0,
            )
        )
        self._decision = _Decision()
        self._state_lock = asyncio.Lock()
        self._state_service = _StateService()
        self._eff = _Eff()


async def _collect_snapshots(runtime: _Runtime):
    return await runtime.snapshot(), await runtime.summary(), await runtime.admin_snapshot()


def test_runtime_operator_facade_exposes_async_summary_methods():
    runtime = _Runtime()
    pnl = asyncio.run(runtime.pnl_summary(window=25))
    snap, summary, admin = asyncio.run(_collect_snapshots(runtime))
    assert pnl == {"window": 25, "realized": "7"}
    assert snap["kind"] == "snapshot"
    assert summary["kind"] == "summary"
    assert admin["kind"] == "admin"


def test_runtime_operator_facade_manages_websocket_subscriptions():
    runtime = _Runtime()
    q = runtime.subscribe()
    assert q in runtime._ws_clients
    runtime.unsubscribe(q)
    assert q not in runtime._ws_clients
    runtime.unsubscribe(q)


def test_runtime_operator_facade_updates_settings_and_safety():
    runtime = _Runtime()
    runtime.set_settings(
        auto_trading=True,
        gas_mode="standard",
        send_mode="public",
        auto_reinvest_enabled=True,
        reinvest_rate=120,
        brain_mode="invalid",
        base_borrow_amount="-9",
        dry_run=False,
    )
    assert runtime._auto_trading is True
    assert runtime.cfg.execution.auto_trading is True
    assert runtime.metrics.gas_mode == "standard"
    assert runtime.metrics.send_mode == "public"
    assert runtime._bankroll.cfg.auto_reinvest_enabled is True
    assert runtime._bankroll.cfg.reinvest_rate_pct == 100
    assert runtime.cfg.execution.brain_mode == "off"
    assert runtime._decision.mode == "off"
    assert runtime.cfg.execution.base_borrow_amount == "0"
    assert runtime._bankroll.cfg.base_borrow_amount_wei == 0
    assert runtime.cfg.execution.dry_run is False

    runtime.set_safety(
        minProfitAbs=12,
        minProfitBps="7",
        slippage_bps="5",
        max_borrow_amount=22,
        require_estimate_gas=0,
        require_simulation=1,
        custom="updated",
        ignored="nope",
    )
    assert runtime.cfg.safety.minProfitAbs == "12"
    assert runtime.cfg.safety.minProfitBps == 7
    assert runtime.cfg.safety.slippage_bps == 5
    assert runtime.cfg.safety.max_borrow_amount == "22"
    assert runtime.cfg.safety.require_estimate_gas is False
    assert runtime.cfg.safety.require_simulation is True
    assert runtime.cfg.safety.custom == "updated"
    assert not hasattr(runtime.cfg.safety, "ignored")


def test_runtime_operator_facade_efficiency_state_is_best_effort():
    runtime = _Runtime()
    assert runtime.efficiency_state()["efficiencyPct"] == 91.0
    runtime._eff = _Eff(fail=True)
    assert runtime.efficiency_state() == {}
