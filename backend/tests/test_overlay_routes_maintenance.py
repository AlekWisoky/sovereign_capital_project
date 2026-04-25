from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
import victor_ai_bot.api_routes.overlay_routes as overlay_routes


class _OverlayRuntime:
    def __init__(self):
        self.calls = []
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="mainnet"))

    def fioa_state(self):
        return {"ok": True, "enabled": True, "mode": "strict"}

    def fioa_audit_tail(self, *, limit: int):
        self.calls.append(("fioa_audit_tail", limit))
        return {"ok": True, "items": [{"limit": limit}]}

    def fioa_governance_report(self, *, limit_audit: int):
        self.calls.append(("fioa_governance_report", limit_audit))
        return {"ok": True, "report": {"limit": limit_audit}}

    def fioa_restrict_agent(self, agent_id: str, *, reason: str):
        self.calls.append(("fioa_restrict_agent", agent_id, reason))
        return True

    def fioa_resume_agent(self, agent_id: str):
        self.calls.append(("fioa_resume_agent", agent_id))
        return True

    def fioa_set_safe_mode(self, on: bool, *, ttl_s: float, reason: str):
        self.calls.append(("fioa_set_safe_mode", on, ttl_s, reason))
        return True

    def narrative_state(self):
        return {"ok": True, "enabled": True, "level": "STANDARD"}

    def narrative_history(self, *, limit: int):
        self.calls.append(("narrative_history", limit))
        return {"ok": True, "items": [{"limit": limit}]}

    def narrative_report(self, *, limit: int):
        self.calls.append(("narrative_report", limit))
        return {"ok": True, "report": f"limit={limit}"}

    def narrative_set_level(self, level: str):
        self.calls.append(("narrative_set_level", level))
        return {"ok": True, "level": level}

    async def narrative_query(self, *, agent_id: str, query_text: str, data_level: str):
        self.calls.append(("narrative_query", agent_id, query_text, data_level))
        return {"ok": True, "agent": agent_id, "query": query_text, "dataLevel": data_level}

    async def narrative_insights(self):
        self.calls.append(("narrative_insights",))
        return {"ok": True, "insights": [{"kind": "summary"}]}


class _ChainRuntime:
    def __init__(self, fioa_mode: str, narrative_level: str):
        self._fioa_mode = fioa_mode
        self._narrative_level = narrative_level

    def fioa_state(self):
        return {"ok": True, "enabled": True, "mode": self._fioa_mode}

    def narrative_state(self):
        return {"ok": True, "enabled": True, "level": self._narrative_level}


class _FakeMultiRuntimeBundle:
    def __init__(self):
        self._active_chain = "base"
        self._runtimes = {
            "base": _ChainRuntime("strict", "STANDARD"),
            "arbitrum": _ChainRuntime("observe", "VERBOSE"),
        }



