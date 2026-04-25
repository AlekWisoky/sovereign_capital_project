import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _AuxRuntime:
    def __init__(self):
        self.calls = []

    def unified_state(self):
        return {"ok": True, "enabled": True, "source": "unified"}

    def spread_opportunities(self):
        return {"ok": True, "count": 1, "opps": [{"routeId": "r1"}]}

    def orchestrator_state(self):
        return {"ok": True, "enabled": True, "name": "orch"}

    def consensus_state(self):
        return {"ok": True, "last": {"block": 123}}

    def behaveagent_state(self):
        return {"ok": True, "enabled": True, "agent": "behave"}

    def treasury_state(self):
        return {"ok": True, "enabled": True, "allocator": "treasury"}

    def governance_layer_state(self):
        return {"ok": True, "enabled": True, "threat": {"level": "low"}}

    def blockspace_state(self):
        return {"ok": True, "enabled": True, "mode": "private"}

    def agent_hub_state(self):
        return {"ok": True, "state": {"agents": 2}}

    def quicksight_state(self):
        return {"ok": True, "enabled": True}

    def quicksight_dataset(self, name: str):
        return {"ok": True, "dataset": str(name), "rows": [{"id": 1}]}

    def quicksight_dashboards(self):
        return {"ok": True, "dashboards": [{"name": "ops"}]}

    def quicksight_ask(self, *, question: str, role: str, token: str):
        self.calls.append(("ask", question, role, token))
        return {"ok": True, "question": question, "role": role, "token": token}

    def quicksight_scenario(self, *, params: dict, role: str, token: str):
        self.calls.append(("scenario", params, role, token))
        return {"ok": True, "params": dict(params or {}), "role": role, "token": token}


