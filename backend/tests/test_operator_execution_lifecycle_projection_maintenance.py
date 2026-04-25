from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService


class _Runtime:
    def __init__(self, *, execution_items, receipt_summary):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                base_borrow_amount="0", gas_mode="fast", send_mode="private", v1_focus="flashloan_atomic"
            ),
            chain=SimpleNamespace(v3_pairs=[{"amount_in": "150"}], curve_pools=[], balancer_pools=[]),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(
            exec_e2e_p50_ms=10, exec_e2e_p90_ms=20, exec_e2e_p99_ms=40,
            submit_to_receipt_p50_ms=30, submit_to_receipt_p90_ms=50, submit_to_receipt_p99_ms=90,
            loop_p50_ms=5, loop_p90_ms=10, loop_p99_ms=20, gas_mode="fast", send_mode="private",
        )
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=False, sandbox_only=False, defensive_mode=False, control_mode="auto", governance_enabled=True,
                mutation_enabled=False, evolution_frozen=True, allocations_frozen=False, metrics_enabled=True,
                latency_profiling_enabled=True, reward_trace_enabled=True, chaos_breakers_enabled=True,
                rpc_batch_enabled=False, rft_episode_export_enabled=False, kelly_enabled=True, auto_reinvest_enabled=False,
                force_send_mode="", force_gas_mode="", brain_mode="", aggression_mode="balanced", full_system_enabled=False,
            ),
            audit=SimpleNamespace(tail=lambda limit=250: []),
        )
        self._execution_service = SimpleNamespace(build_live_state=lambda runtime: {"items": list(execution_items)})
        self._receipt_service = SimpleNamespace(summarize=lambda runtime: dict(receipt_summary))
        self._telemetry_service = SimpleNamespace(service_health=lambda runtime: {"admission": {"ok": True}, "execution": {"ok": True}, "receipt": {"ok": True}, "telemetry": {"ok": True}})
        self._fund_service = SimpleNamespace(summary=lambda runtime: {"ok": True, "health": {"fundStage": "staging", "riskPosture": "balanced", "riskScore": 0.22}})
        self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {"ok": True, "services": {}})
        self._capital_explanation_service = SimpleNamespace(explain=lambda runtime, snapshot=None: {"ok": True, "text": "ok", "facts": {}, "causal": {}})
        self._endpoint_universe = SimpleNamespace(snapshot=lambda: {"private": {"candidates": [{"url": "rpc-fast"}]}})
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": [{"quality": 0.9}]})
        self._drawdown_state = SimpleNamespace(snapshot=lambda: {"drawdownPct": 1.0, "hardStop": {"active": False}})
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(snapshot=lambda: {"configured": True, "read": ["rpc-fast"]})
        self._capital_service = SimpleNamespace(summary=lambda runtime: {"ok": True, "navUsd": 10.0, "allocations": [], "flows": {}, "exposure": {}})
        self._pnl = SimpleNamespace(summary=self._pnl_summary)

    async def _pnl_summary(self, window=50):
        return {"realized_profit_after_gas_usd_micro": "1000000", "recent": []}

    async def snapshot(self):
        return {"metrics": {"auto_trading": True}, "chain": "ethereum", "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]}, "opportunities": []}

    def wealth_goal_state(self):
        return {"ok": True, "state": {"targetReturnPct": 8.0, "timeframeDays": 14, "riskTolerance": "moderate", "progressPct": 55.0, "goalAchieved": False, "nextGoalAllowed": True, "pacing": "steady", "aggressivenessCap": 0.9, "goalStatus": "active", "goalUrgency": "steady"}, "explanation": {"why_posture": "steady"}}

    def family_hardening_state(self):
        return {"ok": True, "items": []}

    def route_quality_state(self):
        return {"items": []}

    def endpoint_quality_state(self):
        return {"lanes": {}, "summary": {}, "generatedAtMs": 0}

    def execution_live_state(self):
        return self._execution_service.build_live_state(self)


def test_operator_summary_projects_non_core_execution_lifecycle_with_closed_loop_projection():
    runtime = _Runtime(
        execution_items=[{
            "txHash": "0xnoncore", "routeFamily": "cross_cex_dex|binance-uniswap", "family": "cex_dex_arb",
            "runtimeFamily": "cross_cex_dex", "capitalFamily": "cross_cex_dex", "displayFamily": "CEX-DEX Arbitrage",
            "familyAliases": ["cex_dex_arb", "cross_cex_dex"], "lane": "PRIVATE", "endpoint": "rpc-fast",
            "flashloan": {"selectedProvider": "balancer"},
        }],
        receipt_summary={
            "ok": True, "lastTxHash": "0xnoncore", "lastRouteFamily": "cross_cex_dex|binance-uniswap",
            "lastFamily": "cex_dex_arb", "lastRuntimeFamily": "cross_cex_dex", "lastCapitalFamily": "cross_cex_dex",
            "lastDisplayFamily": "CEX-DEX Arbitrage", "lastFamilyAliases": ["cex_dex_arb", "cross_cex_dex"],
            "lastFamilyIdentity": {"requestedFamily": "cross_cex_dex", "launchFamily": "cex_dex_arb", "runtimeFamily": "cross_cex_dex", "capitalFamily": "cross_cex_dex", "displayName": "CEX-DEX Arbitrage", "aliases": ["cex_dex_arb", "cross_cex_dex"], "isCore": False},
            "lastProvider": "balancer", "lastFlashloanFeeWei": 6200, "lastBorrowCostUsd": 1.5,
            "lastBorrowing": {"source": "flashloan", "provider": "balancer", "flashloanFeeWei": 6200, "borrowCostUsd": 1.5},
            "lastLoanSettlement": {"ok": True, "loanId": "loan-noncore"},
            "lastTerminalProfitabilityAuthority": {"stage": "realized_settlement", "authoritative": True},
            "lastCapitalAdmission": {"ok": True},
            "lastLearningSync": {"executed": True, "ok": True, "reasonCode": "ok"},
            "lastMemorySync": {"executed": True, "ok": True, "reasonCode": "ok"},
            "lastClosedLoop": {"settlementAccounting": True, "learningRecorded": True, "memoryRecorded": True, "completed": True, "reasonCodes": [], "nextAction": "none"},
            "stateContract": {"phase": "settlement", "reason_code": "settled_success"},
        },
    )
    summary = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    lifecycles = list(summary["executionLifecycles"])
    noncore = next(item for item in lifecycles if item["family"] == "cex_dex_arb")
    assert noncore["runtimeFamily"] == "cross_cex_dex"
    assert noncore["capitalFamily"] == "cross_cex_dex"
    assert noncore["displayFamily"] == "CEX-DEX Arbitrage"
    assert noncore["provider"] == "balancer"
    assert noncore["pendingActive"] is True
    assert noncore["autoTradingReady"] is True
    assert noncore["settlementRecorded"] is True
    assert noncore["closedLoopCompleted"] is True
    assert noncore["endToEndConfirmed"] is True
    assert noncore["phase"] == "settlement"
    assert noncore["v1FocusAligned"] is False


def test_operator_summary_does_not_mark_receipt_only_non_core_family_as_trade_ready_when_not_focus_aligned():
    runtime = _Runtime(
        execution_items=[],
        receipt_summary={
            "ok": True, "lastTxHash": "0xhistorical", "lastRouteFamily": "cross_cex_dex|coinbase-uniswap",
            "lastFamily": "cex_dex_arb", "lastRuntimeFamily": "cross_cex_dex", "lastCapitalFamily": "cross_cex_dex",
            "lastDisplayFamily": "CEX-DEX Arbitrage", "lastFamilyAliases": ["cex_dex_arb", "cross_cex_dex"],
            "lastFamilyIdentity": {"requestedFamily": "cross_cex_dex", "launchFamily": "cex_dex_arb", "runtimeFamily": "cross_cex_dex", "capitalFamily": "cross_cex_dex", "displayName": "CEX-DEX Arbitrage", "aliases": ["cex_dex_arb", "cross_cex_dex"], "isCore": False},
            "lastProvider": "balancer", "lastFlashloanFeeWei": 5100, "lastBorrowCostUsd": 0.9,
            "lastBorrowing": {"source": "flashloan", "provider": "balancer", "flashloanFeeWei": 5100, "borrowCostUsd": 0.9},
            "lastLoanSettlement": {"ok": True},
            "lastTerminalProfitabilityAuthority": {"stage": "realized_settlement", "authoritative": True},
            "lastCapitalAdmission": {"ok": True},
            "lastLearningSync": {"executed": True, "ok": True, "reasonCode": "ok"},
            "lastMemorySync": {"executed": True, "ok": True, "reasonCode": "ok"},
            "lastClosedLoop": {"settlementAccounting": True, "learningRecorded": True, "memoryRecorded": True, "completed": True, "reasonCodes": [], "nextAction": "none"},
            "stateContract": {"phase": "settlement", "reason_code": "settled_success"},
        },
    )
    summary = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    lifecycles = list(summary["executionLifecycles"])
    noncore = next(item for item in lifecycles if item["family"] == "cex_dex_arb")
    assert noncore["pendingActive"] is False
    assert noncore["autoTradingReady"] is False
    assert noncore["closedLoopCompleted"] is True
    assert noncore["endToEndConfirmed"] is True
    assert noncore["phase"] == "settlement"
