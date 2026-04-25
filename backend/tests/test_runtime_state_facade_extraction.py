from types import SimpleNamespace
import asyncio

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_state_facade import RuntimeStateFacade
from victor_ai_bot.runtime_services.family_hardening_service import FamilyHardeningService
from victor_ai_bot.runtime_services.state_service import apply_auto_trade_gate_to_top_opportunity

EXTRACTED_METHODS = {
    "telemetry_summary",
    "capital_engine_state",
    "fund_summary_state",
    "service_health_state",
    "analytics_state",
}


class _FakeStateSummary:
    def capital_engine(self, runtime):
        return {"capital_engine": {"ok": True, "chain": getattr(runtime, "chain", "")}}

    def fund_summary(self, runtime):
        return {"ok": True, "source": "fund_service"}

    def analytics(self, runtime):
        return {"ok": True, "source": "analytics_service"}


class _FakeTelemetry:
    def summary(self):
        return {"realization": {"families": [{"family": "flashloan_atomic"}]}}


class _DummyRuntime(RuntimeStateFacade):
    def __init__(self):
        self.chain = "ethereum"
        self._state_summary_service = _FakeStateSummary()
        self._telemetry_service = _FakeTelemetry()
        self._decision = type("Decision", (), {"brain_state": lambda self: {"ok": True}})()
        self._auxiliary_state_service = type(
            "Aux",
            (),
            {
                "metrics_state": lambda self: {"loopMsP50": 12.5},
                "unified_state": lambda self: {"ok": True},
                "spread_opportunities": lambda self: {"items": []},
                "consensus_state": lambda self: {"items": []},
                "orchestrator_state": lambda self: {"ok": True},
                "behaveagent_state": lambda self: {"ok": True},
                "treasury_state": lambda self: {"ok": True},
                "governance_layer_state": lambda self: {"ok": True},
                "blockspace_state": lambda self: {"ok": True},
                "quicksight_state": lambda self: {"ok": True},
                "quicksight_dataset": lambda self, runtime, name: {"name": name},
                "quicksight_dashboards": lambda self: {"items": []},
                "quicksight_ask": lambda self, runtime, question, role, token: {
                    "question": question
                },
                "quicksight_scenario": lambda self, runtime, params, role, token: {
                    "params": params
                },
                "agent_hub_state": lambda self, runtime, agent_attribution: {
                    "agents": agent_attribution.get("agents", [])
                },
                "research_pipeline_state": lambda self, runtime: {"items": []},
                "doctrine_state": lambda self, runtime: {"ok": True},
                "ledger_state": lambda self, runtime: {"items": []},
                "internal_prime_state": lambda self, runtime: {"ok": True},
                "cio_summary_state": lambda self, runtime: {"ok": True},
            },
        )()

    def agent_attribution_state(self):
        return {"agents": [{"name": "allocator"}]}


