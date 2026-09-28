from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.api import get_runtime
from victor_ai_bot.api_routes import telemetry
from victor_ai_bot.runtime import MultiRuntimeBundle


def test_telemetry_routes_use_canonical_active_runtime_resolver():
    active_runtime = object.__new__(object)
    bundle = object.__new__(MultiRuntimeBundle)
    bundle._active_chain = "ethereum"
    bundle._runtimes = {"ethereum": active_runtime, "base": object()}

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=bundle)))

    assert telemetry.get_runtime(request) is active_runtime
    assert telemetry.get_runtime is get_runtime
