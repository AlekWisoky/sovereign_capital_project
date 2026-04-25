from pathlib import Path

from victor_ai_bot.api import router as api_router
from victor_ai_bot.api_legacy import router as legacy_router
from victor_ai_bot.server import app


def _pairs(router):
    out = set()
    for route in getattr(router, "routes", []) or []:
        path = str(getattr(route, "path", "") or "")
        for method in set(getattr(route, "methods", []) or []):
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.add((str(method).upper(), path))
    return out


def test_api_shell_and_legacy_router_are_both_route_empty():
    assert _pairs(api_router) == set()
    assert _pairs(legacy_router) == set()


def test_server_no_longer_mounts_compatibility_api_shell():
    server_source = (Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'server.py').read_text(
        encoding='utf-8'
    )
    assert 'from .api import router as api_router' not in server_source
    assert 'app.include_router(api_router)' not in server_source


def test_public_app_has_no_routes_owned_by_victor_ai_bot_api_module():
    mounted_modules = {
        str(getattr(getattr(route, 'endpoint', None), '__module__', '') or '')
        for route in app.routes
    }
    assert 'victor_ai_bot.api' not in mounted_modules
