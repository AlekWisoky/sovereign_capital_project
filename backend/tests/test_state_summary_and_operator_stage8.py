from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService
from victor_ai_bot.runtime_services.state_service import StateService
from victor_ai_bot.runtime_services.runtime_context import build_execution_runtime_signals
from victor_ai_bot.persistence.db import PersistenceDB


class _Runtime:
    def family_hardening_state(self):
        return {
            "ok": True,
            "items": [
                {
                    "family": "funding_arb",
                    "controls": {"no_trade": True, "no_trade_reason_codes": ["family_cap_zero"]},
                }
            ],
        }

    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(base_borrow_amount="0", gas_mode="fast", send_mode="private"),
            chain=SimpleNamespace(
                v3_pairs=[{"amount_in": "150"}], curve_pools=[], balancer_pools=[]
            ),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(
            exec_e2e_p50_ms=10,
            exec_e2e_p90_ms=20,
            exec_e2e_p99_ms=40,
            submit_to_receipt_p50_ms=30,
            submit_to_receipt_p90_ms=50,
            submit_to_receipt_p99_ms=90,
            loop_p50_ms=5,
            loop_p90_ms=10,
            loop_p99_ms=20,
            gas_mode="fast",
            send_mode="private",
        )
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=False,
                sandbox_only=False,
                defensive_mode=False,
                control_mode="auto",
                governance_enabled=True,
                mutation_enabled=False,
                evolution_frozen=True,
                allocations_frozen=False,
                metrics_enabled=True,
                latency_profiling_enabled=True,
                reward_trace_enabled=True,
                chaos_breakers_enabled=True,
                rpc_batch_enabled=False,
                rft_episode_export_enabled=False,
                kelly_enabled=True,
                auto_reinvest_enabled=False,
                force_send_mode="",
                force_gas_mode="",
                brain_mode="",
                aggression_mode="balanced",
                full_system_enabled=False,
            ),
            audit=SimpleNamespace(tail=lambda limit=250: []),
        )
        self._execution_service = SimpleNamespace(
            build_live_state=lambda runtime: {
                "items": [
                    {
                        "endpoint": "rpc-fast",
                        "lane": "PRIVATE",
                        "flashloan": {"selectedProvider": "aave"},
                    }
                ]
            }
        )
        self._telemetry_service = SimpleNamespace(
            service_health=lambda runtime: {
                "admission": {"ok": True},
                "execution": {"ok": True},
                "receipt": {"ok": True},
                "telemetry": {"ok": True},
            }
        )
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {"fundStage": "staging", "riskPosture": "balanced", "riskScore": 0.22},
            }
        )
        self._analytics_service = SimpleNamespace(
            system_summary=lambda runtime: {"ok": True, "services": {}}
        )
        self._capital_explanation_service = SimpleNamespace(
            explain=lambda runtime, snapshot=None: {
                "ok": True,
                "text": "ok",
                "facts": {},
                "causal": {},
            }
        )
        self._endpoint_universe = SimpleNamespace(
            snapshot=lambda: {"private": {"candidates": [{"url": "rpc-fast"}]}}
        )
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": [{"quality": 0.9}]})
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {"drawdownPct": 1.0, "hardStop": {"active": False}}
        )
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(
            snapshot=lambda: {"configured": True, "read": ["rpc-fast"]}
        )
        self._agent_attribution = SimpleNamespace(summary=lambda: {"agents": []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {"items": []})
        self._pending = {}
        self._auto_trading = True
        self._pnl = SimpleNamespace(summary=self._pnl_summary)

    async def _pnl_summary(self, window=50):
        return {"realized_profit_after_gas_usd_micro": "1000000", "recent": []}

    async def snapshot(self):
        return {
            "metrics": {"auto_trading": True},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [],
        }

    def wealth_goal_state(self):
        return {
            "ok": True,
            "state": {
                "targetReturnPct": 8.0,
                "timeframeDays": 14,
                "riskTolerance": "moderate",
                "progressPct": 55.0,
                "goalAchieved": False,
                "nextGoalAllowed": True,
                "pacing": "steady",
                "aggressivenessCap": 0.9,
                "goalStatus": "active",
                "goalUrgency": "steady",
            },
            "explanation": {"why_posture": "steady"},
        }


def test_execution_runtime_signals_extracts_stable_inputs():
    rt = _Runtime()
    sig = build_execution_runtime_signals(rt)
    assert sig.base_borrow_amount == 0
    assert sig.route_amount_candidates == [150]
    assert sig.gas_mode == "fast"
    assert sig.send_mode == "private"


def test_state_summary_service_returns_canonical_snapshots():
    rt = _Runtime()
    svc = StateSummaryService()
    assert svc.execution_live(rt)["items"][0]["endpoint"] == "rpc-fast"
    assert svc.fund_summary(rt)["ok"] is True
    assert svc.service_health(rt)["execution"]["ok"] is True


async def _build_snapshot():
    rt = _Runtime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "active"
    assert out["wealthGoal"]["goalStatus"] == "active"
    assert out["services"]["execution"]["ok"] is True
    assert out["familyHardening"]["ok"] is True
    assert out["familyHardening"]["items"][0]["family"] == "funding_arb"
    assert out["familyHardening"]["items"][0]["controls"]["no_trade_reason_codes"] == [
        "family_cap_zero"
    ]
    assert out["execution"]["endpointUniverse"]["private"]["candidates"][0]["url"] == "rpc-fast"


def test_operator_summary_snapshot_asyncio():
    import asyncio

    asyncio.run(_build_snapshot())


class _DegradedOperatorRuntime(_Runtime):
    def endpoint_quality_state(self):
        raise RuntimeError("endpoint quality offline")

    def family_hardening_state(self):
        raise ValueError("family hardening malformed")


async def _build_snapshot_degraded_components():
    rt = _DegradedOperatorRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["execution"]["endpointQuality"] == {"lanes": {}, "summary": {}, "generatedAtMs": 0}
    assert out["familyHardening"]["status"] == "unavailable"
    assert out["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert out["familyHardening"]["items"] == []
    assert out["familyHardeningReasonCodes"] == ["family_hardening_service_unavailable"]
    assert out["holdReasonCode"] == "family_hardening_service_unavailable"
    assert out["holdReasonCodes"] == ["family_hardening_service_unavailable"]
    assert out["recoveryStatus"] == "family_hardening_restore_required"
    assert out["recoveryReasonCode"] == "family_hardening_service_unavailable"
    assert out["recoveryReasonCodes"] == ["family_hardening_service_unavailable"]
    assert out["recoveryReliabilityClass"] == "unavailable"
    assert out["recoveryReliabilityReasonCode"] == "recovery_reliability_unavailable"
    assert out["executionAdvisoryActive"] is True
    assert out["executionAdvisorySeverity"] == "warning"
    assert out["executionAdvisoryClass"] == "unavailable"
    assert out["executionAdvisoryReasonCode"] == "recovery_reliability_unavailable"
    assert out["executionAdvisoryNextAction"] == "restore_family_hardening"
    assert "restore family hardening" in out["pausedReason"].lower()


def test_operator_summary_snapshot_degrades_endpoint_quality_and_family_hardening_failures():
    import asyncio

    asyncio.run(_build_snapshot_degraded_components())


class _FamilyHardeningHoldRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                    "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                    "holdReasonCode": "family_hardening_service_unavailable",
                    "holdReasonCodes": ["family_hardening_service_unavailable"],
                    "suggestedNextAction": "restore_family_hardening",
                    "recoveryStatus": "family_hardening_restore_required",
                    "recoveryReasonCode": "family_hardening_service_unavailable",
                    "recoveryReasonCodes": ["family_hardening_service_unavailable"],
                    "recoveryNextAction": "restore_family_hardening",
                },
            }
        )


