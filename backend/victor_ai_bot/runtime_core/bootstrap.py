from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from ..config import AppConfig, load_configs_from_env
from .container import RuntimeContainer, build_runtime_container
from .coordinator import MultiRuntimeBundle, RuntimeBundle

_SAFE_RUNTIME_LIFECYCLE_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError, OSError)


def load_runtime_configs(default_cfg: str) -> List[AppConfig]:
    return load_configs_from_env(default_cfg)


def build_runtime(cfgs: List[AppConfig]):
    if len(cfgs) > 1:
        return MultiRuntimeBundle(cfgs)
    return RuntimeBundle(cfgs[0])


def attach_runtime(app, runtime) -> RuntimeContainer:
    app.state.runtime = runtime  # type: ignore[attr-defined]
    container = build_runtime_container(runtime)
    app.state.runtime_container = container  # type: ignore[attr-defined]
    return container


def _record_runtime_lifecycle(
    app: Any, *, phase: str, status: str, error: Exception | None = None
) -> None:
    payload: Dict[str, Any] = {"status": str(status)}
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)
    state = getattr(app, "state", None)
    if state is None:
        return
    lifecycle = dict(getattr(state, "runtime_lifecycle", {}) or {})
    lifecycle[str(phase)] = payload
    state.runtime_lifecycle = lifecycle  # type: ignore[attr-defined]


def make_runtime_lifespan():
    @asynccontextmanager
    async def lifespan(app):
        autostart_requested = (os.environ.get("VICTOR_AUTOSTART", "") or "").strip() == "1"
        _record_runtime_lifecycle(
            app, phase="autostart", status="enabled" if autostart_requested else "disabled"
        )
        if autostart_requested:
            try:
                app.state.runtime.start()  # type: ignore[attr-defined]
            except _SAFE_RUNTIME_LIFECYCLE_EXCEPTIONS as exc:
                _record_runtime_lifecycle(app, phase="start", status="failed", error=exc)
            else:
                _record_runtime_lifecycle(app, phase="start", status="ok")
        else:
            _record_runtime_lifecycle(app, phase="start", status="skipped")
        yield
        rt = getattr(app.state, "runtime", None)
        if rt is None:
            _record_runtime_lifecycle(app, phase="stop", status="skipped")
            return
        try:
            await rt.stop()  # type: ignore[func-returns-value]
        except _SAFE_RUNTIME_LIFECYCLE_EXCEPTIONS as exc:
            _record_runtime_lifecycle(app, phase="stop", status="failed", error=exc)
        else:
            _record_runtime_lifecycle(app, phase="stop", status="ok")

    return lifespan
