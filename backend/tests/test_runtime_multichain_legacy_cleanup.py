from fastapi.testclient import TestClient

from victor_ai_bot.api import router as public_api_router
from victor_ai_bot.api_legacy import router as legacy_router
from victor_ai_bot.api_routes.multichain_routes import router as multichain_router
from victor_ai_bot.api_routes.runtime_routes import router as runtime_router
from victor_ai_bot.server import app


RUNTIME_ROUTE_PAIRS = {
    ("GET", "/health"),
    ("GET", "/api/deploy/info"),
    ("GET", "/api/state"),
    ("GET", "/api/brain/state"),
    ("POST", "/api/runtime/start"),
    ("POST", "/api/runtime/stop"),
    ("POST", "/api/settings"),
}

MULTICHAIN_ROUTE_PAIRS = {
    ("GET", "/api/multichain/chains"),
    ("POST", "/api/multichain/select"),
    ("GET", "/api/multichain/state"),
    ("GET", "/api/multichain/summary"),
    ("POST", "/api/multichain/settings"),
}


def _pairs(router):
    out = set()
    for route in getattr(router, "routes", []):
        path = str(getattr(route, "path", "") or "")
        for method in set(getattr(route, "methods", []) or []):
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.add((str(method).upper(), path))
    return out



def test_runtime_and_multichain_routes_are_no_longer_owned_by_legacy_router():
    legacy_pairs = _pairs(legacy_router)
    runtime_pairs = _pairs(runtime_router)
    multichain_pairs = _pairs(multichain_router)
    public_pairs = _pairs(public_api_router)

    for pair in RUNTIME_ROUTE_PAIRS | MULTICHAIN_ROUTE_PAIRS:
        assert pair not in legacy_pairs
        assert pair not in public_pairs

    for pair in RUNTIME_ROUTE_PAIRS:
        assert pair in runtime_pairs

    for pair in MULTICHAIN_ROUTE_PAIRS:
        assert pair in multichain_pairs



def test_runtime_and_multichain_live_paths_still_resolve_through_canonical_routers():
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    deploy = client.get("/api/deploy/info")
    assert deploy.status_code == 200
    deploy_body = deploy.json()
    assert deploy_body["ok"] is True
    assert deploy_body["brand"]["name"] == "x∆v"

    chains = client.get("/api/multichain/chains")
    assert chains.status_code == 200
    chains_body = chains.json()
    assert chains_body["ok"] is True
    assert "active" in chains_body
    assert "chains" in chains_body