async def _build_snapshot_family_hardening_hold():
    rt = _FamilyHardeningHoldRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["familyHardeningReasonCodes"] == ["family_hardening_service_unavailable"]
    assert out["holdReasonCode"] == "family_hardening_service_unavailable"
    assert out["recoveryStatus"] == "family_hardening_restore_required"
    assert out["recoveryReasonCode"] == "family_hardening_service_unavailable"
    assert "restore family hardening" in out["pausedReason"].lower()


def test_operator_summary_snapshot_elevates_family_hardening_hold_to_defensive_posture():
    import asyncio

    asyncio.run(_build_snapshot_family_hardening_hold())


class _SnapshotFailureRuntime(_Runtime):
    async def snapshot(self):
        raise RuntimeError("snapshot offline")

    def capital_explain(self, snapshot=None):
        snap = snapshot or {}
        return {
            "ok": True,
            "text": "capital_explanation_unavailable_base_ok",
            "facts": {"hasMetrics": bool((snap or {}).get("metrics"))},
            "causal": {},
        }


async def _build_snapshot_snapshot_failure():
    rt = _SnapshotFailureRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["observability"]["rpcErrRate"] == 0.0
    assert out["observability"]["oppsSeen"] == 0
    assert out["decisions"] == []
    assert out["services"]["execution"]["ok"] is True


def test_operator_summary_snapshot_degrades_runtime_snapshot_failure():
    import asyncio

    asyncio.run(_build_snapshot_snapshot_failure())


class _MissingExecutionCfgRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(
                v3_pairs=[{"amount_in": "150"}], curve_pools=[], balancer_pools=[]
            ),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        del self._auto_trading

    async def snapshot(self):
        return {
            "metrics": {},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [],
        }


async def _build_snapshot_missing_execution_cfg():
    rt = _MissingExecutionCfgRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["controlMode"] == "auto"
    assert out["portfolio"]["state"] == "active"
    assert out["pausedReason"] == ""


def test_operator_summary_snapshot_handles_missing_execution_cfg():
    import asyncio

    asyncio.run(_build_snapshot_missing_execution_cfg())


async def _explain_snapshot_failure():
    rt = _SnapshotFailureRuntime()
    svc = OperatorSummaryService()
    out = await svc.explain(rt)
    assert out["ok"] is True
    assert out["text"] == "capital_explanation_unavailable_base_ok"
    assert out["facts"]["hasMetrics"] is False


def test_operator_summary_explain_degrades_runtime_snapshot_failure():
    import asyncio

    asyncio.run(_explain_snapshot_failure())


class _OperatorHelperFailureRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._cc = SimpleNamespace(
            controls=self._cc.controls,
            audit=SimpleNamespace(
                tail=lambda limit=250: (_ for _ in ()).throw(RuntimeError("audit offline"))
            ),
            state=lambda: (_ for _ in ()).throw(RuntimeError("cc state offline")),
            explain=lambda base: (_ for _ in ()).throw(RuntimeError("cc explain offline")),
        )
        self._anomaly = SimpleNamespace(
            snapshot=lambda: (_ for _ in ()).throw(RuntimeError("anomaly offline"))
        )
        self._pnl = SimpleNamespace(summary=self._broken_pnl_summary)

    async def _broken_pnl_summary(self, window=50):
        raise RuntimeError("pnl offline")

    def wealth_goal_state(self):
        raise RuntimeError("wealth goal offline")

    def meta_state(self):
        raise RuntimeError("meta offline")

    def execution_capture_analytics(self):
        raise RuntimeError("capture analytics offline")

    def capital_explain(self, snapshot=None):
        raise RuntimeError("capital explain offline")


async def _build_snapshot_helper_failures():
    rt = _OperatorHelperFailureRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["navUsd"] == 0.0
    assert out["wealthGoal"] is None
    assert out["wealthGoalDetails"] is None
    assert out["governance"]["storage"] == {}
    assert out["governanceHistory"] == []
    assert out["decisions"] == []
    assert out["sandbox"]["proposals"] == []
    assert out["analytics"]["laneSuccess"] == []
    assert out["analytics"]["venueQuality"] == []
    assert out["risk"]["breakers"]["gasAnomalyBreaker"] is False


def test_operator_summary_snapshot_degrades_helper_runtime_failures():
    import asyncio

    asyncio.run(_build_snapshot_helper_failures())


async def _explain_helper_failures():
    rt = _OperatorHelperFailureRuntime()
    svc = OperatorSummaryService()
    out = await svc.explain(rt)
    assert out["ok"] is False
    assert out["text"] == "explain_failed"
    assert out["facts"] == {}
    assert out["causal"] == {}


def test_operator_summary_explain_degrades_helper_runtime_failures():
    import asyncio

    asyncio.run(_explain_helper_failures())


class _AfterCostOpportunityRuntime(_Runtime):
    async def snapshot(self):
        return {
            "metrics": {"auto_trading": True},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [
                {
                    "id": "gross-only",
                    "expected_profit_raw": "9000",
                    "meta": {},
                },
                {
                    "id": "after-cost-positive",
                    "expected_profit_raw": "1",
                    "can_execute": True,
                    "meta": {"profit_after_costs": "500", "safety": {"exec_ready": True}},
                },
                {
                    "id": "after-cost-nonpositive",
                    "expected_profit_raw": "9999",
                    "meta": {"profit_after_costs": "0"},
                },
                {
                    "id": "after-cost-invalid",
                    "expected_profit_raw": "9999",
                    "meta": {"profit_after_costs": "oops"},
                },
                {
                    "id": "after-cost-from-safety",
                    "expected_profit_raw": "1",
                    "can_execute": True,
                    "meta": {
                        "safety": {
                            "profit_after_costs_wei": "700",
                            "exec_ready": False,
                            "reason": "signing_not_ready",
                        }
                    },
                },
            ],
        }


async def _build_snapshot_after_cost_executable_count():
    rt = _AfterCostOpportunityRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["observability"]["oppsSeen"] == 5
    assert out["observability"]["oppsAfterCostPositive"] == 2
    assert out["observability"]["oppsExecutable"] == 1


def test_operator_summary_snapshot_counts_only_after_cost_profitable_opportunities_as_executable():
    import asyncio

    asyncio.run(_build_snapshot_after_cost_executable_count())


class _AfterCostMismatchRuntime(_AfterCostOpportunityRuntime):
    async def snapshot(self):
        snap = await super().snapshot()
        snap["opportunities"].insert(
            1,
            {
                "id": "after-cost-mismatched",
                "expected_profit_raw": "99999",
                "can_execute": True,
                "meta": {
                    "profit_after_costs": "900",
                    "safety": {"profit_after_costs_wei": "100", "exec_ready": True},
                },
            },
        )
        return snap


