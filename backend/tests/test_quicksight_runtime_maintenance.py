from __future__ import annotations

import asyncio
import builtins
from pathlib import Path

from victor_ai_bot.analytics.quicksight.config import QuickSightAnalyticsConfig
from victor_ai_bot.analytics.quicksight.runtime import QuickSightAnalyticsRuntime


class _BrokenPnlStore:
    async def summary(self, *, window: int):
        del window
        raise RuntimeError("summary_unavailable")

    async def income_breakdown(self, *, window: int):
        del window
        raise RuntimeError("income_unavailable")


def test_quicksight_runtime_tick_preserves_operator_safe_fallbacks():
    cfg = QuickSightAnalyticsConfig(enabled=True, tick_seconds=0.0, datasets=["TRADING_METRICS"])
    runtime = QuickSightAnalyticsRuntime(cfg, pnl_store=_BrokenPnlStore())

    asyncio.run(
        runtime.tick(
            state={
                "ts": 123,
                "pnl": {},
                "treasury": {},
                "governance": {},
                "behaveagent": {},
                "market": {},
                "circuit_breaker": {},
                "agent_perf": {},
            }
        )
    )

    state = runtime.state()
    assert state["income"] == {}
    assert state["datasets"]["TRADING_METRICS"] == 1
    assert state["export_status"]["ok"] is True


def test_quicksight_runtime_export_failures_are_visible(monkeypatch, tmp_path: Path):
    cfg = QuickSightAnalyticsConfig(
        enabled=True,
        tick_seconds=0.0,
        export_on_tick=True,
        export_dir=str(tmp_path / "analytics"),
        datasets=["TRADING_METRICS"],
    )
    runtime = QuickSightAnalyticsRuntime(cfg)

    real_open = builtins.open

    def flaky_open(path, *args, **kwargs):
        if str(path).endswith("dashboards.json"):
            raise OSError("blocked_write")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    asyncio.run(
        runtime.tick(
            state={
                "ts": 456,
                "pnl": {"win_rate": 0.6, "drawdown": 0.1},
                "treasury": {},
                "governance": {},
                "behaveagent": {},
                "market": {},
                "circuit_breaker": {},
                "agent_perf": {},
            }
        )
    )

    state = runtime.state()
    assert state["export_status"]["ok"] is False
    assert "blocked_write" in state["export_status"]["last_error"]
    assert any(str(row["path"]).endswith("dashboards.json") for row in state["export_status"]["writes"])
