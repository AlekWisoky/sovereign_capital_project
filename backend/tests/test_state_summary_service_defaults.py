from victor_ai_bot.runtime_services.state_summary_service import ServiceSnapshotDefaults


def test_service_snapshot_defaults_preserve_legacy_keys_and_add_explicit_unavailable_shape():
    defaults = ServiceSnapshotDefaults()

    assert defaults.fund_summary["reason"] == "fund_service_unavailable"
    assert defaults.fund_summary["reason_code"] == "fund_service_unavailable"
    assert defaults.fund_summary["status"] == "unavailable"
    assert defaults.fund_summary["profitDoctrine"]["reason_code"] == "doctrine_unavailable"
    assert defaults.fund_summary["ledger"]["reason_code"] == "ledger_unavailable"
    assert defaults.fund_summary["internalPrime"]["reason_code"] == "internal_prime_unavailable"
    assert defaults.fund_summary["capitalTruth"]["reason_code"] == "capital_truth_unavailable"
    assert (
        defaults.fund_summary["familyHardening"]["reason_code"]
        == "family_hardening_service_unavailable"
    )
    assert defaults.fund_summary["familyHardening"]["reason_codes"] == [
        "family_hardening_service_unavailable"
    ]
    assert (
        defaults.fund_summary["familyHardening"]["recovery_status"]
        == "family_hardening_restore_required"
    )
    assert defaults.fund_summary["familyHardening"]["recovery_reliability_class"] == "unavailable"
    assert defaults.fund_summary["familyHardening"]["items"] == []
    assert defaults.fund_summary["researchPipeline"] == {
        "items": [],
        "pipelineCounts": {},
        "throughput": {},
    }

    assert defaults.analytics["error"] == "analytics_service_unavailable"
    assert defaults.analytics["reason_code"] == "analytics_service_unavailable"
    assert defaults.analytics["status"] == "unavailable"

    assert defaults.capital_summary["reason_code"] == "capital_summary_unavailable"
    assert defaults.capital_truth_state["reason_code"] == "capital_truth_service_unavailable"
    assert defaults.capital_explain["text"] == "capital_explanation_unavailable"
    assert defaults.capital_explain["reason_code"] == "capital_explanation_unavailable"
    assert defaults.capital_explain["status"] == "unavailable"
    assert defaults.capital_explain["facts"] == {}
    assert defaults.capital_explain["causal"] == {}

    services = defaults.services
    for key, reason_code in {
        "admission": "admission_service_unavailable",
        "execution": "execution_service_unavailable",
        "receipt": "receipt_service_unavailable",
        "telemetry": "telemetry_service_unavailable",
        "wealthGoal": "wealth_goal_service_unavailable",
        "replay": "replay_service_unavailable",
    }.items():
        payload = services[key]
        assert payload["reason"] == reason_code
        assert payload["reason_code"] == reason_code
        assert payload["status"] == "unavailable"


from types import SimpleNamespace

from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService


def test_state_summary_service_fills_partial_service_health_payloads_with_canonical_defaults():
    runtime = SimpleNamespace(
        _telemetry_service=SimpleNamespace(
            service_health=lambda runtime: {"execution": {"ok": True}}
        ),
    )

    payload = StateSummaryService().service_health(runtime)

    assert payload["execution"]["ok"] is True
    assert payload["admission"]["reason_code"] == "admission_service_unavailable"
    assert payload["receipt"]["reason_code"] == "receipt_service_unavailable"
    assert payload["wealthGoal"]["reason_code"] == "wealth_goal_service_unavailable"
    assert payload["replay"]["reason_code"] == "replay_service_unavailable"