async def _build_snapshot_after_cost_mismatch_excluded_from_verified_counts():
    rt = _AfterCostMismatchRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["observability"]["oppsSeen"] == 6
    assert out["observability"]["oppsAfterCostPositive"] == 2
    assert out["observability"]["oppsExecutable"] == 1


def test_operator_summary_snapshot_excludes_mismatched_after_fee_truth_from_verified_counts():
    import asyncio

    asyncio.run(_build_snapshot_after_cost_mismatch_excluded_from_verified_counts())


class _AfterCostRouteInvalidRuntime(_AfterCostOpportunityRuntime):
    async def snapshot(self):
        snap = await super().snapshot()
        snap["opportunities"][1]["meta"]["execution_route_plan"] = {
            "executable": False,
            "route_invalid_causes": ["route_plan_not_executable"],
        }
        snap["opportunities"][1]["meta"]["route_invalid_causes"] = ["route_plan_not_executable"]
        return snap


async def _build_snapshot_after_cost_route_invalid_excluded_from_executable_counts():
    rt = _AfterCostRouteInvalidRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["observability"]["oppsAfterCostPositive"] == 2
    assert out["observability"]["oppsExecutable"] == 0


def test_operator_summary_snapshot_excludes_route_invalid_after_fee_positive_opportunities_from_executable_counts():
    import asyncio

    asyncio.run(_build_snapshot_after_cost_route_invalid_excluded_from_executable_counts())


class _AfterCostRouteRuntimeDegradedRuntime(_AfterCostOpportunityRuntime):
    async def snapshot(self):
        snap = await super().snapshot()
        snap["opportunities"][1]["meta"]["execution_route_runtime"] = {
            "degraded": True,
            "reason_codes": ["execution_route_input_unavailable"],
            "input": {"ok": False, "code": "execution_route_input_unavailable"},
        }
        return snap


async def _build_snapshot_after_cost_route_runtime_degraded_excluded_from_executable_counts():
    rt = _AfterCostRouteRuntimeDegradedRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["observability"]["oppsAfterCostPositive"] == 2
    assert out["observability"]["oppsExecutable"] == 0


def test_operator_summary_snapshot_excludes_route_runtime_degraded_after_fee_positive_opportunities_from_executable_counts():
    import asyncio

    asyncio.run(_build_snapshot_after_cost_route_runtime_degraded_excluded_from_executable_counts())


class _GlobalBlockerOpportunityRuntime(_AfterCostOpportunityRuntime):
    def __init__(self, *, hard_stop: bool = False, kill_switch: bool = False):
        super().__init__()
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {
                "drawdownPct": 9.0 if hard_stop else 1.0,
                "hardStop": {
                    "active": hard_stop,
                    "reason_codes": ["drawdown_hard_stop"] if hard_stop else [],
                },
            }
        )
        self._kill_switch = SimpleNamespace(
            snapshot=lambda: {
                "metrics": {},
                "suppressions": ({"execution": {"reason": "manual_block"}} if kill_switch else {}),
                "history": [],
            }
        )


async def _build_snapshot_hard_stop_blocks_operator_executable_truth():
    rt = _GlobalBlockerOpportunityRuntime(hard_stop=True)
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "paused"
    assert out["executionGate"]["blocked"] is True
    assert out["executionGate"]["reason_code"] == "drawdown_hard_stop"
    assert out["observability"]["oppsAfterCostPositive"] == 2
    assert out["observability"]["oppsExecutable"] == 0
    assert "drawdown hard stop is active" in out["pausedReason"]


def test_operator_summary_snapshot_surfaces_drawdown_hard_stop_as_global_execution_blocker():
    import asyncio

    asyncio.run(_build_snapshot_hard_stop_blocks_operator_executable_truth())


async def _build_snapshot_kill_switch_blocks_operator_executable_truth():
    rt = _GlobalBlockerOpportunityRuntime(kill_switch=True)
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "paused"
    assert out["executionGate"]["blocked"] is True
    assert out["executionGate"]["reason_code"] == "kill_switch_active"
    assert out["observability"]["oppsExecutable"] == 0
    assert "kill switch suppressions are active" in out["pausedReason"]


def test_operator_summary_snapshot_surfaces_kill_switch_as_global_execution_blocker():
    import asyncio

    asyncio.run(_build_snapshot_kill_switch_blocks_operator_executable_truth())


class _FundHoldRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                    "holdReasonCode": "capital_truth_degraded",
                    "holdReasonCodes": ["capital_truth_degraded"],
                    "capitalTruthReasonCodes": ["capital_truth_degraded"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


async def _build_snapshot_fund_hold_reason_sync():
    rt = _FundHoldRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["holdReasonCode"] == "capital_truth_degraded"
    assert out["holdReasonCodes"] == ["capital_truth_degraded"]
    assert out["capitalTruthReasonCodes"] == ["capital_truth_degraded"]
    assert out["suggestedNextAction"] == "restore_capital_truth"
    assert out["observability"]["oppsExecutable"] == 0
    assert "System posture is defensive because capital truth degraded." in out["pausedReason"]
    assert "restore capital truth" in out["pausedReason"]


def test_operator_summary_snapshot_syncs_fund_hold_reason_codes_into_command_center_status():
    import asyncio

    asyncio.run(_build_snapshot_fund_hold_reason_sync())


class _InternalPrimeHoldRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                    "holdReasonCode": "internal_prime_journal_borrowed_mismatch",
                    "holdReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                    "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                    "suggestedNextAction": "repair_internal_prime_accounting",
                },
            }
        )


async def _build_snapshot_internal_prime_hold_sync():
    rt = _InternalPrimeHoldRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["holdReasonCode"] == "internal_prime_journal_borrowed_mismatch"
    assert out["internalPrimeReasonCodes"] == ["internal_prime_journal_borrowed_mismatch"]
    assert out["suggestedNextAction"] == "repair_internal_prime_accounting"
    assert out["recoveryReady"] is False
    assert out["recoveryStatus"] == "internal_prime_reconciliation_required"
    assert out["recoveryReasonCode"] == "internal_prime_journal_borrowed_mismatch"
    assert out["recoveryReasonCodes"] == ["internal_prime_journal_borrowed_mismatch"]
    assert out["recoveryNextAction"] == "repair_internal_prime_accounting"
    assert out["observability"]["oppsExecutable"] == 0
    assert (
        "System posture is defensive because internal prime journal borrowed mismatch."
        in out["pausedReason"]
    )
    assert "repair internal prime accounting" in out["pausedReason"]


def test_operator_summary_snapshot_elevates_internal_prime_hold_to_defensive_posture():
    import asyncio

    asyncio.run(_build_snapshot_internal_prime_hold_sync())


class _FundUnavailableCapitalTruthRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                    "holdReasonCode": "capital_truth_unavailable",
                    "holdReasonCodes": ["capital_truth_unavailable"],
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


