from __future__ import annotations

"""Sentry bootstrap for the production FastAPI runtime.

Sentry is observability only: it must never become an execution dependency.
When no DSN is configured, initialization is a no-op. When the SDK is absent,
the core runtime can still boot and trade paths are not blocked.
"""

import os
from typing import Any, Dict

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    try:
        value = float(raw) if raw.strip() else float(default)
    except (TypeError, ValueError):
        value = float(default)
    return max(0.0, min(1.0, value))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return bool(default)
    return raw.strip().lower() in _TRUE_VALUES


def sentry_settings() -> Dict[str, Any]:
    """Return sanitized Sentry runtime settings (never includes the DSN)."""
    return {
        "environment": str(
            os.environ.get("SENTRY_ENVIRONMENT")
            or os.environ.get("VICTOR_ENVIRONMENT")
            or "development"
        ).strip(),
        "release": str(
            os.environ.get("SENTRY_RELEASE")
            or os.environ.get("VICTOR_RELEASE")
            or os.environ.get("GITHUB_SHA")
            or ""
        ).strip(),
        "traces_sample_rate": _env_float("SENTRY_TRACES_SAMPLE_RATE", 0.05),
        "profiles_sample_rate": _env_float("SENTRY_PROFILES_SAMPLE_RATE", 0.0),
        "enable_logs": _env_bool("SENTRY_ENABLE_LOGS", False),
    }


def init_sentry() -> bool:
    """Initialize Sentry once, without making it a runtime-critical dependency."""
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    settings = sentry_settings()
    kwargs: Dict[str, Any] = {
        "dsn": dsn,
        "environment": settings["environment"],
        "traces_sample_rate": settings["traces_sample_rate"],
        "profiles_sample_rate": settings["profiles_sample_rate"],
        "send_default_pii": False,
        "enable_logs": settings["enable_logs"],
    }
    if settings["release"]:
        kwargs["release"] = settings["release"]
    sentry_sdk.init(**kwargs)
    return True


def set_sentry_trade_context(
    *,
    decision_id: str = "",
    correlation_id: str = "",
    execution_id: str = "",
    outcome_id: str = "",
    opportunity_id: str = "",
    route_id: str = "",
    sizing_id: str = "",
    action: str = "",
    mode: str = "",
) -> None:
    """Attach safe lifecycle identifiers to the current Sentry scope."""
    try:
        import sentry_sdk
    except ImportError:
        return
    values = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "outcome_id": outcome_id,
        "opportunity_id": opportunity_id,
        "route_id": route_id,
        "sizing_id": sizing_id,
        "action": action,
        "mode": mode,
    }
    for key, value in values.items():
        text = str(value or "").strip()
        if text:
            sentry_sdk.set_tag(key, text)


def capture_runtime_exception(
    error: BaseException, *, context: Dict[str, Any] | None = None
) -> None:
    """Capture a handled runtime exception without exposing sensitive payloads."""
    try:
        import sentry_sdk
    except ImportError:
        return
    with sentry_sdk.new_scope() as scope:
        safe_context = dict(context or {})
        for key in (
            "decision_id",
            "correlation_id",
            "execution_id",
            "outcome_id",
            "opportunity_id",
            "route_id",
            "sizing_id",
            "action",
            "mode",
            "status",
            "reason_code",
        ):
            if key in safe_context and safe_context[key] is not None:
                scope.set_tag(key, str(safe_context[key]))
        sentry_sdk.capture_exception(error)