def test_runtime_bundle_inherits_extracted_state_facade():
    assert issubclass(RuntimeBundle, RuntimeStateFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_state_facade_preserves_summary_behavior_and_aliases():
    runtime = _DummyRuntime()

    assert runtime.telemetry_summary()["realization"]["families"][0]["family"] == "flashloan_atomic"
    assert runtime.capital_engine_state()["capital_engine"]["chain"] == "ethereum"
    assert (
        runtime.fund_state()
        == runtime.fund_summary_state()
        == {"ok": True, "source": "fund_service"}
    )
    assert runtime.analytics_state() == {"ok": True, "source": "analytics_service"}


def test_runtime_state_facade_unavailable_defaults_remain_operator_safe():
    runtime = _DummyRuntime()
    runtime._state_summary_service = None
    runtime._withdraw_all_service = None
    runtime._family_hardening_service = None
    runtime._capital_truth_service = None

    execution = runtime.service_health_state()["execution"]
    assert execution["reason"] == "execution_service_unavailable"
    assert execution["reason_code"] == execution["reason"]
    assert execution["status"] == "unavailable"

    withdraw = asyncio.run(runtime.withdraw_all_state())
    assert withdraw["reason_code"] == "withdraw_all_service_unavailable"
    assert withdraw["reason"] == withdraw["reason_code"]
    assert withdraw["status"] == "unavailable"

    assert runtime.launch_state()["reason_code"] == "launch_service_unavailable"
    fund_summary = runtime.fund_summary_state()
    assert fund_summary["reason_code"] == "fund_service_unavailable"
    assert fund_summary["fundOs"]["fund_os"]["stage_policy"]["stage"] == "internal_capital"
    assert "profitDoctrine" in fund_summary
    assert "ledger" in fund_summary
    assert "internalPrime" in fund_summary
    assert fund_summary["capitalTruth"]["reason_code"] == "capital_truth_service_unavailable"
    assert fund_summary["familyHardening"]["items"] == []
    assert fund_summary["researchPipeline"] == {"items": []}
    assert runtime.family_hardening_state()["items"] == []
    assert runtime.family_hardening_state()["status"] == "unavailable"
    assert runtime.capital_truth_state()["reason_code"] == "capital_truth_service_unavailable"
    assert runtime.analytics_state()["error"] == "analytics_service_unavailable"
    assert runtime.analytics_state()["reason_code"] == "analytics_service_unavailable"
    assert runtime.capital_explain()["text"] == "capital_explanation_unavailable"
    assert runtime.capital_explain()["reason_code"] == "capital_explanation_unavailable"
    assert runtime.analytics_state()["status"] == "unavailable"


class _ExplodingTelemetry:
    def summary(self):
        raise RuntimeError("telemetry down")


class _ExplodingAux:
    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise RuntimeError(f"{name} failed")

        return _boom


class _ExplodingSummaryService:
    def summary(self, runtime):
        raise RuntimeError("summary failed")


class _ExplodingWithdrawService:
    async def state(self, runtime):
        raise RuntimeError("withdraw failed")


class _ExplodingStateSummary:
    def __getattr__(self, name):
        def _boom(*args, **kwargs):
            raise RuntimeError(f"{name} failed")

        return _boom


class _FamilyHardeningUnavailableSummaryRuntime(RuntimeStateFacade):
    def __init__(self):
        self.chain = "ethereum"
        self._family_hardening_service = FamilyHardeningService()
        self._capital_truth_service = None
        self._state_summary_service = None
        self._withdraw_all_service = None
        self._telemetry_service = type(
            "Telemetry", (), {"summary": lambda self: {"realization": {"families": []}}}
        )()
        self._decision = type("Decision", (), {"brain_state": lambda self: {"ok": True}})()
        self._auxiliary_state_service = type(
            "Aux",
            (),
            {
                "metrics_state": lambda self: {},
                "research_pipeline_state": lambda self, runtime: {"items": []},
                "doctrine_state": lambda self, runtime: {"ok": True},
                "ledger_state": lambda self, runtime: {"items": []},
                "internal_prime_state": lambda self, runtime: {"ok": True},
                "cio_summary_state": lambda self, runtime: {"ok": True},
            },
        )()

    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "familyHardeningStatus": "unavailable",
                "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                "familyHardeningReliabilityClass": "unavailable",
                "familyHardeningReliabilityReasonCode": "family_hardening_reliability_unavailable",
                "familyHardeningReliabilityReasonCodes": [
                    "family_hardening_reliability_unavailable"
                ],
                "recoveryReady": True,
                "recoveryStatus": "ready",
                "recoveryReasonCode": "ok",
                "recoveryReasonCodes": [],
            }
        }

    def strategy_scorecards_state(self):
        return {
            "families": [
                {
                    "family": "funding_arb",
                    "count": 8,
                    "executionSuccessRate": 0.75,
                    "gasEfficiency": 2.5,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.1,
                }
            ]
        }

    def engine_state(self):
        return {
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 42.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                }
            ],
        }

    def telemetry_summary(self):
        return {"venueReliability": 0.8}

    def execution_calibration_state(self):
        return {"items": [{"route_family": "funding", "calibration_factor": 0.9}]}

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"funding_arb": 0.2}}}


