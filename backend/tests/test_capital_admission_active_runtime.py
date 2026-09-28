from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.api import get_runtime
from victor_ai_bot.api_routes import fund_routes, treasury_extra
from victor_ai_bot.runtime import MultiRuntimeBundle


def _request_with_multi_runtime(active_runtime: object):
    bundle = object.__new__(MultiRuntimeBundle)
    bundle._active_chain = "ethereum"
    bundle._runtimes = {"ethereum": active_runtime, "base": object()}
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=bundle)))


def test_fund_routes_use_canonical_active_runtime_resolver():
    active_runtime = object()
    request = _request_with_multi_runtime(active_runtime)

    assert fund_routes.get_runtime(request) is active_runtime
    assert fund_routes.get_runtime is get_runtime


def test_treasury_routes_use_canonical_active_runtime_resolver():
    active_runtime = object()
    request = _request_with_multi_runtime(active_runtime)

    assert treasury_extra.get_runtime(request) is active_runtime
    assert treasury_extra.get_runtime is get_runtime
