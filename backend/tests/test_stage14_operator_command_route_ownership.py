from __future__ import annotations

from collections import Counter

from victor_ai_bot.api import router as api_router
from fastapi.testclient import TestClient

from victor_ai_bot.server import app


COMMAND_ROUTES = {
    ("GET", "/api/command/state"),
    ("POST", "/api/command/directive"),
    ("POST", "/api/command/risk_multiplier"),
    ("POST", "/api/command/exploration_cap"),
    ("POST", "/api/command/approve"),
    ("POST", "/api/command/force_safe_mode"),
}


def test_api_shell_excludes_routes_owned_by_operator_command_module():
    mounted = set()
    for route in getattr(api_router, "routes", []) or []:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        for method in methods:
            mounted.add((method, path))
    assert mounted.isdisjoint(COMMAND_ROUTES)


def test_public_app_mounts_single_copy_of_each_operator_command_route():
    counts: Counter[tuple[str, str]] = Counter()
    modules: dict[tuple[str, str], list[str]] = {}
    for route in app.routes:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        module = str(getattr(getattr(route, "endpoint", None), "__module__", "") or "")
        for method in methods:
            key = (method, path)
            counts[key] += 1
            modules.setdefault(key, []).append(module)
    for key in COMMAND_ROUTES:
        assert counts[key] == 1
        assert modules[key] == ["victor_ai_bot.api_routes.operator_command_routes"]


class _UnavailableCommandRuntime:
    pass


def test_operator_command_route_unavailable_defaults_are_canonical_and_explicit(monkeypatch):
    runtime = _UnavailableCommandRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    state = client.get("/api/command/state").json()

    assert state["ok"] is False
    assert state["enabled"] is False
    assert state["reason"] == "unavailable"
    assert state["status"] == "unavailable"
    assert state["reason_code"] == "unavailable"
    assert state["auto_trade_recovery"]["blocked"] is False
    assert state["auto_trade_gate"]["allowed"] is True