async def _build_snapshot_capital_truth_unavailable_sync():
    rt = _FundUnavailableCapitalTruthRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["holdReasonCode"] == "capital_truth_unavailable"
    assert out["holdReasonCodes"] == ["capital_truth_unavailable"]
    assert out["capitalTruthReasonCodes"] == ["capital_truth_unavailable"]
    assert out["suggestedNextAction"] == "restore_capital_truth"
    assert out["recoveryReady"] is False
    assert out["recoveryStatus"] == "capital_truth_restore_required"
    assert out["recoveryReasonCode"] == "capital_truth_unavailable"
    assert out["recoveryReasonCodes"] == ["capital_truth_unavailable"]
    assert out["recoveryNextAction"] == "restore_capital_truth"
    assert out["observability"]["oppsExecutable"] == 0
    assert "System posture is defensive because capital truth unavailable." in out["pausedReason"]
    assert "restore capital truth" in out["pausedReason"]


def test_operator_summary_snapshot_elevates_capital_truth_unavailable_to_defensive_posture():
    import asyncio

    asyncio.run(_build_snapshot_capital_truth_unavailable_sync())


class _RecoveryFreshnessRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "defensive",
                    "riskScore": 0.22,
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "holdReasonCode": "capital_truth_unavailable",
                    "holdReasonCodes": ["capital_truth_unavailable"],
                    "suggestedNextAction": "restore_capital_truth",
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_unavailable",
                    "recoveryReasonCodes": ["capital_truth_unavailable"],
                    "recoveryNextAction": "restore_capital_truth",
                    "recoveryFreshnessClass": "unavailable",
                    "recoveryFreshnessReasonCode": "capital_truth_freshness_unavailable",
                    "recoveryFreshnessReasonCodes": ["capital_truth_freshness_unavailable"],
                    "recoveryFreshnessNextAction": "refresh_capital_truth_snapshot",
                    "capitalTruthFreshnessClass": "unavailable",
                    "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_unavailable"],
                },
            }
        )


async def _build_snapshot_recovery_freshness():
    rt = _RecoveryFreshnessRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["recoveryFreshnessClass"] == "unavailable"
    assert out["recoveryFreshnessReasonCode"] == "capital_truth_freshness_unavailable"
    assert out["recoveryFreshnessReasonCodes"] == ["capital_truth_freshness_unavailable"]
    assert out["recoveryFreshnessNextAction"] == "refresh_capital_truth_snapshot"
    assert out["capitalTruthFreshnessClass"] == "unavailable"
    assert out["capitalTruthFreshnessReasonCodes"] == ["capital_truth_freshness_unavailable"]


def test_operator_summary_snapshot_surfaces_recovery_freshness_canon():
    import asyncio

    asyncio.run(_build_snapshot_recovery_freshness())


class _RecoveryHistoryRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "pilot_capital",
                    "riskPosture": "defensive",
                    "riskScore": 0.42,
                    "recoveryReady": True,
                    "recoveryStatus": "ready",
                    "recoveryReasonCode": "ok",
                    "recoveryReasonCodes": [],
                    "recoveryHistoryComponent": "capital_truth",
                    "recoveryHistoryStatus": "recovered",
                    "recoveryRecoveredAtTsMs": 1700000060000,
                    "capitalTruthRecoveryHistoryStatus": "recovered",
                    "capitalTruthRecoveredAtTsMs": 1700000060000,
                },
            }
        )


def test_operator_summary_surfaces_capital_truth_recovery_history_when_fund_health_tracks_recent_recovery():
    import asyncio

    payload = asyncio.run(OperatorSummaryService().build_snapshot(_RecoveryHistoryRuntime()))
    assert payload["recoveryHistoryComponent"] == "capital_truth"
    assert payload["recoveryHistoryStatus"] == "recovered"
    assert payload["recoveryRecoveredAtTsMs"] == 1700000060000


class _RecoveryHistorySeverityRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "pilot_capital",
                    "riskPosture": "defensive",
                    "riskScore": 0.42,
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_unavailable",
                    "recoveryReasonCodes": ["capital_truth_unavailable"],
                    "recoveryHistoryComponent": "capital_truth",
                    "recoveryHistoryStatus": "degraded",
                    "recoveryDegradedCount": 3,
                    "recoveryLastHealthyTsMs": 1700000000000,
                    "recoveryDegradationSeverityClass": "persistent",
                },
            }
        )


def test_operator_summary_surfaces_recovery_history_count_and_severity_when_fund_health_tracks_persistent_capital_degradation():
    import asyncio

    payload = asyncio.run(
        OperatorSummaryService().build_snapshot(_RecoveryHistorySeverityRuntime())
    )
    assert payload["recoveryDegradedCount"] == 3
    assert payload["recoveryLastHealthyTsMs"] == 1700000000000
    assert payload["recoveryDegradationSeverityClass"] == "persistent"


def test_operator_summary_surfaces_recovery_reliability_for_capital_truth_unavailable():
    import asyncio

    class Runtime(_Runtime):
        def __init__(self):
            super().__init__()
            self._fund_service = SimpleNamespace(
                summary=lambda runtime: {
                    "ok": True,
                    "health": {
                        "fundStage": "pilot_capital",
                        "riskPosture": "defensive",
                        "riskScore": 0.42,
                        "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                        "holdReasonCode": "capital_truth_unavailable",
                        "holdReasonCodes": ["capital_truth_unavailable"],
                        "recoveryStatus": "capital_truth_restore_required",
                        "recoveryReasonCode": "capital_truth_unavailable",
                        "recoveryReasonCodes": ["capital_truth_unavailable"],
                        "capitalTruthReliabilityClass": "unavailable",
                        "capitalTruthReliabilityReasonCode": "capital_truth_reliability_unavailable",
                        "capitalTruthReliabilityReasonCodes": [
                            "capital_truth_reliability_unavailable",
                            "capital_truth_freshness_unavailable",
                        ],
                        "recoveryReliabilityClass": "unavailable",
                        "recoveryReliabilityReasonCode": "recovery_reliability_unavailable",
                        "recoveryReliabilityReasonCodes": [
                            "recovery_reliability_unavailable",
                            "capital_truth_reliability_unavailable",
                        ],
                        "recoveryReliabilityNextAction": "restore_capital_truth",
                    },
                }
            )

    payload = asyncio.run(OperatorSummaryService().build_snapshot(Runtime()))
    assert payload["recoveryReliabilityClass"] == "unavailable"
    assert payload["recoveryReliabilityReasonCode"] == "recovery_reliability_unavailable"
    assert payload["recoveryReliabilityNextAction"] == "restore_capital_truth"


def test_operator_summary_downgrades_active_posture_to_defensive_when_recovery_reliability_is_fragile_without_hard_hold():
    import asyncio

    class Runtime(_Runtime):
        def __init__(self):
            super().__init__()
            self._fund_service = SimpleNamespace(
                summary=lambda runtime: {
                    "ok": True,
                    "health": {
                        "fundStage": "pilot_capital",
                        "riskPosture": "balanced",
                        "riskScore": 0.22,
                        "recoveryReliabilityClass": "fragile",
                        "recoveryReliabilityReasonCode": "recovery_reliability_fragile",
                        "recoveryReliabilityReasonCodes": [
                            "recovery_reliability_fragile",
                            "recovery_recovered_fragile",
                        ],
                        "recoveryReliabilityNextAction": "repair_internal_prime_accounting",
                    },
                }
            )

    payload = asyncio.run(OperatorSummaryService().build_snapshot(Runtime()))
    assert payload["portfolio"]["state"] == "defensive"
    assert payload["executionAdvisoryActive"] is True
    assert payload["executionAdvisorySeverity"] == "warning"
    assert payload["executionAdvisoryClass"] == "fragile"
    assert payload["executionAdvisoryReasonCode"] == "recovery_reliability_fragile"
    assert payload["executionAdvisoryNextAction"] == "repair_internal_prime_accounting"


