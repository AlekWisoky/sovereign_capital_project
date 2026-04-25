from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _CommandRuntime:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def superstructure_set_directive(self, directive: dict, *, ttl_s: float) -> bool:
        self.calls.append(("directive", {"directive": directive, "ttl_s": ttl_s}))
        return True

    def superstructure_set_risk_multiplier(self, multiplier: float) -> bool:
        self.calls.append(("risk_multiplier", multiplier))
        return True

    def superstructure_set_exploration_cap(self, exploration_cap: float) -> bool:
        self.calls.append(("exploration_cap", exploration_cap))
        return True

    def superstructure_approve(self, proposal_id: str, *, ttl_s: float) -> bool:
        self.calls.append(("approve", {"proposal_id": proposal_id, "ttl_s": ttl_s}))
        return True

    def superstructure_force_safe_mode(self, *, ttl_s: float, reason: str) -> bool:
        self.calls.append(("force_safe_mode", {"ttl_s": ttl_s, "reason": reason}))
        return True


def test_command_routes_reject_unknown_fields_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    rejected = client.post(
        "/api/command/force_safe_mode",
        json={"ttl_s": 45, "reason": "stress", "unexpected": True},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert rejected["ok"] is False
    assert rejected["status"] == "invalid"
    assert rejected["reason_code"] == "unknown_request_fields"
    assert rejected["details"]["fields"] == ["unexpected"]
    assert runtime.calls == []


def test_command_set_directive_validates_mapping_and_ttl_before_runtime_call(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    invalid_mapping = client.post(
        "/api/command/directive",
        json={"directive": "not-a-mapping"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert invalid_mapping["ok"] is False
    assert invalid_mapping["status"] == "invalid"
    assert invalid_mapping["reason_code"] == "invalid_mapping_value"
    assert invalid_mapping["details"]["field"] == "directive"
    assert runtime.calls == []

    empty_payload = client.post(
        "/api/command/directive",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert empty_payload["ok"] is False
    assert empty_payload["status"] == "invalid"
    assert empty_payload["reason_code"] == "empty_command_payload"
    assert empty_payload["details"]["required_any_of"] == ["directive", "payload"]
    assert runtime.calls == []

    null_mapping = client.post(
        "/api/command/directive",
        json={"directive": None},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert null_mapping["ok"] is False
    assert null_mapping["status"] == "invalid"
    assert null_mapping["reason_code"] == "invalid_mapping_value"
    assert null_mapping["details"]["field"] == "directive"
    assert runtime.calls == []

    invalid_ttl = client.post(
        "/api/command/directive",
        json={"directive": {"mode": "observe"}, "ttl_s": "later"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert invalid_ttl["ok"] is False
    assert invalid_ttl["status"] == "invalid"
    assert invalid_ttl["reason_code"] == "invalid_float_value"
    assert invalid_ttl["details"]["field"] == "ttl_s"
    assert runtime.calls == []

    accepted = client.post(
        "/api/command/directive",
        json={"payload": {"mode": "observe"}, "ttl_s": "120.5"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert accepted == {"ok": True}
    assert runtime.calls == [
        ("directive", {"directive": {"mode": "observe"}, "ttl_s": 120.5})
    ]


def test_command_numeric_routes_use_canonical_float_validation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    risk = client.post(
        "/api/command/risk_multiplier",
        json={"risk_multiplier": "1.25"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert risk == {"ok": True}

    empty_risk = client.post(
        "/api/command/risk_multiplier",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert empty_risk["ok"] is False
    assert empty_risk["status"] == "invalid"
    assert empty_risk["reason_code"] == "empty_command_payload"
    assert runtime.calls == [("risk_multiplier", 1.25)]

    exploration = client.post(
        "/api/command/exploration_cap",
        json={"exploration_cap": False},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert exploration["ok"] is False
    assert exploration["status"] == "invalid"
    assert exploration["reason_code"] == "invalid_float_value"
    assert runtime.calls == [("risk_multiplier", 1.25)]

    empty_exploration = client.post(
        "/api/command/exploration_cap",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert empty_exploration["ok"] is False
    assert empty_exploration["status"] == "invalid"
    assert empty_exploration["reason_code"] == "empty_command_payload"
    assert runtime.calls == [("risk_multiplier", 1.25)]


def test_command_approve_and_force_safe_mode_validate_ttl_before_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _CommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    approve = client.post(
        "/api/command/approve",
        json={"proposal_id": "p-1", "ttl_s": "bad"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert approve["ok"] is False
    assert approve["status"] == "invalid"
    assert approve["reason_code"] == "invalid_float_value"
    assert runtime.calls == []

    missing_proposal = client.post(
        "/api/command/approve",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert missing_proposal["ok"] is False
    assert missing_proposal["status"] == "invalid"
    assert missing_proposal["reason_code"] == "missing_proposal_id"
    assert runtime.calls == []

    blank_proposal = client.post(
        "/api/command/approve",
        json={"proposal_id": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert blank_proposal["ok"] is False
    assert blank_proposal["status"] == "invalid"
    assert blank_proposal["reason_code"] == "invalid_string_value"
    assert blank_proposal["details"]["field"] == "proposal_id"
    assert runtime.calls == []

    safe_mode = client.post(
        "/api/command/force_safe_mode",
        json={"ttl_s": 30, "reason": "operator"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert safe_mode == {"ok": True}
    assert runtime.calls == [
        ("force_safe_mode", {"ttl_s": 30.0, "reason": "operator"})
    ]

    empty_safe_mode = client.post(
        "/api/command/force_safe_mode",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert empty_safe_mode["ok"] is False
    assert empty_safe_mode["status"] == "invalid"
    assert empty_safe_mode["reason_code"] == "empty_command_payload"

    blank_reason = client.post(
        "/api/command/force_safe_mode",
        json={"reason": "   "},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert blank_reason["ok"] is False
    assert blank_reason["status"] == "invalid"
    assert blank_reason["reason_code"] == "invalid_string_value"
    assert blank_reason["details"]["field"] == "reason"
    assert runtime.calls == [
        ("force_safe_mode", {"ttl_s": 30.0, "reason": "operator"})
    ]
