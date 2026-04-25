from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
import victor_ai_bot.api_routes.multichain_routes as multichain_routes


class _RuntimeSettingsRuntime:
    def __init__(self):
        self.calls: list[dict[str, object]] = []
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="base"))

    def set_settings(self, **kwargs):
        self.calls.append(dict(kwargs))


class _MultiRuntimeSettingsBundle:
    def __init__(self):
        self._active_chain = "base"
        self._runtimes = {"base": object(), "arbitrum": object()}
        self.calls: list[tuple[str, dict[str, object]]] = []

    def chains(self):
        return list(self._runtimes.keys())

    def set_settings_for(self, chain_name: str, **kwargs):
        self.calls.append((chain_name, dict(kwargs)))
        return chain_name in self._runtimes


def test_runtime_settings_route_canonicalizes_values_without_truthiness_drift(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _RuntimeSettingsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/settings",
        json={
            "auto_trading": "false",
            "gas_mode": "FAST",
            "send_mode": "PRIVATE",
            "auto_reinvest_enabled": "1",
            "reinvest_rate": "25",
            "brain_mode": "AUTO",
            "base_borrow_amount": "7",
            "dry_run": "true",
        },
        headers={"X-Admin-Key": "secret"},
    )

    assert response.json() == {"ok": True}
    assert runtime.calls == [
        {
            "auto_trading": False,
            "gas_mode": "fast",
            "send_mode": "private",
            "auto_reinvest_enabled": True,
            "reinvest_rate": 25,
            "brain_mode": "auto",
            "base_borrow_amount": "7",
            "dry_run": True,
        }
    ]


def test_runtime_settings_route_rejects_invalid_payload_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _RuntimeSettingsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    unknown = client.post(
        "/api/settings",
        json={"auto_trading": True, "unexpected": 1},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert unknown["ok"] is False
    assert unknown["status"] == "invalid"
    assert unknown["reason_code"] == "unknown_request_fields"
    assert runtime.calls == []

    invalid = client.post(
        "/api/settings",
        json={"reinvest_rate": "bad"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert invalid["ok"] is False
    assert invalid["status"] == "invalid"
    assert invalid["reason_code"] == "invalid_integer_value"
    assert runtime.calls == []


def test_multichain_settings_route_validates_and_normalizes_before_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    original = multichain_routes.MultiRuntimeBundle
    multichain_routes.MultiRuntimeBundle = _MultiRuntimeSettingsBundle
    try:
        runtime = _MultiRuntimeSettingsBundle()
        monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
        client = TestClient(app)

        ok = client.post(
            "/api/multichain/settings",
            json={
                "chain": "arbitrum",
                "auto_trading": "false",
                "auto_reinvest_enabled": "true",
                "reinvest_rate": 33,
                "brain_mode": "suggest",
                "dry_run": 1,
            },
            headers={"X-Admin-Key": "secret"},
        ).json()

        assert ok["ok"] is True
        assert runtime.calls == [
            (
                "arbitrum",
                {
                    "auto_trading": False,
                    "auto_reinvest_enabled": True,
                    "reinvest_rate": 33,
                    "brain_mode": "suggest",
                    "dry_run": True,
                },
            )
        ]

        invalid = client.post(
            "/api/multichain/settings",
            json={"chain": "base", "brain_mode": "rl", "extra": True},
            headers={"X-Admin-Key": "secret"},
        ).json()
        assert invalid["ok"] is False
        assert invalid["status"] == "invalid"
        assert invalid["reason_code"] == "unknown_request_fields"
        assert runtime.calls == [
            (
                "arbitrum",
                {
                    "auto_trading": False,
                    "auto_reinvest_enabled": True,
                    "reinvest_rate": 33,
                    "brain_mode": "suggest",
                    "dry_run": True,
                },
            )
        ]
    finally:
        multichain_routes.MultiRuntimeBundle = original


def test_runtime_settings_route_rejects_empty_patch_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _RuntimeSettingsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/settings",
        json={},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert response["ok"] is False
    assert response["status"] == "invalid"
    assert response["reason_code"] == "empty_settings_patch"
    assert runtime.calls == []


def test_multichain_settings_route_rejects_unknown_target_chain_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    original = multichain_routes.MultiRuntimeBundle
    multichain_routes.MultiRuntimeBundle = _MultiRuntimeSettingsBundle
    try:
        runtime = _MultiRuntimeSettingsBundle()
        monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
        client = TestClient(app)

        response = client.post(
            "/api/multichain/settings",
            json={"chain": "optimism", "brain_mode": "suggest"},
            headers={"X-Admin-Key": "secret"},
        ).json()

        assert response["ok"] is False
        assert response["status"] == "invalid"
        assert response["reason_code"] == "unknown_chain"
        assert response["details"] == {"field": "chain", "value": "optimism"}
        assert runtime.calls == []
    finally:
        multichain_routes.MultiRuntimeBundle = original


def test_multichain_settings_route_rejects_mismatched_chain_on_single_runtime_without_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _RuntimeSettingsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.post(
        "/api/multichain/settings",
        json={"chain": "arbitrum", "brain_mode": "suggest"},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert response["ok"] is False
    assert response["status"] == "invalid"
    assert response["reason_code"] == "unknown_chain"
    assert response["details"] == {"field": "chain", "value": "arbitrum"}
    assert runtime.calls == []