def _operator_execution_route_plan_ready() -> dict[str, object]:
    return {
        "selected_venues": ["uni", "curve"],
        "split": [
            {"venue": "uni", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
            {"venue": "curve", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
        ],
        "fallback_tree": [],
        "fallback_used": False,
        "executable": True,
        "require_fallback_tree": False,
        "provider_priority": [],
        "provider_fallback": "",
        "reserve_distortion": 0.0,
        "mutation_factor": 1.0,
        "route_invalid_causes": [],
        "runtime": {
            "input": {"ok": True, "code": "ok", "detail": ""},
            "legs": {"ok": True, "code": "ok", "detail": ""},
            "mutation": {"ok": True, "code": "ok", "detail": ""},
            "profit": {"ok": True, "code": "ok", "detail": ""},
            "degraded": False,
        },
        "leg_plan": [
            {
                "index": 0,
                "venue": "uni",
                "share": 0.5,
                "venue_quality": 0.9,
                "viability": 1.0,
                "selected": True,
                "distortion": 0.0,
                "action": "execute",
                "fallback_venues": [],
            },
            {
                "index": 1,
                "venue": "curve",
                "share": 0.5,
                "venue_quality": 0.9,
                "viability": 1.0,
                "selected": True,
                "distortion": 0.0,
                "action": "execute",
                "fallback_venues": [],
            },
        ],
        "raw_route_plan": {},
    }


class _OperatorTreasuryGateRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        from victor_ai_bot.runtime_services.execution_service import ExecutionService

        self._execution_service = ExecutionService()
        self._opps = [
            SimpleNamespace(
                id="op-1",
                strategy="funding_arb",
                expected_profit_raw="1000",
                can_execute=True,
                route_id="r-op",
                route=SimpleNamespace(
                    legs=[
                        SimpleNamespace(venue="uni", min_out="100"),
                        SimpleNamespace(venue="curve", min_out="100"),
                    ]
                ),
                min_outs=["100", "100"],
                meta={
                    "strategy_family": "funding_arb",
                    "profit_after_costs": "250",
                    "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
                    "capture": {
                        "metadata": {"execution_route_plan": _operator_execution_route_plan_ready()}
                    },
                },
            )
        ]
        self._family_hardening_service = SimpleNamespace(
            family_state=lambda runtime, family: {
                "enabled": True,
                "controls": {
                    "admission_ready": True,
                    "execution_eligible": True,
                    "capital_eligible": True,
                    "treasury_eligible": True,
                    "governance_eligible": True,
                    "recovery_ready": True,
                },
                "explanation": {"status": "active", "recovery_ready": True},
                "readiness": {"ready": True, "actualExecutionReady": True},
            }
        )
        self._treasury = SimpleNamespace(
            cfg=SimpleNamespace(
                enabled=True, allow_maximum=False, max_aggressiveness_without_approval="HIGH"
            ),
            snapshot=lambda: {
                "aggressiveness": {
                    "aggressiveness_level": "MAXIMUM",
                    "aggressiveness_multiplier": 1.4,
                },
                "goal": {"target_return_percentage": 12.0, "max_drawdown_pct": 4.0},
            },
            governance_check=lambda *, aggressiveness_level, approved_by_human=False: {
                "ok": False,
                "reason": "maximum_disabled",
            },
        )
        self.fund_summary_state = lambda: {
            "ok": True,
            "health": {
                "holdReasonCode": "",
                "holdReasonCodes": [],
                "recoveryReady": True,
                "recoveryStatus": "ready",
            },
        }


async def _build_snapshot_treasury_auto_trade_gate():
    rt = _OperatorTreasuryGateRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["autoTradeGate"]["allowed"] is False
    assert out["autoTradeGate"]["stage"] == "treasury_hold"
    assert out["autoTradeGate"]["reasonCode"] == "maximum_disabled"
    assert out["autoTradeRecovery"]["ready"] is False
    assert out["autoTradeRecovery"]["status"] == "treasury_alignment_required"
    assert out["autoTradeRecovery"]["reasonCode"] == "maximum_disabled"
    assert "Autonomous execution is blocked because maximum disabled." in out["pausedReason"]


def test_operator_summary_snapshot_surfaces_auto_trade_gate_when_treasury_blocks_ready_opportunity():
    import asyncio

    asyncio.run(_build_snapshot_treasury_auto_trade_gate())


class _ExplodingOperatorAdmissionService(ExecutionService):
    def build_live_state(self, runtime):
        return {
            "items": [
                {
                    "endpoint": "rpc-fast",
                    "lane": "PRIVATE",
                    "flashloan": {"selectedProvider": "aave"},
                }
            ]
        }

    def auto_trade_hold_gate(self, runtime):
        raise RuntimeError("fund summary offline")


class _OperatorAdmissionFailureRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._execution_service = _ExplodingOperatorAdmissionService()
        self._opps = [
            SimpleNamespace(
                id="after-cost",
                strategy="flash_arb",
                expected_profit_raw="100",
                can_execute=True,
                route_id="r-after",
                meta={
                    "strategy_family": "flashloan_atomic",
                    "profit_after_costs": "250",
                    "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
                },
            )
        ]
        self.fund_summary_state = lambda: {
            "ok": True,
            "health": {
                "holdReasonCode": "",
                "holdReasonCodes": [],
                "recoveryReady": True,
                "recoveryStatus": "ready",
            },
        }


async def _build_snapshot_admission_failure_gate():
    rt = _OperatorAdmissionFailureRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["autoTradeGate"]["allowed"] is False
    assert out["autoTradeGate"]["stage"] == "admission_hold"
    assert out["autoTradeGate"]["reasonCode"] == "admission_gate_failed"
    assert out["autoTradeRecovery"]["ready"] is False
    assert out["autoTradeRecovery"]["status"] == "auto_trade_admission_restore_required"
    assert out["autoTradeRecovery"]["reasonCode"] == "admission_gate_failed"
    assert "Autonomous execution is blocked because admission gate failed." in out["pausedReason"]


def test_operator_summary_snapshot_fails_closed_when_auto_trade_admission_gate_errors():
    import asyncio

    asyncio.run(_build_snapshot_admission_failure_gate())


def test_operator_summary_snapshot_projects_family_hardening_auto_trade_recovery_contract():
    import asyncio

    rt = _Runtime()
    rt._execution_service = ExecutionService()
    rt._opps = [
        SimpleNamespace(
            id="op-family-hardening",
            strategy="funding_arb",
            expected_profit_raw="1000",
            can_execute=True,
            route_id="r-fh",
            route=SimpleNamespace(
                legs=[
                    SimpleNamespace(venue="uni", min_out="100"),
                    SimpleNamespace(venue="curve", min_out="100"),
                ]
            ),
            min_outs=["100", "100"],
            meta={
                "strategy_family": "funding_arb",
                "profit_after_costs": "250",
                "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
                "capture": {
                    "metadata": {"execution_route_plan": _operator_execution_route_plan_ready()}
                },
            },
        )
    ]
    rt.fund_summary_state = lambda: {
        "ok": True,
        "health": {
            "holdReasonCode": "",
            "holdReasonCodes": [],
            "recoveryReady": True,
            "recoveryStatus": "ready",
        },
    }
    svc = OperatorSummaryService()
    out = asyncio.run(svc.build_snapshot(rt))
    assert out["autoTradeGate"]["stage"] == "family_hold"
    assert out["autoTradeGate"]["reasonCode"] == "family_hardening_service_unavailable"
    assert out["autoTradeRecovery"]["status"] == "family_hardening_restore_required"
    assert out["autoTradeRecovery"]["reasonCode"] == "family_hardening_service_unavailable"
    assert out["autoTradeRecovery"]["familyHardeningReasonCodes"] == [
        "family_hardening_service_unavailable"
    ]
    assert out["autoTradeRecovery"]["reliabilityClass"] == "unavailable"
    assert (
        out["autoTradeRecovery"]["reliabilityReasonCode"]
        == "family_hardening_reliability_unavailable"
    )
    assert out["autoTradeRecovery"]["historyComponent"] == "family_hardening"
    assert out["autoTradeRecovery"]["historyStatus"] == "degraded"


class _PersistentOperatorTreasuryGateRuntime(_OperatorTreasuryGateRuntime):
    def __init__(self, db_path: str):
        super().__init__()
        self._db = PersistenceDB(db_path)
        self._treasury_reason = "maximum_disabled"
        self._treasury = SimpleNamespace(
            cfg=SimpleNamespace(
                enabled=True, allow_maximum=False, max_aggressiveness_without_approval="HIGH"
            ),
            snapshot=lambda: {
                "aggressiveness": {
                    "aggressiveness_level": "MAXIMUM",
                    "aggressiveness_multiplier": 1.4,
                },
                "goal": {"target_return_percentage": 12.0, "max_drawdown_pct": 4.0},
                "approved_by_human": self._treasury_reason == "ok",
            },
            governance_check=lambda *, aggressiveness_level, approved_by_human=False: {
                "ok": self._treasury_reason == "ok",
                "reason": ("ok" if self._treasury_reason == "ok" else self._treasury_reason),
            },
        )


async def _build_snapshot_persisted_auto_trade_recovery(tmp_path):
    rt = _PersistentOperatorTreasuryGateRuntime(str(tmp_path / "runtime.sqlite3"))
    svc = OperatorSummaryService()
    first = await svc.build_snapshot(rt)
    assert first["autoTradeRecovery"]["historyStatus"] == "blocked"
    assert first["autoTradeRecovery"]["degradedCount"] == 1
    first_history = list(first["autoTradeRecovery"].get("history") or [])
    assert len(first_history) == 1
    assert first_history[0]["eventType"] == "blocked"
    assert first_history[0]["reasonCode"] == "maximum_disabled"

    blocked_again = await svc.build_snapshot(rt)
    assert blocked_again["autoTradeRecovery"]["historyStatus"] == "blocked"
    assert blocked_again["autoTradeRecovery"]["degradedCount"] == 1
    blocked_again_history = list(blocked_again["autoTradeRecovery"].get("history") or [])
    assert len(blocked_again_history) == 1
    assert blocked_again_history[0]["eventType"] == "blocked"

    rt._treasury_reason = "ok"
    second = await svc.build_snapshot(rt)
    assert second["autoTradeGate"]["reasonCode"] == "ok"
    assert second["autoTradeRecovery"]["status"] == "ready"
    assert second["autoTradeRecovery"]["historyStatus"] == "recovered"
    assert second["autoTradeRecovery"]["degradedCount"] == 1
    assert second["autoTradeRecovery"]["lastHealthyTsMs"] > 0
    assert second["autoTradeRecovery"]["reliabilityClass"] in {"fragile", "stable"}
    second_history = list(second["autoTradeRecovery"].get("history") or [])
    assert [evt["eventType"] for evt in second_history[:2]] == ["recovered", "blocked"]
    assert second_history[0]["reasonCode"] == "ok"


async def _build_snapshot_persisted_auto_trade_recovery_blocked_update(tmp_path):
    rt = _PersistentOperatorTreasuryGateRuntime(str(tmp_path / "runtime.sqlite3"))
    svc = OperatorSummaryService()
    first = await svc.build_snapshot(rt)
    assert first["autoTradeRecovery"]["historyStatus"] == "blocked"
    assert first["autoTradeRecovery"]["degradedCount"] == 1
    first_history = list(first["autoTradeRecovery"].get("history") or [])
    assert len(first_history) == 1
    assert first_history[0]["eventType"] == "blocked"
    assert first_history[0]["reasonCode"] == "maximum_disabled"

    rt._treasury_reason = "aggressiveness_requires_approval"
    updated = await svc.build_snapshot(rt)
    assert updated["autoTradeGate"]["reasonCode"] == "aggressiveness_requires_approval"
    assert updated["autoTradeRecovery"]["historyStatus"] == "blocked"
    assert updated["autoTradeRecovery"]["degradedCount"] == 1
    updated_history = list(updated["autoTradeRecovery"].get("history") or [])
    assert [evt["eventType"] for evt in updated_history[:2]] == ["blocked_update", "blocked"]
    assert updated_history[0]["reasonCode"] == "aggressiveness_requires_approval"
    assert updated_history[0]["stage"] == "treasury_hold"

    repeated = await svc.build_snapshot(rt)
    repeated_history = list(repeated["autoTradeRecovery"].get("history") or [])
    assert [evt["eventType"] for evt in repeated_history[:2]] == ["blocked_update", "blocked"]
    assert len(repeated_history) == 2


def test_operator_summary_snapshot_records_blocked_update_when_blocker_reason_changes_while_degraded(
    tmp_path,
):
    import asyncio

    asyncio.run(_build_snapshot_persisted_auto_trade_recovery_blocked_update(tmp_path))


def test_operator_summary_snapshot_persists_auto_trade_recovery_history_across_recovery_cycle(
    tmp_path,
):
    import asyncio

    asyncio.run(_build_snapshot_persisted_auto_trade_recovery(tmp_path))


class _SummaryCaptureForcePublicRuntime(_OperatorTreasuryGateRuntime):
    def __init__(self):
        super().__init__()
        self._execution_service = ExecutionService()
        self._opps = [
            SimpleNamespace(
                id="op-family-hardening",
                strategy="funding_arb",
                expected_profit_raw="1000",
                can_execute=True,
                route_id="r-fh",
                route=SimpleNamespace(
                    legs=[
                        SimpleNamespace(venue="uni", min_out="100"),
                        SimpleNamespace(venue="curve", min_out="100"),
                    ]
                ),
                min_outs=["100", "100"],
                meta={
                    "strategy_family": "funding_arb",
                    "profit_after_costs": "250",
                    "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
                    "capture": {
                        "lane": "PRIVATE",
                        "metadata": {
                            "execution_route_plan": {
                                "executable": True,
                                "selected_venues": ["uni", "curve"],
                                "provider_priority": ["router-a"],
                                "route_invalid_causes": [],
                            }
                        },
                    },
                },
            )
        ]
        self._cc.controls.force_send_mode = "public"
        self.cfg.chain.name = "ethereum"
        self.cfg.execution.redact_routes_when_private = False
        self.cfg.execution.dry_run = False
        self.cfg.execution.withdraw_mode = "txdata"
        self.cfg.execution.brain_mode = "off"
        self.rpc_manager = SimpleNamespace(
            snapshot=lambda: {"read": [{"ok": True}], "send": [{"ok": True}]}
        )
        self.metrics.model_dump = lambda: {
            "gas_mode": self.metrics.gas_mode,
            "send_mode": self.metrics.send_mode,
            "realized_profit_raw": getattr(self.metrics, "realized_profit_raw", "0"),
            "efficiency_pct": getattr(self.metrics, "efficiency_pct", 0.0),
            "success_rate_pct": getattr(self.metrics, "success_rate_pct", 0.0),
        }
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=0, max_borrow_amount_wei=0),
            state=SimpleNamespace(
                realized_profit_wei=0,
                last_amount_in_wei=0,
                success_streak=0,
                fail_streak=0,
            ),
            success_rate_pct=lambda: 0.0,
        )
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 0.0, "success_rate_pct": 0.0}
        )
        self._errors = []
        self._exec_log = []

    def fund_summary_state(self):
        return {
            "ok": True,
            "health": {
                "holdReasonCode": "",
                "holdReasonCodes": [],
                "recoveryReady": True,
                "recoveryStatus": "ready",
            },
        }


