from __future__ import annotations

import asyncio

from victor_ai_bot.runtime_legacy import MultiRuntimeBundle


class _Runtime:
    def __init__(self):
        self.calls = []

    def set_settings(self, **kwargs):
        self.calls.append(("set_settings", kwargs.copy()))

    async def snapshot(self):
        return {"ok": True, "kind": "snapshot"}

    async def admin_snapshot(self):
        return {"ok": True, "kind": "admin"}

    async def execute_opportunity_by_id(self, opp_id: str, **kwargs):
        self.calls.append(("execute", opp_id, kwargs.copy()))
        return {"ok": True, "id": opp_id, **kwargs}

    async def poll_and_update_receipt(self, tx_hash: str):
        self.calls.append(("poll", tx_hash))
        return {"ok": True, "tx_hash": tx_hash}

    async def pnl_summary(self, window: int = 50):
        self.calls.append(("pnl_summary", window))
        return {"ok": True, "window": window}

    def brain_state(self):
        return {"ok": True, "brain": "active"}

    async def summary(self):
        return {"ok": True, "kind": "summary"}


class _Pnl:
    def __init__(self):
        self.calls = []

    async def income_breakdown(self, window: int = 3600):
        self.calls.append(window)
        return {"ok": True, "window": window}


class _TelemetryRuntime(_Runtime):
    def __init__(self, *, slow_summary: bool):
        super().__init__()
        self.slow_summary = slow_summary

    def market_pipeline_telemetry_state(self):
        return {
            "ok": True,
            "chain": "arbitrum",
            "scanner": {"alive": True},
        }

    async def summary(self):
        if self.slow_summary:
            await asyncio.sleep(0.05)
        return {
            "ok": True,
            "auto_trade_gate": {"allowed": False, "stage": "shadow"},
            "auto_trade_recovery": {"active": False},
        }


async def _exercise_market_pipeline_telemetry_timeout() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "base"
    bundle._runtimes = {
        "base": _TelemetryRuntime(slow_summary=False),
        "arbitrum": _TelemetryRuntime(slow_summary=True),
    }
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    payload = await bundle.market_pipeline_telemetry_readonly()

    assert payload["chains"]["base"]["scanner"]["alive"] is True
    assert payload["chains"]["arbitrum"]["scanner"]["alive"] is True
    assert payload["chains"]["arbitrum"]["admission"]["status"] == "unavailable"
    assert payload["chains"]["arbitrum"]["admission"]["reason_code"] == "market_pipeline_admission_summary_unavailable"


def test_multiruntime_market_pipeline_preserves_telemetry_on_summary_timeout() -> None:
    asyncio.run(_exercise_market_pipeline_telemetry_timeout())


def test_multiruntime_state_facade_preserves_active_chain_contract() -> None:
    active = _Runtime()
    other = _Runtime()
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "active"
    bundle._runtimes = {"active": active, "other": other}
    bundle._pnl = _Pnl()
    bundle.SNAPSHOT_TIMEOUT_S = 0.01
    bundle.ALLOW_AUTO_ALL = False
    bundle.chains = lambda: ["active", "other"]

    bundle.set_settings(auto_trading=True, paper=False)
    assert active.calls[0] == ("set_settings", {"auto_trading": True, "paper": False})

    assert bundle.set_settings_for("missing", auto_trading=True) is False
    assert bundle.set_settings_for("other", auto_trading=True, paper=True) is True
    assert other.calls[0] == ("set_settings", {"auto_trading": False, "paper": True})

    snap = asyncio.run(bundle.snapshot())
    admin = asyncio.run(bundle.admin_snapshot())
    execute = asyncio.run(
        bundle.execute_opportunity_by_id(
            "opp-1", mode="manual", amount_in_override="123", force_dry_run=True
        )
    )
    receipt = asyncio.run(bundle.poll_and_update_receipt("0xabc"))
    pnl_summary = asyncio.run(bundle.pnl_summary(window=77))
    pnl_income = asyncio.run(bundle.pnl_income(window=88))
    summary_all = asyncio.run(bundle.summary_all())

    assert snap == {"ok": True, "kind": "snapshot"}
    assert admin["multichain"] == {"active": "active", "chains": ["active", "other"]}
    assert execute["ok"] is True and execute["id"] == "opp-1"
    assert receipt == {"ok": True, "tx_hash": "0xabc"}
    assert pnl_summary == {"ok": True, "window": 77}
    assert pnl_income == {"ok": True, "window": 88}
    assert bundle.brain_state() == {"ok": True, "brain": "active"}
    assert summary_all["active"] == "active"
    assert summary_all["chains"]["active"]["ok"] is True


def test_multiruntime_state_facade_degrades_income_breakdown_failure() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "active"
    bundle._runtimes = {"active": _Runtime()}
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    class _BadPnl:
        async def income_breakdown(self, window: int = 3600):
            raise RuntimeError("boom")

    bundle._pnl = _BadPnl()
    assert asyncio.run(bundle.pnl_income()) == {"ok": False, "error": "income_breakdown_failed"}