def test_new_system_and_admin_routes_smoke(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    client = TestClient(app)
    r = client.get("/api/system/summary")
    assert r.status_code == 200
    rbody = r.json()
    assert "auto_trade_recovery" in rbody
    assert "auto_trade_gate" in rbody
    quality = client.get("/api/system/execution/quality")
    assert quality.status_code == 200
    qbody = quality.json()
    assert "endpoint_quality" in qbody
    assert "kill_switch" in qbody
    assert "auto_trade_recovery" in qbody
    assert "auto_trade_gate" in qbody
    denied = client.get("/api/admin/capabilities")
    assert denied.status_code == 401
    allowed = client.get("/api/admin/capabilities", headers={"X-Admin-Key": "secret"})
    assert allowed.status_code == 200


def test_security_audit_route_requires_admin(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    client = TestClient(app)
    denied = client.get("/api/system/security/audit")
    assert denied.status_code == 401
    allowed = client.get("/api/system/security/audit", headers={"X-Admin-Key": "secret"})
    assert allowed.status_code == 200


def test_rpc_preferences_route_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    denied_write = client.post("/api/system/rpc/preferences", json={"read": ["https://r1"]})
    denied_read = client.get("/api/system/rpc/preferences")
    assert denied_write.status_code == 401
    assert denied_read.status_code == 401

    saved = client.post(
        "/api/system/rpc/preferences",
        json={
            "read": [" https://r1 ", "https://r1"],
            "send": ["https://s1"],
            "private": ["https://p1"],
        },
        headers={"X-Admin-Key": "secret"},
    )
    assert saved.status_code == 200
    assert saved.json()["preferences"]["read"] == ["https://r1"]

    partial = client.post(
        "/api/system/rpc/preferences",
        json={"read": ["https://r2"]},
        headers={"X-Admin-Key": "secret"},
    )
    assert partial.status_code == 200
    partial_body = partial.json()
    assert partial_body["preferences"]["read"] == ["https://r2"]
    assert partial_body["preferences"]["send"] == ["https://s1"]
    assert partial_body["preferences"]["private"] == ["https://p1"]

    invalid = client.post(
        "/api/system/rpc/preferences",
        json={"send": "https://not-a-list"},
        headers={"X-Admin-Key": "secret"},
    )
    assert invalid.status_code == 200
    invalid_body = invalid.json()
    assert invalid_body["ok"] is False
    assert invalid_body["status"] == "invalid"
    assert invalid_body["reason_code"] == "invalid_rpc_preference_list"

    snap = client.get("/api/system/rpc/preferences", headers={"X-Admin-Key": "secret"})
    assert snap.status_code == 200
    body = snap.json()
    assert body["configured"] is True
    assert body["read"] == ["https://r2"]
    assert body["send"] == ["https://s1"]
    assert body["private"] == ["https://p1"]


def test_risk_live_state_route(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    client = TestClient(app)
    resp = client.get("/api/risk/live-state")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "drawdown" in body
    assert "kill_switch" in body
    assert "auto_trade_recovery" in body
    assert "auto_trade_gate" in body


def test_auxiliary_state_and_analytics_routes_use_canonical_modules(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _AuxRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    unified = client.get("/api/unified/state").json()
    spread = client.get("/api/spread/opportunities").json()
    orchestrator = client.get("/api/orchestrator/state").json()
    consensus = client.get("/api/consensus/state").json()
    behaveagent = client.get("/api/behaveagent/state").json()
    treasury = client.get("/api/treasury/state").json()
    governance = client.get("/api/governance/state").json()
    blockspace = client.get("/api/blockspace/state").json()
    agenthub = client.get("/api/agenthub/state").json()

    for body in (
        unified,
        spread,
        orchestrator,
        consensus,
        behaveagent,
        governance,
        blockspace,
        agenthub,
    ):
        assert "auto_trade_recovery" in body
        assert "auto_trade_gate" in body

    assert unified["source"] == "unified"
    assert spread["count"] == 1
    assert orchestrator["name"] == "orch"
    assert consensus["last"]["block"] == 123
    assert behaveagent["agent"] == "behave"
    assert treasury["allocator"] == "treasury"
    assert governance["threat"]["level"] == "low"
    assert blockspace["mode"] == "private"
    assert agenthub["state"]["agents"] == 2

    state = client.get("/api/analytics/state")
    dataset = client.get("/api/analytics/datasets/operators")
    dashboards = client.get("/api/analytics/dashboards")
    assert state.json()["enabled"] is True
    assert dataset.json()["dataset"] == "operators"
    assert dashboards.json()["dashboards"][0]["name"] == "ops"

    ask = client.post(
        "/api/analytics/ask",
        json={"question": "status?"},
        headers={"X-Role": "ANALYST", "X-Role-Token": "tok-1"},
    )
    scenario = client.post(
        "/api/analytics/scenario",
        json={"stress": "gas_5x"},
        headers={"X-Role": "RISK_MANAGER", "X-Role-Token": "tok-2"},
    )
    assert ask.json()["role"] == "ANALYST"
    assert ask.json()["token"] == "tok-1"
    assert scenario.json()["params"]["stress"] == "gas_5x"
    assert runtime.calls == [
        ("ask", "status?", "ANALYST", "tok-1"),
        ("scenario", {"stress": "gas_5x"}, "RISK_MANAGER", "tok-2"),
    ]


class _SystemControlSurfaceRuntime:
    def service_health_state(self):
        return {
            "admission": {
                "ok": False,
                "status": "unavailable",
                "reason_code": "admission_service_unavailable",
                "reason": "admission_service_unavailable",
            }
        }

    def capital_truth_state(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "capital_truth_service_unavailable",
            "reason": "capital_truth_service_unavailable",
        }

    def family_hardening_state(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "family_hardening_service_unavailable",
            "reason": "family_hardening_service_unavailable",
            "items": [],
        }

    def capital_explain(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "capital_explanation_unavailable",
            "text": "capital_explanation_unavailable",
            "facts": {},
            "causal": {},
        }


def test_system_control_surface_unavailable_defaults_remain_backward_compatible(monkeypatch):
    runtime = _SystemControlSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/system/summary").json()
    services = client.get("/api/system/services").json()
    capital_truth = client.get("/api/system/capital/truth").json()
    family_hardening = client.get("/api/system/family-hardening").json()
    capital_explain = client.get("/api/system/capital/explain").json()

    assert summary["ok"] is False
    assert summary["status"] == "unavailable"
    assert summary["reason_code"] == "analytics_service_unavailable"
    assert summary["error"] == "analytics_service_unavailable"
    assert summary["services"]["admission"]["reason_code"] == "admission_service_unavailable"
    assert summary["capitalTruth"]["reason_code"] == "capital_truth_service_unavailable"
    assert summary["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"

    assert services["admission"]["reason_code"] == "admission_service_unavailable"

    assert capital_truth["status"] == "unavailable"
    assert capital_truth["reason_code"] == "capital_truth_service_unavailable"

    assert family_hardening["status"] == "unavailable"
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["items"] == []

    assert capital_explain["status"] == "unavailable"
    assert capital_explain["reason_code"] == "capital_explanation_unavailable"
    assert capital_explain["text"] == "capital_explanation_unavailable"


class _MinimalSystemControlSurfaceRuntime:
    pass


def test_system_control_surface_route_fallbacks_remain_backward_compatible(monkeypatch):
    runtime = _MinimalSystemControlSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    services = client.get("/api/system/services").json()
    capital_truth = client.get("/api/system/capital/truth").json()
    family_hardening = client.get("/api/system/family-hardening").json()
    capital_explain = client.get("/api/system/capital/explain").json()

    assert services["status"] == "unavailable"
    assert services["reason_code"] == "service_health_unavailable"
    assert services["reason"] == "service_health_unavailable"

    assert capital_truth["status"] == "unavailable"
    assert capital_truth["reason_code"] == "capital_truth_unavailable"
    assert capital_truth["reason"] == "capital_truth_unavailable"

    assert family_hardening["status"] == "unavailable"
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["reason"] == "family_hardening_service_unavailable"
    assert family_hardening["items"] == []

    assert capital_explain["status"] == "unavailable"
    assert capital_explain["reason_code"] == "capital_explanation_unavailable"
    assert capital_explain["text"] == "capital_explanation_unavailable"
    assert capital_explain["facts"] == {}
    assert capital_explain["causal"] == {}


class _CommandCenterRouteRuntime:
    def __init__(self):
        from types import SimpleNamespace

        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=True,
                control_mode="view_only",
                sandbox_only=False,
                allocations_frozen=False,
                defensive_mode=False,
                reduce_exposure_half=False,
                governance_enabled=True,
                mutation_enabled=True,
                aggression_mode="balanced",
                full_system_enabled=False,
                force_send_mode="",
                force_gas_mode="",
            ),
            audit=SimpleNamespace(tail=lambda limit=200: []),
        )
        self.calls = []

        def _set_controls(patch, actor="operator", reason=""):
            for key, value in patch.items():
                setattr(self._cc.controls, key, value)
            return {"ok": True, "patch": dict(patch), "reason": reason}

        self._cc.set_controls = _set_controls

    def set_settings(self, **kwargs):
        self.calls.append(kwargs)


def test_command_center_control_route_accepts_documented_top_level_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandCenterRouteRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/commandcenter/control",
        json={"controlMode": "assist", "reason": "resume in assist"},
        headers={"X-Admin-Key": "secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["patch"]["control_mode"] == "assist"
    assert runtime._cc.controls.paused is False
    assert runtime.calls == [{"auto_trading": True}]


def test_command_center_control_route_rejects_reason_only_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandCenterRouteRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/commandcenter/control",
        json={"reason": "missing patch"},
        headers={"X-Admin-Key": "secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["reason_code"] == "empty_control_patch"


class _HealthyAnalyticsService:
    def system_summary(self, runtime):
        return {"ok": True, "telemetry": {"families": []}}


class _AnalyticsSummaryRuntime:
    def __init__(self):
        self._analytics_service = _HealthyAnalyticsService()

    def service_health_state(self):
        return {
            "admission": {
                "ok": True,
                "status": "ok",
                "reason_code": "ok",
                "reason": "ok",
            }
        }

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["internal_prime_journal_borrowed_mismatch"],
        }

    def family_hardening_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "reason_code": "family_hardening_rebuild_required",
            "items": [{"family": "funding_arb", "status": "fragile"}],
        }


def test_system_summary_surfaces_capital_truth_and_family_hardening_even_when_analytics_service_is_available(
    monkeypatch,
):
    runtime = _AnalyticsSummaryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/system/summary").json()

    assert summary["ok"] is True
    assert summary["services"]["admission"]["reason_code"] == "ok"
    assert summary["capitalTruth"]["status"] == "degraded"
    assert summary["capitalTruth"]["status_reasons"] == ["internal_prime_journal_borrowed_mismatch"]
    assert summary["familyHardening"]["status"] == "degraded"
    assert summary["familyHardening"]["reason_code"] == "family_hardening_rebuild_required"
    assert summary["familyHardening"]["items"][0]["family"] == "funding_arb"


class _BlockedSystemSummaryRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 5,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "capital_truth",
            "history_stage": "capital_hold",
            "history_reason_code": "capital_truth_unavailable",
            "history_reason_codes": ["capital_truth_unavailable"],
            "history_next_action": "restore_capital_truth",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "capital_truth_unavailable",
            "component_reliability_reason_codes": ["capital_truth_unavailable"],
            "component_reliability_next_action": "restore_capital_truth",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _SystemSummaryRuntimeWithRecovery(_AnalyticsSummaryRuntime):
    def __init__(self):
        super().__init__()
        self._auto_trade_recovery_repo = _BlockedSystemSummaryRecoveryRepo()


def test_system_summary_surfaces_persisted_auto_trade_recovery_gate(monkeypatch):
    runtime = _SystemSummaryRuntimeWithRecovery()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/system/summary").json()

    assert summary["ok"] is True
    assert summary["services"]["admission"]["reason_code"] == "ok"
    assert summary["capitalTruth"]["status"] == "degraded"
    assert summary["auto_trade_recovery"]["blocked"] is True
    assert summary["auto_trade_recovery"]["history_component"] == "capital_truth"
    assert summary["auto_trade_recovery"]["history_reason_code"] == "capital_truth_unavailable"
    assert summary["auto_trade_gate"] == {
        "allowed": False,
        "stage": "capital_hold",
        "reason_code": "capital_truth_unavailable",
        "reason_codes": ["capital_truth_unavailable"],
        "next_action": "restore_capital_truth",
    }


class _BrokenSystemControlSurfaceRuntime:
    def __init__(self):
        self._analytics_service = SimpleNamespace(
            system_summary=lambda runtime: (_ for _ in ()).throw(RuntimeError("analytics failed"))
        )

    def service_health_state(self):
        raise RuntimeError("service health failed")

    def capital_truth_state(self):
        raise RuntimeError("capital truth failed")

    def family_hardening_state(self):
        raise RuntimeError("family hardening failed")

    def capital_explain(self):
        raise RuntimeError("capital explain failed")


def test_system_control_surface_routes_fail_closed_when_runtime_methods_raise(monkeypatch):
    runtime = _BrokenSystemControlSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/system/summary").json()
    services = client.get("/api/system/services").json()
    capital_truth = client.get("/api/system/capital/truth").json()
    family_hardening = client.get("/api/system/family-hardening").json()
    capital_explain = client.get("/api/system/capital/explain").json()

    assert summary["ok"] is False
    assert summary["reason_code"] == "analytics_service_unavailable"
    assert summary["services"]["reason_code"] == "service_health_unavailable"
    assert summary["capitalTruth"]["reason_code"] == "capital_truth_unavailable"
    assert summary["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert summary["familyHardening"]["recovery_status"] == "family_hardening_restore_required"
    assert summary["familyHardening"]["recovery_reliability_class"] == "unavailable"

    assert services["status"] == "unavailable"
    assert services["reason_code"] == "service_health_unavailable"

    assert capital_truth["status"] == "unavailable"
    assert capital_truth["reason_code"] == "capital_truth_unavailable"

    assert family_hardening["status"] == "unavailable"
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["items"] == []
    assert family_hardening["recovery_status"] == "family_hardening_restore_required"
    assert family_hardening["recovery_reliability_class"] == "unavailable"

    assert capital_explain["status"] == "unavailable"
    assert capital_explain["reason_code"] == "capital_explanation_unavailable"
    assert capital_explain["text"] == "capital_explanation_unavailable"