def test_state_service_summary_surfaces_capture_lane_force_send_conflict_before_later_treasury_blockers():
    rt = _SummaryCaptureForcePublicRuntime()
    import asyncio

    out = asyncio.run(StateService().summary(rt))
    assert out["auto_trade_gate"]["stage"] == "route_hold"
    assert out["auto_trade_gate"]["reason_code"] == "private_lane_required"
    assert "operator_force_send_mode_conflict" in out["auto_trade_gate"]["reason_codes"]
    assert (
        out["auto_trade_gate"]["next_action"]
        == "clear_force_send_mode_or_restore_private_submission"
    )


class _ReceiptOutcomeTruthHoldRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                    "holdReasonCode": "settled_profit_truth_unavailable",
                    "holdReasonCodes": ["settled_profit_truth_unavailable"],
                    "capitalTruthReasonCodes": ["settled_profit_truth_unavailable"],
                    "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
                    "suggestedNextAction": "restore_receipt_outcome_truth",
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "settled_profit_truth_unavailable",
                    "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
                    "recoveryNextAction": "restore_receipt_outcome_truth",
                    "recoveryHistoryComponent": "receipt_outcome_truth",
                    "recoveryHistoryStatus": "degraded",
                    "receiptOutcomeTruthRecoveryHistoryStatus": "degraded",
                    "receiptOutcomeTruthReliabilityClass": "degraded",
                    "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                    "receiptOutcomeTruthReliabilityReasonCodes": [
                        "receipt_outcome_truth_reliability_degraded",
                        "settled_profit_truth_unavailable",
                    ],
                    "recoveryReliabilityClass": "degraded",
                    "recoveryReliabilityReasonCode": "recovery_reliability_degraded",
                    "recoveryReliabilityReasonCodes": [
                        "recovery_reliability_degraded",
                        "receipt_outcome_truth_reliability_degraded",
                        "settled_profit_truth_unavailable",
                    ],
                    "recoveryReliabilityNextAction": "restore_receipt_outcome_truth",
                },
            }
        )


