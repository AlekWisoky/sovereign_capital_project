from __future__ import annotations

import asyncio

from victor_ai_bot.analytics.quicksight.dashboards import build_dashboards_with_status
from victor_ai_bot.analytics.quicksight.config import QuickSightAnalyticsConfig
from victor_ai_bot.analytics.quicksight.runtime import QuickSightAnalyticsRuntime


def test_build_dashboards_with_status_degrades_malformed_inputs():
    dashboards, status = build_dashboards_with_status(
        ts="bad-ts",
        pnl={"realized_pnl_wei": object(), "net_pnl_wei": object(), "win_rate": object(), "trades": "bad"},
        treasury={
            "goal": {"target_return_pct": object()},
            "inventory_balancer": {"targets": "bad"},
            "aggressiveness": {"borrow_mult_target_cap": object()},
        },
        income="bad",
        market={"volatility_proxy": object(), "basefee_gwei": object(), "pending_rate": object()},
        governance={"threat": "bad", "pdr_tail": "bad", "override_log": "bad", "compliance_score": object()},
        circuit_breaker="bad",
        agent_perf={"agents": "bad", "global": "bad"},
    )

    assert dashboards["EXECUTIVE_OVERVIEW"]["kpis"]["trades"] == 0
    assert dashboards["RISK_CONTROL_PANEL"]["real_time"]["volatility"] == 0.0
    assert dashboards["AGENT_PERFORMANCE_VIEW"]["agents"] == []
    assert dashboards["GOVERNANCE_AUDIT_VIEW"]["pdr_timeline"] == []
    assert status["EXECUTIVE_OVERVIEW"]["degraded"] is True
    assert status["RISK_CONTROL_PANEL"]["degraded"] is True
    assert status["AGENT_PERFORMANCE_VIEW"]["degraded"] is True
    assert status["GOVERNANCE_AUDIT_VIEW"]["degraded"] is True


def test_quicksight_runtime_exposes_dashboard_status_for_malformed_inputs():
    cfg = QuickSightAnalyticsConfig(
        enabled=True,
        tick_seconds=0.0,
        datasets=["TRADING_METRICS"],
    )
    runtime = QuickSightAnalyticsRuntime(cfg)

    asyncio.run(
        runtime.tick(
            state={
                "ts": 123,
                "pnl": {"win_rate": object(), "trades": "bad", "realized_pnl_wei": 0, "net_pnl_wei": 0},
                "treasury": {
                    "goal": {"target_return_pct": object()},
                    "inventory_balancer": {"targets": "bad"},
                    "aggressiveness": {"aggressiveness_level": "LOW", "borrow_mult_target_cap": object()},
                },
                "governance": {"threat": "bad", "pdr_tail": "bad", "override_log": "bad", "compliance_score": object()},
                "behaveagent": {},
                "market": {"volatility_proxy": object(), "basefee_gwei": object(), "pending_rate": object()},
                "circuit_breaker": "bad",
                "agent_perf": {"agents": "bad", "global": "bad"},
            }
        )
    )

    state = runtime.state()
    ds = state["dashboard_status"]
    assert ds["EXECUTIVE_OVERVIEW"]["degraded"] is True
    assert ds["RISK_CONTROL_PANEL"]["degraded"] is True
    assert ds["AGENT_PERFORMANCE_VIEW"]["degraded"] is True
    assert ds["GOVERNANCE_AUDIT_VIEW"]["degraded"] is True
