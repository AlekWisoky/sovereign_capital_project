from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(base_borrow_amount="0", gas_mode="fast", send_mode="private", v1_focus="flashloan_atomic"),
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
        self._execution_service = SimpleNamespace(
            build_live_state=lambda runtime: {
                "items": [
                    {
                        "routeFamily": "flashloan_atomic|uni",
                        "family": "flash_arb",
                        "runtimeFamily": "flashloan_atomic",
                        "capitalFamily": "flashloan_atomic",
                        "displayFamily": "Flash Arbitrage",
                        "familyAliases": ["flash_arb", "flashloan_atomic"],
                        "lane": "PRIVATE",
                        "endpoint": "rpc-fast",
                        "flashloan": {"selectedProvider": "aave"},
                    }
                ]
            }
        )
        self._receipt_service = SimpleNamespace(
            summarize=lambda runtime: {
                "ok": True,
                "lastTxHash": "0xlife",
                "lastRouteFamily": "flashloan_atomic|uni",
                "lastFamily": "flash_arb",
                "lastRuntimeFamily": "flashloan_atomic",
                "lastCapitalFamily": "flashloan_atomic",
                "lastDisplayFamily": "Flash Arbitrage",
                "lastFamilyAliases": ["flash_arb", "flashloan_atomic"],
                "lastFamilyIdentity": {
                    "requestedFamily": "flashloan_atomic",
                    "launchFamily": "flash_arb",
                    "runtimeFamily": "flashloan_atomic",
                    "capitalFamily": "flashloan_atomic",
                    "displayName": "Flash Arbitrage",
                    "aliases": ["flash_arb", "flashloan_atomic"],
                    "isCore": True,
                },
                "lastProvider": "aave",
                "lastFlashloanFeeWei": 4500,
                "lastBorrowCostUsd": 1.1,
                "lastBorrowing": {"source": "flashloan", "provider": "aave", "flashloanFeeWei": 4500, "borrowCostUsd": 1.1},
                "lastLoanSettlement": {"ok": True, "loanId": "loan-1"},
                "lastTerminalProfitabilityAuthority": {"stage": "realized_settlement", "authoritative": True},
                "lastCapitalAdmission": {"ok": True, "stateContract": {"phase": "capital_admission"}},
                "lastLearningSync": {"executed": True, "ok": True, "reasonCode": "ok"},
                "lastMemorySync": {"executed": True, "ok": True, "reasonCode": "ok"},
                "lastClosedLoop": {"settlementAccounting": True, "learningRecorded": True, "memoryRecorded": True, "completed": True, "reasonCodes": [], "nextAction": "none"},
                "stateContract": {"phase": "settlement", "reason_code": "settled_success"},
            }
        )
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


def test_operator_summary_projects_receipt_closed_loop_and_confirms_v1_flashloan_lifecycle():
    summary = asyncio.run(OperatorSummaryService().build_snapshot(_Runtime()))

    assert summary["receiptSummary"]["lastClosedLoop"]["completed"] is True
    assert summary["receiptSummary"]["lastLearningSync"]["ok"] is True
    assert summary["receiptSummary"]["lastMemorySync"]["ok"] is True
    assert summary["flashloanArbLifecycle"]["focusFamily"] == "flash_arb"
    assert summary["flashloanArbLifecycle"]["runtimeFamily"] == "flashloan_atomic"
    assert summary["flashloanArbLifecycle"]["provider"] == "aave"
    assert summary["flashloanArbLifecycle"]["autoTradingReady"] is True
    assert summary["flashloanArbLifecycle"]["settlementRecorded"] is True
    assert summary["flashloanArbLifecycle"]["closedLoopCompleted"] is True
    assert summary["flashloanArbLifecycle"]["endToEndConfirmed"] is True
    assert summary["flashloanArbLifecycle"]["receiptSummaryState"]["phase"] == "settlement"