def test_runtime_state_facade_surfaces_top_level_family_hardening_service_degradation_from_service_summary():
    runtime = _FamilyHardeningUnavailableSummaryRuntime()
    payload = runtime.family_hardening_state()

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "family_hardening_service_unavailable"
    assert payload["reason_codes"] == ["family_hardening_service_unavailable"]
    assert payload["recovery_status"] == "family_hardening_restore_required"
    assert payload["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert payload["recovery_reliability_class"] == "unavailable"
    assert payload["family_hardening_reason_codes"] == ["family_hardening_service_unavailable"]
    assert payload["items"]


class _FamilyHardeningReceiptOutcomeTruthSummaryRuntime(_FamilyHardeningUnavailableSummaryRuntime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
                "receiptOutcomeTruthRecoveryHistoryStatus": "degraded",
                "receiptOutcomeTruthDegradedSinceTsMs": 4102444800000,
                "receiptOutcomeTruthReliabilityClass": "degraded",
                "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "receiptOutcomeTruthReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                ],
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "settled_profit_truth_unavailable",
                "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
                "recoveryNextAction": "restore_receipt_outcome_truth",
                "recoveryHistoryComponent": "receipt_outcome_truth",
                "recoveryHistoryStatus": "degraded",
                "recoveryReliabilityClass": "degraded",
                "recoveryReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "recoveryReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                ],
                "familyHardeningStatus": "ok",
                "familyHardeningReasonCodes": [],
                "familyHardeningReliabilityClass": "stable",
                "familyHardeningReliabilityReasonCode": "ok",
                "familyHardeningReliabilityReasonCodes": [],
            }
        }


class _FamilyHardeningRecoveredFragileSummaryRuntime(_FamilyHardeningUnavailableSummaryRuntime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "familyHardeningStatus": "ok",
                "familyHardeningReasonCodes": [],
                "familyHardeningRecoveryHistoryStatus": "recovered",
                "familyHardeningRecoveredRecently": True,
                "familyHardeningDegradedCount": 2,
                "familyHardeningRecoveredFragile": True,
                "familyHardeningReliabilityClass": "fragile",
                "familyHardeningReliabilityReasonCode": "family_hardening_reliability_fragile",
                "familyHardeningReliabilityReasonCodes": [
                    "family_hardening_reliability_fragile",
                    "family_hardening_recovered_fragile",
                ],
                "recoveryReady": True,
                "recoveryStatus": "ready",
                "recoveryReasonCode": "ok",
                "recoveryReasonCodes": [],
                "recoveryReliabilityClass": "stable",
                "recoveryReliabilityReasonCode": "ok",
                "recoveryReliabilityReasonCodes": [],
            }
        }