def test_state_summary_service_degrades_bounded_runtime_failures_canonically():
    class _BrokenStore:
        def snapshot(self):
            raise RuntimeError("offline")

    class _BrokenExecService:
        def build_live_state(self, runtime):
            raise OSError("live state unavailable")

    class _BrokenTelemetryService:
        def service_health(self, runtime):
            raise RuntimeError("telemetry unavailable")

    class _BrokenAnalyticsService:
        def system_summary(self, runtime):
            raise RuntimeError("analytics unavailable")

    class _BrokenCapitalExplanationService:
        def explain(self, runtime, snapshot=None):
            raise RuntimeError("capital explain unavailable")

    class _BrokenReplay:
        def state(self):
            raise RuntimeError("replay unavailable")

    class _BrokenPnl:
        def state(self):
            raise RuntimeError("pnl unavailable")

    class _BrokenFamilyHardeningRuntime(SimpleNamespace):
        def family_hardening_state(self):
            raise RuntimeError("family hardening unavailable")

    runtime = _BrokenFamilyHardeningRuntime(
        _endpoint_universe=_BrokenStore(),
        _execution_service=_BrokenExecService(),
        _route_quality=_BrokenStore(),
        _drawdown_state=_BrokenStore(),
        _kill_switch=_BrokenStore(),
        _risk_memory=_BrokenStore(),
        _path_diversity=_BrokenStore(),
        _edge_learning=_BrokenStore(),
        _rpc_preferences=_BrokenStore(),
        _agent_attribution=SimpleNamespace(
            summary=lambda: (_ for _ in ()).throw(RuntimeError("agents unavailable"))
        ),
        _telemetry_service=_BrokenTelemetryService(),
        _analytics_service=_BrokenAnalyticsService(),
        _capital_explanation_service=_BrokenCapitalExplanationService(),
        _replay=_BrokenReplay(),
        _pnl=_BrokenPnl(),
        _launch_service=SimpleNamespace(
            summary=lambda runtime: (_ for _ in ()).throw(RuntimeError("launch unavailable"))
        ),
        _family_hardening_service=object(),
        _treasury=SimpleNamespace(
            snapshot=lambda: (_ for _ in ()).throw(RuntimeError("treasury unavailable"))
        ),
        _family_covariance=SimpleNamespace(
            penalties=lambda: (_ for _ in ()).throw(RuntimeError("covariance unavailable"))
        ),
    )

    svc = StateSummaryService()

    assert svc.endpoint_universe(runtime) == {
        "read": {},
        "public": {},
        "protected": {},
        "private": {},
    }
    assert svc.execution_live(runtime) == {"items": []}
    assert svc.route_quality(runtime) == {"items": []}
    assert svc.drawdown(runtime)["drawdownPct"] == 0.0
    assert svc.kill_switch(runtime) == {"metrics": {}, "suppressions": {}, "history": []}
    assert svc.risk_memory(runtime) == {"failures": {}}
    assert svc.path_diversity(runtime) == {"paths": []}
    assert svc.edge_learning(runtime)["items"] == []
    assert svc.rpc_preferences(runtime)["configured"] is False
    assert svc.agent_attribution(runtime) == {"agents": []}
    assert svc.analytics(runtime)["reason_code"] == "analytics_service_unavailable"
    assert svc.capital_summary(runtime)["reason_code"] == "capital_summary_unavailable"
    assert svc.capital_truth_state(runtime)["reason_code"] == "capital_truth_service_unavailable"
    assert svc.capital_explain(runtime)["reason_code"] == "capital_explanation_unavailable"
    assert svc.replay_state(runtime) == {}
    assert svc.pnl_state(runtime) == {}
    assert (
        svc.service_health(runtime)["telemetry"]["reason_code"] == "telemetry_service_unavailable"
    )
    assert svc.launch(runtime)["reason_code"] == "launch_service_unavailable"
    assert (
        svc.launch(runtime)["familyHardening"]["reason_code"]
        == "family_hardening_service_unavailable"
    )
    assert (
        svc.launch(runtime)["familyHardening"]["recovery_status"]
        == "family_hardening_restore_required"
    )
    assert svc.launch(runtime)["familyHardening"]["recovery_reliability_class"] == "unavailable"
    assert svc.capital_engine(runtime) == {
        "capital_engine": {},
        "reinvestment_policy": {},
        "capital_efficiency_metrics": {},
        "drawdown_state": svc.defaults.drawdown,
        "covariance_penalties": {},
    }