def test_overlay_routes_use_canonical_module(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    assert client.get("/api/fioa/state").json()["mode"] == "strict"
    assert client.get("/api/narrative/state").json()["level"] == "STANDARD"

    audit = client.get("/api/fioa/audit?limit=11", headers={"X-Admin-Key": "secret"})
    report = client.get("/api/fioa/report?limit_audit=7", headers={"X-Admin-Key": "secret"})
    restrict_resp = client.post(
        "/api/fioa/agent/restrict",
        json={"agent_id": "agent-1", "reason": "policy"},
        headers={"X-Admin-Key": "secret"},
    )
    resume_resp = client.post(
        "/api/fioa/agent/resume",
        json={"agent_id": "agent-1"},
        headers={"X-Admin-Key": "secret"},
    )
    safe_mode_resp = client.post(
        "/api/fioa/safe_mode",
        json={"on": True, "ttl_s": 45, "reason": "stress"},
        headers={"X-Admin-Key": "secret"},
    )
    history = client.get("/api/narrative/history?limit=8", headers={"X-Admin-Key": "secret"})
    report_narrative = client.get("/api/narrative/report?limit=5", headers={"X-Admin-Key": "secret"})
    set_level = client.post(
        "/api/narrative/explanation_level",
        json={"level": "VERBOSE"},
        headers={"X-Admin-Key": "secret"},
    )
    query = client.post(
        "/api/narrative/query",
        json={"query": "status", "agent_id": "ops", "data_level": "PUBLIC"},
        headers={"X-Admin-Key": "secret"},
    )
    insights = client.get("/api/narrative/insights", headers={"X-Admin-Key": "secret"})

    assert audit.json()["items"][0]["limit"] == 11
    assert report.json()["report"]["limit"] == 7
    assert restrict_resp.json()["ok"] is True
    assert resume_resp.json()["ok"] is True
    assert safe_mode_resp.json()["ok"] is True
    assert history.json()["items"][0]["limit"] == 8
    assert report_narrative.json()["report"] == "limit=5"
    assert set_level.json()["level"] == "VERBOSE"
    assert query.json()["agent"] == "ops"
    assert insights.json()["insights"][0]["kind"] == "summary"
    assert runtime.calls == [
        ("fioa_audit_tail", 11),
        ("fioa_governance_report", 7),
        ("fioa_restrict_agent", "agent-1", "policy"),
        ("fioa_resume_agent", "agent-1"),
        ("fioa_set_safe_mode", True, 45.0, "stress"),
        ("narrative_history", 8),
        ("narrative_report", 5),
        ("narrative_set_level", "VERBOSE"),
        ("narrative_query", "ops", "status", "PUBLIC"),
        ("narrative_insights",),
    ]



def test_overlay_multichain_state_routes(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    original = overlay_routes.MultiRuntimeBundle
    overlay_routes.MultiRuntimeBundle = _FakeMultiRuntimeBundle
    try:
        runtime = _FakeMultiRuntimeBundle()
        monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
        client = TestClient(app)

        fioa = client.get("/api/multichain/fioa/state", headers={"X-Admin-Key": "secret"})
        narrative = client.get(
            "/api/multichain/narrative/state", headers={"X-Admin-Key": "secret"}
        )

        assert fioa.json()["active"] == "base"
        assert fioa.json()["chains"]["base"]["mode"] == "strict"
        assert fioa.json()["chains"]["arbitrum"]["mode"] == "observe"
        assert narrative.json()["active"] == "base"
        assert narrative.json()["chains"]["base"]["level"] == "STANDARD"
        assert narrative.json()["chains"]["arbitrum"]["level"] == "VERBOSE"
    finally:
        overlay_routes.MultiRuntimeBundle = original



class _MissingChainRuntime:
    pass


class _MissingOverlayMultiRuntimeBundle:
    def __init__(self):
        self._active_chain = "base"
        self._runtimes = {
            "base": _MissingChainRuntime(),
            "arbitrum": _MissingChainRuntime(),
        }


def test_overlay_multichain_missing_state_routes_are_canonical(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    original = overlay_routes.MultiRuntimeBundle
    overlay_routes.MultiRuntimeBundle = _MissingOverlayMultiRuntimeBundle
    try:
        runtime = _MissingOverlayMultiRuntimeBundle()
        monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
        client = TestClient(app)

        fioa = client.get("/api/multichain/fioa/state", headers={"X-Admin-Key": "secret"}).json()
        narrative = client.get(
            "/api/multichain/narrative/state", headers={"X-Admin-Key": "secret"}
        ).json()

        assert fioa["chains"]["base"]["ok"] is False
        assert fioa["chains"]["base"]["status"] == "unavailable"
        assert fioa["chains"]["base"]["reason_code"] == "unavailable"

        assert narrative["ok"] is True
        assert narrative["chains"]["base"]["ok"] is False
        assert narrative["chains"]["base"]["status"] == "unavailable"
        assert narrative["chains"]["base"]["reason_code"] == "unavailable"
    finally:
        overlay_routes.MultiRuntimeBundle = original


class _OverlayUnavailableRuntime:
    pass


def test_overlay_route_unavailable_defaults_are_canonical_and_explicit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    fioa = client.get("/api/fioa/state").json()
    narrative = client.get("/api/narrative/state").json()
    report = client.get("/api/fioa/report", headers={"X-Admin-Key": "secret"}).json()
    explain = client.post(
        "/api/narrative/explanation_level",
        json={"level": "VERBOSE"},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert fioa["ok"] is False
    assert fioa["enabled"] is False
    assert fioa["reason"] == "unavailable"
    assert fioa["status"] == "unavailable"
    assert fioa["reason_code"] == "unavailable"

    assert narrative["ok"] is False
    assert narrative["enabled"] is False
    assert narrative["reason"] == "unavailable"
    assert narrative["status"] == "unavailable"
    assert narrative["reason_code"] == "unavailable"

    assert report["ok"] is False
    assert report["enabled"] is False
    assert report["reason"] == "unavailable"
    assert report["status"] == "unavailable"
    assert report["reason_code"] == "unavailable"

    assert explain["ok"] is False
    assert explain["error"] == "unavailable"
    assert explain["status"] == "unavailable"
    assert explain["reason_code"] == "unavailable"



def test_fioa_safe_mode_uses_canonical_boolean_parsing(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    accepted = client.post(
        "/api/fioa/safe_mode",
        json={"on": "false", "ttl_s": 30, "reason": "clear"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert accepted["ok"] is True
    assert runtime.calls == [("fioa_set_safe_mode", False, 30.0, "clear")]

    rejected = client.post(
        "/api/fioa/safe_mode",
        json={"on": "engage", "ttl_s": 30, "reason": "clear"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert rejected["ok"] is False
    assert rejected["status"] == "invalid"
    assert rejected["reason_code"] == "invalid_boolean_value"
    assert rejected["details"]["field"] == "on"
    assert runtime.calls == [("fioa_set_safe_mode", False, 30.0, "clear")]


def test_fioa_safe_mode_ttl_validation_and_unknown_fields(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    zero_ttl = client.post(
        "/api/fioa/safe_mode",
        json={"on": True, "ttl_s": 0, "reason": "expire_now"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert zero_ttl["ok"] is True
    assert runtime.calls == [("fioa_set_safe_mode", True, 0.0, "expire_now")]

    invalid_ttl = client.post(
        "/api/fioa/safe_mode",
        json={"on": True, "ttl_s": "later", "reason": "expire_now"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert invalid_ttl["ok"] is False
    assert invalid_ttl["status"] == "invalid"
    assert invalid_ttl["reason_code"] == "invalid_float_value"
    assert invalid_ttl["details"]["field"] == "ttl_s"
    assert runtime.calls == [("fioa_set_safe_mode", True, 0.0, "expire_now")]

    unknown = client.post(
        "/api/fioa/safe_mode",
        json={"on": True, "ttl_s": 10, "reason": "expire_now", "mode": "strict"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert unknown["ok"] is False
    assert unknown["status"] == "invalid"
    assert unknown["reason_code"] == "unknown_request_fields"
    assert unknown["details"]["fields"] == ["mode"]
    assert runtime.calls == [("fioa_set_safe_mode", True, 0.0, "expire_now")]


def test_overlay_mutation_routes_reject_unknown_fields(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    restrict_resp = client.post(
        "/api/fioa/agent/restrict",
        json={"agent_id": "agent-1", "reason": "policy", "scope": "all"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert restrict_resp["ok"] is False
    assert restrict_resp["reason_code"] == "unknown_request_fields"

    resume_resp = client.post(
        "/api/fioa/agent/resume",
        json={"agent_id": "agent-1", "reason": "policy"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert resume_resp["ok"] is False
    assert resume_resp["reason_code"] == "unknown_request_fields"

    explain_resp = client.post(
        "/api/narrative/explanation_level",
        json={"level": "VERBOSE", "ttl_s": 60},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert explain_resp["ok"] is False
    assert explain_resp["reason_code"] == "unknown_request_fields"

    assert runtime.calls == []


def test_overlay_mutation_routes_require_explicit_operator_intent(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OverlayRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    safe_mode_empty = client.post(
        "/api/fioa/safe_mode",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert safe_mode_empty["ok"] is False
    assert safe_mode_empty["status"] == "invalid"
    assert safe_mode_empty["reason_code"] == "missing_safe_mode_toggle"
    assert safe_mode_empty["details"]["field"] == "on"

    safe_mode_blank_reason = client.post(
        "/api/fioa/safe_mode",
        json={"on": True, "reason": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert safe_mode_blank_reason["ok"] is False
    assert safe_mode_blank_reason["status"] == "invalid"
    assert safe_mode_blank_reason["reason_code"] == "invalid_string_value"
    assert safe_mode_blank_reason["details"]["field"] == "reason"

    level_empty = client.post(
        "/api/narrative/explanation_level",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert level_empty["ok"] is False
    assert level_empty["status"] == "invalid"
    assert level_empty["reason_code"] == "missing_level"
    assert level_empty["details"]["field"] == "level"

    level_blank = client.post(
        "/api/narrative/explanation_level",
        json={"level": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert level_blank["ok"] is False
    assert level_blank["status"] == "invalid"
    assert level_blank["reason_code"] == "invalid_string_value"
    assert level_blank["details"]["field"] == "level"

    restrict_missing = client.post(
        "/api/fioa/agent/restrict",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert restrict_missing["ok"] is False
    assert restrict_missing["status"] == "invalid"
    assert restrict_missing["reason_code"] == "missing_agent_id"
    assert restrict_missing["details"]["field"] == "agent_id"

    resume_blank = client.post(
        "/api/fioa/agent/resume",
        json={"agent_id": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert resume_blank["ok"] is False
    assert resume_blank["status"] == "invalid"
    assert resume_blank["reason_code"] == "invalid_string_value"
    assert resume_blank["details"]["field"] == "agent_id"

    assert runtime.calls == []