def test_runtime_state_facade_surfaces_top_level_family_hardening_receipt_outcome_truth_from_service_summary():
    runtime = _FamilyHardeningReceiptOutcomeTruthSummaryRuntime()
    payload = runtime.family_hardening_state()

    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "settled_profit_truth_unavailable"
    assert payload["reason_codes"] == ["settled_profit_truth_unavailable"]
    assert payload["recovery_status"] == "capital_truth_restore_required"
    assert payload["recovery_reason_code"] == "settled_profit_truth_unavailable"
    assert payload["recovery_next_action"] == "restore_receipt_outcome_truth"
    assert payload["recovery_history_component"] == "receipt_outcome_truth"
    assert payload["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert payload["receipt_outcome_truth_recovery_history_status"] == "degraded"
    assert payload["receipt_outcome_truth_reliability_class"] == "degraded"


def test_runtime_state_facade_surfaces_top_level_family_hardening_recovered_fragility_from_service_summary():
    runtime = _FamilyHardeningRecoveredFragileSummaryRuntime()
    payload = runtime.family_hardening_state()

    assert payload["ok"] is True
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "family_hardening_reliability_fragile"
    assert payload["recovery_status"] == "degraded"
    assert payload["recovery_reason_code"] == "family_hardening_reliability_fragile"
    assert payload["recovery_history_component"] == "family_hardening"
    assert payload["recovery_history_status"] == "recovered"
    assert payload["recovery_degraded_count"] == 2
    assert payload["recovery_recovered_recently"] is True
    assert payload["recovery_reliability_class"] == "fragile"
    assert payload["recovery_recovered_fragile"] is True
    assert payload["family_hardening_recovered_fragile"] is True


def test_runtime_state_facade_route_facing_accessors_fail_closed_when_services_raise():
    runtime = _DummyRuntime()
    runtime._telemetry_service = _ExplodingTelemetry()
    runtime._auxiliary_state_service = _ExplodingAux()
    runtime._family_hardening_service = _ExplodingSummaryService()
    runtime._capital_truth_service = _ExplodingSummaryService()
    runtime._withdraw_all_service = _ExplodingWithdrawService()

    telemetry = runtime.telemetry_summary()
    assert telemetry == {"realization": {"families": []}, "agents": {"agents": []}}

    assert runtime.research_pipeline_state() == {
        "items": [],
        "pipelineCounts": {},
        "throughput": {},
    }
    assert runtime.doctrine_state() == {"optimizationObjectives": {}}
    assert runtime.ledger_state() == {"balances": {}, "tail": [], "transactions": []}
    assert runtime.internal_prime_state() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "internal_prime_unavailable",
        "reason": "internal_prime_unavailable",
        "borrowedUsd": 0.0,
        "capacityUsd": 0.0,
        "utilization": 0.0,
        "inventory": {},
        "familyExposure": {},
        "openLoans": [],
        "disputedLoans": [],
        "loanCount": 0,
        "disputedLoanCount": 0,
        "stateReady": False,
        "stateStatus": "unavailable",
        "stateReasonCode": "internal_prime_unavailable",
        "stateReason": "internal_prime_unavailable",
    }

    cio = runtime.cio_summary_state()
    assert cio["reason_code"] == "cio_service_unavailable"
    assert cio["status"] == "unavailable"

    unified = runtime.unified_state()
    assert unified["reason_code"] == "unified_state_unavailable"
    assert unified["enabled"] is False

    spread = runtime.spread_opportunities()
    assert spread["reason_code"] == "spread_opportunities_unavailable"
    assert spread["count"] == 0
    assert spread["opps"] == []

    consensus = runtime.consensus_state()
    assert consensus["reason_code"] == "consensus_state_unavailable"
    assert consensus["last"] == {}

    orchestrator = runtime.orchestrator_state()
    assert orchestrator["reason_code"] == "orchestrator_state_unavailable"
    assert orchestrator["enabled"] is False

    behave = runtime.behaveagent_state()
    assert behave["reason_code"] == "behaveagent_state_unavailable"
    assert behave["enabled"] is False

    governance = runtime.governance_layer_state()
    assert governance["reason_code"] == "governance_layer_unavailable"
    assert governance["enabled"] is False

    blockspace = runtime.blockspace_state()
    assert blockspace["reason_code"] == "blockspace_state_unavailable"
    assert blockspace["enabled"] is False

    quicksight = runtime.quicksight_state()
    assert quicksight["reason_code"] == "quicksight_unavailable"
    assert quicksight["enabled"] is False

    dataset = runtime.quicksight_dataset("fills")
    assert dataset["reason_code"] == "quicksight_unavailable"
    assert dataset["dataset"] == "fills"
    assert dataset["rows"] == []

    dashboards = runtime.quicksight_dashboards()
    assert dashboards["reason_code"] == "quicksight_unavailable"
    assert dashboards["dashboards"] == []

    ask = runtime.quicksight_ask("What changed?")
    assert ask["reason_code"] == "quicksight_unavailable"

    scenario = runtime.quicksight_scenario({"capital_shift": 0.1})
    assert scenario["reason_code"] == "quicksight_unavailable"

    agent_hub = runtime.agent_hub_state()
    assert agent_hub["reason_code"] == "agent_hub_state_unavailable"
    assert agent_hub["state"] == {}

    family_hardening = runtime.family_hardening_state()
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["reason_codes"] == ["family_hardening_service_unavailable"]
    assert family_hardening["recovery_status"] == "family_hardening_restore_required"
    assert family_hardening["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["recovery_next_action"] == "restore_family_hardening"
    assert family_hardening["recovery_history_component"] == "family_hardening"
    assert family_hardening["recovery_history_status"] == "degraded"
    assert family_hardening["recovery_reliability_class"] == "unavailable"
    assert family_hardening["family_hardening_reason_codes"] == [
        "family_hardening_service_unavailable"
    ]
    assert family_hardening["items"] == []

    capital_truth = runtime.capital_truth_state()
    assert capital_truth["reason_code"] == "capital_truth_service_unavailable"
    assert capital_truth["status"] == "unavailable"

    withdraw = asyncio.run(runtime.withdraw_all_state())
    assert withdraw["reason_code"] == "withdraw_all_service_unavailable"
    assert withdraw["status"] == "unavailable"


def test_runtime_state_facade_state_summary_backed_accessors_fail_closed_when_service_methods_raise():
    runtime = _DummyRuntime()
    runtime._state_summary_service = _ExplodingStateSummary()

    assert runtime.execution_capture_analytics() == {"laneSuccess": [], "venueQuality": []}
    assert runtime.execution_calibration_state() == {"items": []}
    assert runtime.venue_profiles_state() == {"venues": []}
    assert runtime.endpoint_quality_state() == {"lanes": {}, "relays": {}}
    assert runtime.venue_scorecards_state() == {"items": []}
    assert runtime.endpoint_universe_state() == {
        "read": {},
        "public": {},
        "protected": {},
        "private": {},
    }
    assert runtime.execution_live_state() == {"items": []}
    assert runtime.route_quality_state() == {"items": []}

    drawdown = runtime.drawdown_state()
    assert drawdown["drawdownPct"] == 0.0
    assert drawdown["hardStop"] == {"active": False, "reason_codes": []}

    assert runtime.kill_switch_state() == {"metrics": {}, "suppressions": {}, "history": []}
    assert runtime.risk_memory_state() == {"failures": {}}
    assert runtime.path_diversity_state() == {"paths": []}
    assert runtime.edge_learning_state() == {"items": [], "quarantine": {}, "explorationBudget": {}}

    launch = runtime.launch_state()
    assert launch["reason_code"] == "launch_service_unavailable"
    assert launch["status"] == "unavailable"

    assert runtime.rpc_preferences_state() == {
        "read": [],
        "send": [],
        "private": [],
        "configured": False,
    }
    assert runtime.strategy_scorecards_state() == {"families": []}
    assert runtime.agent_attribution_state() == {"agents": [{"name": "allocator"}]}
    assert runtime.capital_engine_state() == {
        "capital_engine": {},
        "reinvestment_policy": {},
        "capital_efficiency_metrics": {},
    }

    fund_summary = runtime.fund_summary_state()
    assert fund_summary["reason_code"] == "fund_service_unavailable"
    assert fund_summary["status"] == "unavailable"

    service_health = runtime.service_health_state()
    assert service_health["execution"]["reason_code"] == "execution_service_unavailable"

    capital_explain = runtime.capital_explain()
    assert capital_explain["reason_code"] == "capital_explanation_unavailable"
    assert capital_explain["text"] == "capital_explanation_unavailable"

    analytics = runtime.analytics_state()
    assert analytics["reason_code"] == "analytics_service_unavailable"
    assert analytics["status"] == "unavailable"


def test_apply_auto_trade_gate_to_top_opportunity_projects_receipt_outcome_truth_recovery_fields():
    top_info = {"id": "opp-top", "execution_allowed": True, "can_execute_after_costs": True}
    admission = SimpleNamespace(
        allowed=False,
        stage="fund_hold",
        reason="settled_profit_truth_unavailable",
        gate={
            "reason_codes": ["settled_profit_truth_unavailable"],
            "suggestedNextAction": "restore_receipt_outcome_truth",
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "settled_profit_truth_unavailable",
            "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
            "recoveryNextAction": "restore_receipt_outcome_truth",
            "recoveryHistoryComponent": "receipt_outcome_truth",
            "recoveryHistoryStatus": "degraded",
            "recoveryReliabilityClass": "degraded",
            "recoveryReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
            "recoveryReliabilityReasonCodes": [
                "receipt_outcome_truth_reliability_degraded",
                "settled_profit_truth_unavailable",
            ],
            "recoveryReliabilityNextAction": "restore_receipt_outcome_truth",
            "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
        },
    )

    out = apply_auto_trade_gate_to_top_opportunity(top_info, admission)

    assert out is not None
    assert out["execution_allowed"] is False
    assert out["can_execute_after_costs"] is False
    assert out["auto_trade_recovery_component"] == "receipt_outcome_truth"
    assert out["auto_trade_recovery_next_action"] == "restore_receipt_outcome_truth"


def test_apply_auto_trade_recovery_projection_uses_history_stage_and_reason_for_recovered_state():
    from victor_ai_bot.runtime_services.state_service import _apply_auto_trade_recovery_projection

    out = _apply_auto_trade_recovery_projection(
        {},
        {
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "ready": True,
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
        },
    )

    assert out["auto_trade_recovery_reason_code"] == "settled_profit_truth_unavailable"
    assert out["auto_trade_recovery_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert out["auto_trade_recovery_component_reliability_class"] == "degraded"
    assert (
        out["auto_trade_recovery_component_reliability_reason_code"]
        == "receipt_outcome_truth_reliability_degraded"
    )
    assert out["auto_trade_recovery_component_reliability_reason_codes"] == [
        "receipt_outcome_truth_reliability_degraded",
        "settled_profit_truth_unavailable",
    ]
    assert out["auto_trade_recovery_component_reliability_next_action"] == (
        "restore_receipt_outcome_truth"
    )
    assert out["auto_trade_recovery_receipt_outcome_truth_reason_codes"] == [
        "settled_profit_truth_unavailable"
    ]


def test_apply_auto_trade_recovery_projection_preserves_component_fragility():
    from victor_ai_bot.runtime_services.state_service import _apply_auto_trade_recovery_projection

    out = _apply_auto_trade_recovery_projection(
        {},
        {
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "ready": True,
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
        },
    )

    assert out["auto_trade_recovery_component_reliability_class"] == "fragile"
    assert out["auto_trade_recovery_component_reliability_reason_code"] == (
        "receipt_outcome_truth_reliability_fragile"
    )
    assert out["auto_trade_recovery_component_reliability_next_action"] == (
        "restore_receipt_outcome_truth"
    )
    assert out["auto_trade_recovery_component_recovered_fragile"] is True


def test_apply_auto_trade_recovery_projection_uses_history_component_and_component_next_action_for_recovered_state():
    from victor_ai_bot.runtime_services.state_service import _apply_auto_trade_recovery_projection

    out = _apply_auto_trade_recovery_projection(
        {},
        {
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "ready": True,
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
        },
    )

    assert out["auto_trade_recovery_component"] == "receipt_outcome_truth"
    assert out["auto_trade_recovery_next_action"] == "restore_receipt_outcome_truth"


def test_apply_auto_trade_recovery_projection_uses_history_stage_and_reason_for_recovered_state():
    from victor_ai_bot.runtime_services.state_service import _apply_auto_trade_recovery_projection

    out = _apply_auto_trade_recovery_projection(
        {},
        {
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "ready": True,
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
        },
    )

    assert out["auto_trade_recovery_reason_code"] == "settled_profit_truth_unavailable"
    assert out["auto_trade_recovery_reason_codes"] == ["settled_profit_truth_unavailable"]