async def _build_snapshot_receipt_outcome_truth_hold_sync():
    rt = _ReceiptOutcomeTruthHoldRuntime()
    svc = OperatorSummaryService()
    out = await svc.build_snapshot(rt)
    assert out["ok"] is True
    assert out["portfolio"]["state"] == "defensive"
    assert out["holdReasonCode"] == "settled_profit_truth_unavailable"
    assert out["receiptOutcomeTruthReasonCodes"] == ["settled_profit_truth_unavailable"]
    assert out["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_view_uses_history_stage_and_reason_for_recovered_current_view():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "history_reason_code": "settled_profit_truth_unavailable",
        "history_reason_codes": ["settled_profit_truth_unavailable"],
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["stage"] == "fund_hold"
    assert out["reasonCode"] == "settled_profit_truth_unavailable"
    assert out["reasonCodes"] == ["settled_profit_truth_unavailable"]
    assert out["recoveryStatus"] == "capital_truth_restore_required"
    assert out["recoveryHistoryComponent"] == "receipt_outcome_truth"
    assert out["receiptOutcomeTruthRecoveryHistoryStatus"] == "degraded"
    assert out["receiptOutcomeTruthReliabilityClass"] == "degraded"
    assert out["recoveryReliabilityNextAction"] == "restore_receipt_outcome_truth"
    assert out["observability"]["oppsExecutable"] == 0
    assert "settled profit truth unavailable" in out["pausedReason"]
    assert "restore receipt outcome truth" in out["pausedReason"]


def test_operator_summary_snapshot_surfaces_receipt_outcome_truth_as_first_class_recovery_component():
    import asyncio

    asyncio.run(_build_snapshot_receipt_outcome_truth_hold_sync())


def test_operator_summary_auto_trade_recovery_view_preserves_receipt_outcome_truth_history_fields():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "receipt_outcome_truth",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "degraded",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_degraded",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "recent_events": [
            {
                "ts_ms": 2000,
                "event_type": "recovered",
                "stage": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "blocker_component": "receipt_outcome_truth",
                "next_action": "",
                "history_status": "recovered",
                "degraded_count": 1,
                "history_component": "receipt_outcome_truth",
                "history_stage": "fund_hold",
                "reliability_class": "degraded",
                "reliability_reason_code": "receipt_outcome_truth_reliability_degraded",
                "reliability_reason_codes": [
                    "receipt_outcome_truth_reliability_degraded",
                    "settled_profit_truth_unavailable",
                ],
                "reliability_next_action": "restore_receipt_outcome_truth",
                "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
            }
        ],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["historyComponent"] == "receipt_outcome_truth"
    assert out["receiptOutcomeTruthReasonCodes"] == ["settled_profit_truth_unavailable"]
    assert out["componentReliabilityClass"] == "degraded"
    assert out["componentReliabilityReasonCode"] == ("receipt_outcome_truth_reliability_degraded")
    assert out["componentReliabilityReasonCodes"] == [
        "receipt_outcome_truth_reliability_degraded",
        "settled_profit_truth_unavailable",
    ]
    assert out["componentReliabilityNextAction"] == "restore_receipt_outcome_truth"
    assert out["componentRecoveredFragile"] is False
    assert out["history"][0]["historyComponent"] == "receipt_outcome_truth"
    assert out["history"][0]["componentReliabilityClass"] == "degraded"
    assert out["history"][0]["componentReliabilityReasonCode"] == (
        "receipt_outcome_truth_reliability_degraded"
    )
    assert out["history"][0]["componentReliabilityReasonCodes"] == [
        "receipt_outcome_truth_reliability_degraded",
        "settled_profit_truth_unavailable",
    ]
    assert out["history"][0]["componentReliabilityNextAction"] == ("restore_receipt_outcome_truth")
    assert out["history"][0]["componentRecoveredFragile"] is False
    assert out["history"][0]["receiptOutcomeTruthReasonCodes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert out["history"][0]["reliabilityReasonCode"] == (
        "receipt_outcome_truth_reliability_degraded"
    )


