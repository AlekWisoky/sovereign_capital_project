from __future__ import annotations

from collections import Counter

from victor_ai_bot.api import router as api_router
from victor_ai_bot.server import app


WITHDRAW_ALL_ROUTES = {
    ("GET", "/api/withdraw/all/state"),
    ("POST", "/api/withdraw/all/config"),
    ("POST", "/api/withdraw/all/preview"),
    ("POST", "/api/withdraw/all/execute"),
}


def test_api_shell_excludes_routes_owned_by_withdraw_all_module():
    mounted = set()
    for route in getattr(api_router, "routes", []) or []:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        for method in methods:
            mounted.add((method, path))
    assert mounted.isdisjoint(WITHDRAW_ALL_ROUTES)


def test_public_app_mounts_single_copy_of_each_withdraw_all_route():
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
    for key in WITHDRAW_ALL_ROUTES:
        assert counts[key] == 1
        assert modules[key] == ["victor_ai_bot.api_routes.withdraw_all_routes"]
