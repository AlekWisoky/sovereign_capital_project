from __future__ import annotations

import asyncio

from victor_ai_bot.analytics.quicksight.config import QuickSightAnalyticsConfig
from victor_ai_bot.analytics.quicksight.datasets import build_trading_metrics_rows_with_status
from victor_ai_bot.analytics.quicksight.runtime import QuickSightAnalyticsRuntime


def test_build_trading_metrics_rows_with_status_degrades_malformed_inputs():
    rows, status = build_trading_metrics_rows_with_status(
        ts="bad-ts",
        pnl_summary={
            "recent": [{
                "realized_profit_after_gas_wei": "oops",
                "expected_profit_after_costs_wei": object(),
            }, "bad-item"],
            "win_rate": object(),
            "trades": "bad",
            "realized_pnl_wei": object(),
        },
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["timestamp"] == 0
    assert row["realized_pnl_wei"] == "0"
    assert row["trades"] == 0
    assert status["degraded"] is True
    assert status["metrics"]["degraded"] is True
    assert status["recent"]["degraded"] is True


def test_quicksight_runtime_exposes_dataset_status_for_malformed_inputs():
    cfg = QuickSightAnalyticsConfig(
        enabled=True,
        tick_seconds=0.0,
        datasets=["TRADING_METRICS", "TREASURY_METRICS", "GOVERNANCE_METRICS", "REGIME_CONTEXT"],
    )
    runtime = QuickSightAnalyticsRuntime(cfg)

    asyncio.run(
        runtime.tick(
            state={
                "ts": 123,
                "pnl": {"recent": ["bad"], "win_rate": 0.5, "trades": 2, "realized_pnl_wei": 0, "net_pnl_wei": 0},
                "treasury": {"inventory_balancer": {"targets": {"stable_reserves": 0.1}}, "aggressiveness": {"aggressiveness_level": "LOW", "borrow_mult_target_cap": 1.0}, "goal": {}, "liquidity_buffer_pct": object()},
                "governance": {"threat": {"score": 0.1}, "pdr_tail": "bad", "override_log": "bad"},
                "behaveagent": {"features": "bad", "confidence": object()},
                "market": {"volatility_proxy": object()},
                "circuit_breaker": {},
                "agent_perf": {},
            }
        )
    )

    state = runtime.state()
    ds = state["dataset_status"]
    assert ds["TRADING_METRICS"]["degraded"] is True
    assert ds["TREASURY_METRICS"]["degraded"] is True
    assert ds["GOVERNANCE_METRICS"]["degraded"] is True
    assert ds["REGIME_CONTEXT"]["degraded"] is True
    assert state["datasets"]["TRADING_METRICS"] == 1
