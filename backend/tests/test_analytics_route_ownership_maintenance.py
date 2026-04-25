from victor_ai_bot.api_routes.analytics_routes import router as analytics_router
from victor_ai_bot.api_routes.system_routes import router as system_router


def _paths(router):
    return {getattr(route, "path", "") for route in getattr(router, "routes", [])}


def test_analytics_routes_live_on_dedicated_router_without_path_drift():
    analytics_paths = _paths(analytics_router)
    system_paths = _paths(system_router)

    expected = {
        "/api/analytics/state",
        "/api/analytics/datasets/{name}",
        "/api/analytics/dashboards",
        "/api/analytics/ask",
        "/api/analytics/scenario",
    }

    assert expected <= analytics_paths
    assert expected.isdisjoint(system_paths)