def test_auto_trade_recovery_view_preserves_component_fragility_after_recovery():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "receipt_outcome_truth",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [
            {
                "ts_ms": 2000,
                "event_type": "recovered",
                "stage": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "blocker_component": "receipt_outcome_truth",
                "next_action": "",
                "history_status": "recovered",
                "degraded_count": 1,
                "history_component": "receipt_outcome_truth",
                "history_stage": "fund_hold",
                "reliability_class": "fragile",
                "reliability_reason_code": "auto_trade_recovery_fragile",
                "reliability_reason_codes": ["auto_trade_recovery_fragile"],
                "reliability_next_action": "monitor_auto_trade_reentry",
                "component_reliability_class": "fragile",
                "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
                "component_reliability_reason_codes": [
                    "receipt_outcome_truth_reliability_fragile",
                    "settled_profit_truth_unavailable",
                ],
                "component_reliability_next_action": "restore_receipt_outcome_truth",
                "component_recovered_fragile": True,
                "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
            }
        ],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["componentRecoveredFragile"] is True
    assert out["history"][0]["componentRecoveredFragile"] is True
    assert out["history"][0]["componentReliabilityClass"] == "fragile"


def test_auto_trade_recovery_view_uses_history_component_and_component_next_action_for_recovered_events():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "receipt_outcome_truth",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [
            {
                "ts_ms": 2000,
                "event_type": "recovered",
                "stage": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "blocker_component": "",
                "next_action": "",
                "history_status": "recovered",
                "degraded_count": 1,
                "history_component": "receipt_outcome_truth",
                "history_stage": "fund_hold",
                "reliability_class": "fragile",
                "reliability_reason_code": "auto_trade_recovery_fragile",
                "reliability_reason_codes": ["auto_trade_recovery_fragile"],
                "reliability_next_action": "monitor_auto_trade_reentry",
                "component_reliability_class": "fragile",
                "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
                "component_reliability_reason_codes": [
                    "receipt_outcome_truth_reliability_fragile",
                    "settled_profit_truth_unavailable",
                ],
                "component_reliability_next_action": "restore_receipt_outcome_truth",
                "component_recovered_fragile": True,
                "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
            }
        ],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["history"][0]["component"] == "receipt_outcome_truth"
    assert out["history"][0]["historyComponent"] == "receipt_outcome_truth"
    assert out["history"][0]["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_view_uses_history_stage_and_reason_for_recovered_events():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "receipt_outcome_truth",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [
            {
                "ts_ms": 2000,
                "event_type": "recovered",
                "stage": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "blocker_component": "",
                "next_action": "",
                "history_status": "recovered",
                "degraded_count": 1,
                "history_component": "receipt_outcome_truth",
                "history_stage": "fund_hold",
                "history_reason_code": "settled_profit_truth_unavailable",
                "history_reason_codes": ["settled_profit_truth_unavailable"],
                "reliability_class": "fragile",
                "reliability_reason_code": "auto_trade_recovery_fragile",
                "reliability_reason_codes": ["auto_trade_recovery_fragile"],
                "reliability_next_action": "monitor_auto_trade_reentry",
                "component_reliability_class": "fragile",
                "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
                "component_reliability_reason_codes": [
                    "receipt_outcome_truth_reliability_fragile",
                    "settled_profit_truth_unavailable",
                ],
                "component_reliability_next_action": "restore_receipt_outcome_truth",
                "component_recovered_fragile": True,
                "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
            }
        ],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["history"][0]["stage"] == "fund_hold"
    assert out["history"][0]["reasonCode"] == "settled_profit_truth_unavailable"
    assert out["history"][0]["reasonCodes"] == ["settled_profit_truth_unavailable"]


def test_auto_trade_recovery_view_uses_history_component_and_component_next_action_for_recovered_current_view():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["component"] == "receipt_outcome_truth"
    assert out["suggestedNextAction"] == "restore_receipt_outcome_truth"


def test_auto_trade_recovery_view_uses_history_stage_and_reason_for_recovered_current_view():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "history_reason_code": "settled_profit_truth_unavailable",
        "history_reason_codes": ["settled_profit_truth_unavailable"],
        "reliability_class": "fragile",
        "reliability_reason_code": "auto_trade_recovery_fragile",
        "reliability_reason_codes": ["auto_trade_recovery_fragile"],
        "reliability_next_action": "monitor_auto_trade_reentry",
        "component_reliability_class": "fragile",
        "component_reliability_reason_code": "receipt_outcome_truth_reliability_fragile",
        "component_reliability_reason_codes": [
            "receipt_outcome_truth_reliability_fragile",
            "settled_profit_truth_unavailable",
        ],
        "component_reliability_next_action": "restore_receipt_outcome_truth",
        "component_recovered_fragile": True,
        "receipt_outcome_truth_reason_codes": ["settled_profit_truth_unavailable"],
        "recent_events": [],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["stage"] == "fund_hold"
    assert out["reasonCode"] == "settled_profit_truth_unavailable"
    assert out["reasonCodes"] == ["settled_profit_truth_unavailable"]


def test_auto_trade_recovery_view_exports_history_lifecycle_fields():
    recovery = {
        "blocked": False,
        "ready": True,
        "stage": "ok",
        "status": "ready",
        "reason_code": "ok",
        "reason_codes": [],
        "next_action": "",
        "component": "receipt_outcome_truth",
        "history_status": "recovered",
        "history_component": "receipt_outcome_truth",
        "history_stage": "fund_hold",
        "recent_events": [
            {
                "ts_ms": 2000,
                "event_type": "recovered",
                "stage": "fund_hold",
                "reason_code": "settled_profit_truth_unavailable",
                "reason_codes": ["settled_profit_truth_unavailable"],
                "blocker_component": "receipt_outcome_truth",
                "next_action": "restore_receipt_outcome_truth",
                "history_status": "recovered",
                "degraded": False,
                "degraded_since_ts_ms": 1000,
                "recovered_at_ts_ms": 2000,
                "last_healthy_ts_ms": 2000,
                "updated_ts_ms": 2000,
                "degraded_count": 1,
                "history_component": "receipt_outcome_truth",
                "history_stage": "fund_hold",
            }
        ],
    }

    out = OperatorSummaryService._auto_trade_recovery_view(recovery)

    assert out["history"][0]["degraded"] is False
    assert out["history"][0]["degradedSinceTsMs"] == 1000
    assert out["history"][0]["recoveredAtTsMs"] == 2000
    assert out["history"][0]["lastHealthyTsMs"] == 2000
    assert out["history"][0]["updatedTsMs"] == 2000
