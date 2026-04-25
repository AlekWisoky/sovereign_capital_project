from __future__ import annotations

from collections import Counter

from fastapi.testclient import TestClient

from victor_ai_bot.api import router as api_router
from victor_ai_bot.server import app


WITHDRAW_ROUTES = {
    ("GET", "/api/withdraw/config"),
    ("POST", "/api/withdraw/convert/prepare"),
    ("POST", "/api/withdraw/convert/quote"),
    ("POST", "/api/withdraw/convert/execute"),
    ("POST", "/api/withdraw/prepare"),
    ("POST", "/api/withdraw/execute"),
}


def test_api_shell_excludes_routes_owned_by_withdraw_module():
    mounted = set()
    for route in getattr(api_router, "routes", []) or []:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        for method in methods:
            mounted.add((method, path))
    assert mounted.isdisjoint(WITHDRAW_ROUTES)


def test_public_app_mounts_single_copy_of_each_withdraw_route():
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
    for key in WITHDRAW_ROUTES:
        assert counts[key] == 1
        assert modules[key] == ["victor_ai_bot.api_routes.withdraw_routes"]



def test_withdraw_config_route_emits_summary_contract():
    client = TestClient(app)
    resp = client.get("/api/withdraw/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summaryContract"]["truthFamily"] == "withdraw_config"
    assert body["summaryContract"]["readModel"] == "withdraw_config_projection_v1"
