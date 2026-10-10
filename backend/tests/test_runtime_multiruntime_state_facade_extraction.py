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
        self.summary_calls = 0

    def market_pipeline_telemetry_state(self):
        return {
            "ok": True,
            "chain": "arbitrum",
            "scanner": {"alive": True},
        }

    async def summary(self):
        self.summary_calls += 1
        if self.slow_summary:
            raise asyncio.TimeoutError("synthetic summary timeout")
        return {
            "ok": True,
            "auto_trade_gate": {"allowed": False, "stage": "shadow"},
            "auto_trade_recovery": {"active": False},
        }


async def _exercise_market_pipeline_telemetry_timeout() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "base"
    base = _TelemetryRuntime(slow_summary=False)
    arbitrum = _TelemetryRuntime(slow_summary=True)
    bundle._runtimes = {"base": base, "arbitrum": arbitrum}
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    class _JupiterSnapshot:
        def __init__(self):
            self.discover_calls = 0

        def snapshot(self):
            return {"status": "cached", "execution_authority": False}

        async def discover(self):
            self.discover_calls += 1
            raise AssertionError("telemetry reads must not perform live Jupiter discovery")

    jupiter = _JupiterSnapshot()
    bundle._solana_jupiter = jupiter

    payload = await bundle.market_pipeline_telemetry_readonly()

    assert payload["chains"]["base"]["scanner"]["alive"] is True
    assert payload["chains"]["arbitrum"]["scanner"]["alive"] is True
    assert payload["chains"]["arbitrum"]["admission"]["status"] == "not_sampled"
    assert payload["chains"]["arbitrum"]["admission"]["reason_code"] == "live_summary_skipped_for_read_latency"
    assert base.summary_calls == 0
    assert arbitrum.summary_calls == 0
    assert jupiter.discover_calls == 0
    assert payload["solana_jupiter_source"] == "last_completed_snapshot"


def test_multiruntime_market_pipeline_preserves_telemetry_without_live_summary() -> None:
    asyncio.run(_exercise_market_pipeline_telemetry_timeout())

async def _exercise_readonly_selection_uses_cached_jupiter_snapshot() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "base"
    bundle._runtimes = {"base": _TelemetryRuntime(slow_summary=False)}
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    class _JupiterSnapshot:
        def __init__(self):
            self.refresh_requests = 0
            self.discover_calls = 0

        def snapshot_or_schedule_refresh(self):
            self.refresh_requests += 1
            return {
                "status": "cached",
                "candidates": [],
                "execution_authority": False,
                "refresh": {
                    "source": "last_completed_snapshot",
                    "in_progress": True,
                    "execution_authority": False,
                },
            }

        async def discover(self):
            self.discover_calls += 1
            raise AssertionError("selection reads must not await live Jupiter discovery")

    jupiter = _JupiterSnapshot()
    bundle._solana_jupiter = jupiter
    payload = await bundle.select_best_opportunity_readonly()

    assert payload["ok"] is True
    assert payload["runtime_count"] == 1
    assert payload["global_discovery_candidates"] == []
    assert jupiter.refresh_requests == 1
    assert jupiter.discover_calls == 0


def test_multiruntime_selection_uses_cached_jupiter_snapshot() -> None:
    asyncio.run(_exercise_readonly_selection_uses_cached_jupiter_snapshot())



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
