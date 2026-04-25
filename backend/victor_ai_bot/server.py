from __future__ import annotations

"""FastAPI app wiring.

This module is the backend entrypoint used by uvicorn:

  uvicorn victor_ai_bot.server:app

It intentionally keeps imports light and avoids optional-heavy subsystems at
import time so that a missing optional dependency cannot prevent the core bot
from booting.
"""

import logging
import os
from typing import Any, Dict, List, MutableMapping

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api_routes import (
    advanced_router,
    admin_router,
    agents_router,
    command_center_router,
    engine_router,
    evolution_router,
    frontend_router,
    fund_router,
    governance_router,
    superstructure_router,
    ops_router,
    launch_router,
    multichain_router,
    operator_command_router,
    overlay_router,
    intelligence_router,
    rft_router,
    risk_router,
    runtime_router,
    strategies_router,
    system_router,
    telemetry_router,
    treasury_router,
    analytics_router,
    wealth_router,
    withdraw_router,
    withdraw_all_router,
)
from .config import AppConfig
from .config_validation import enforce_or_warn
from .deploy_mode import enforce_public_defaults
from .logging_utils import configure_logging
from .ratelimit import RateLimitMiddleware
from .runtime_core import attach_runtime, build_runtime, load_runtime_configs, make_runtime_lifespan

log = logging.getLogger(__name__)

_OMAR_IMPORT_EXCEPTIONS = (ImportError, ModuleNotFoundError, AttributeError)
_OMAR_RAW_SETTINGS_EXCEPTIONS = (ImportError, ModuleNotFoundError, OSError, UnicodeError, TypeError, ValueError)
_OMAR_ATTACH_EXCEPTIONS = (RuntimeError, AttributeError, TypeError, ValueError)
_PUBLIC_DEFAULTS_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _boot_bucket(ok: bool = True, *, reason: str = "ok") -> Dict[str, Any]:
    return {"ok": bool(ok), "reason": str(reason), "degraded": not bool(ok)}


def _set_boot(bucket: MutableMapping[str, Any], *, ok: bool, reason: str) -> None:
    bucket["ok"] = bool(ok)
    bucket["reason"] = str(reason)
    bucket["degraded"] = not bool(ok)


def _init_boot_status() -> Dict[str, Any]:
    return {
        "public_defaults": _boot_bucket(),
        "config_validation": _boot_bucket(),
        "omar": {"enabled": False, **_boot_bucket(reason="disabled")},
    }


def _cors_allow_origins() -> List[str]:
    raw = os.environ.get("VICTOR_CORS_ALLOW_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if origins:
        return origins
    # Safe local defaults only. Production origins must be supplied explicitly
    # through VICTOR_CORS_ALLOW_ORIGINS when the web app is hosted remotely.
    return [
        "http://localhost:19006",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:19006",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]


def _raw_settings_for_omar(cfg_path: str) -> Dict[str, Any]:
    """Best-effort load of the raw YAML settings dict.

    OMAR integration expects a raw dict-like settings structure. We keep this
    loader dependency-free and tolerant: if anything fails, return {}.
    """

    try:
        import yaml  # local import to keep import graph small

        with open(cfg_path, "r", encoding="utf-8") as f:
            obj = yaml.safe_load(f) or {}
        return obj if isinstance(obj, dict) else {}
    except _OMAR_RAW_SETTINGS_EXCEPTIONS:
        return {}


def _maybe_attach_omar(
    app: FastAPI,
    *,
    cfg_paths: List[str],
    boot_status: MutableMapping[str, Any],
) -> None:
    """Attach OMAR endpoints when explicitly enabled.

    OMAR is experimental/optional. We never let it break core bot boot.

    Enable via:
      export VICTOR_ENABLE_OMAR=1
    """

    omar_status = boot_status.setdefault("omar", {"enabled": False, **_boot_bucket(reason="disabled")})

    if (os.environ.get("VICTOR_ENABLE_OMAR", "") or "").strip() != "1":
        _set_boot(omar_status, ok=True, reason="disabled")
        omar_status["enabled"] = False
        return

    omar_status["enabled"] = True

    try:
        # Lazy imports so optional deps (e.g., numpy) do not break core.
        from victor_ai_bot.omar.api import build_router as build_omar_router
        from victor_ai_bot.omar.integration import make_omar_from_settings
    except _OMAR_IMPORT_EXCEPTIONS as e:  # pragma: no cover
        _set_boot(omar_status, ok=False, reason="import_failed")
        omar_status["error"] = str(e)
        log.warning("OMAR disabled (import failed): %s", e)
        return

    # Keep a single runtime instance (created on first access).
    _omar_runtime: Dict[str, Any] = {"rt": None}

    def get_omar_runtime():
        if _omar_runtime["rt"] is not None:
            return _omar_runtime["rt"]

        # Use the first config path as the canonical settings source.
        path = cfg_paths[0] if cfg_paths else ""
        raw = _raw_settings_for_omar(path) if path else {}
        chain_name = str(
            ((raw.get("chain") or {}) if isinstance(raw, dict) else {}).get("name") or "default"
        )
        _omar_runtime["rt"] = make_omar_from_settings(raw, chain_name=chain_name)
        return _omar_runtime["rt"]

    try:
        app.include_router(build_omar_router(get_omar_runtime))
        _set_boot(omar_status, ok=True, reason="attached")
        log.info("OMAR routes enabled under /api/omar")
    except _OMAR_ATTACH_EXCEPTIONS as e:  # pragma: no cover
        _set_boot(omar_status, ok=False, reason="router_attach_failed")
        omar_status["error"] = str(e)
        log.warning("OMAR disabled (router attach failed): %s", e)


def create_app() -> FastAPI:
    configure_logging()

    lifespan = make_runtime_lifespan()
    app = FastAPI(title="x∆v — Sovereign Capital", lifespan=lifespan)
    boot_status = _init_boot_status()
    app.state.boot_status = boot_status  # type: ignore[attr-defined]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allow_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    # Lightweight in-memory rate limits for expensive endpoints.
    # Safe defaults; configurable via env. Designed to prevent runaway polling.
    app.add_middleware(RateLimitMiddleware)

    # Load config(s)
    default_cfg = os.path.join(os.path.dirname(__file__), "..", "config", "ethereum.yaml")
    cfgs: List[AppConfig] = load_runtime_configs(default_cfg)

    # Enforce deployment-mode safe defaults + validate config.
    public_defaults_status = boot_status["public_defaults"]
    config_validation_status = boot_status["config_validation"]
    for c in cfgs:
        try:
            enforce_public_defaults(c)
        except _PUBLIC_DEFAULTS_EXCEPTIONS as e:
            _set_boot(public_defaults_status, ok=False, reason="public_defaults_failed")
            public_defaults_status["error"] = str(e)
        # enforce_or_warn may raise in strict mode (intentionally).
        enforce_or_warn(c)
    _set_boot(config_validation_status, ok=True, reason="validated")

    # Runtime bundle
    runtime = build_runtime(cfgs)
    attach_runtime(app, runtime)

    # Primary API. Runtime/system/multichain hot paths and the dedicated
    # split routers below form the mounted public surface.
    app.include_router(runtime_router)
    app.include_router(multichain_router)
    app.include_router(system_router)
    app.include_router(analytics_router)
    app.include_router(admin_router)
    app.include_router(frontend_router)
    app.include_router(engine_router)
    app.include_router(command_center_router)
    app.include_router(operator_command_router)
    app.include_router(overlay_router)
    app.include_router(intelligence_router)
    app.include_router(governance_router)
    app.include_router(superstructure_router)
    app.include_router(ops_router)
    app.include_router(withdraw_router)
    app.include_router(withdraw_all_router)
    # High-change domains are split into dedicated routers to keep api.py stable.
    app.include_router(wealth_router)
    app.include_router(rft_router)
    app.include_router(advanced_router)
    app.include_router(agents_router)
    app.include_router(treasury_router)
    app.include_router(strategies_router)
    app.include_router(evolution_router)
    app.include_router(telemetry_router)
    app.include_router(fund_router)
    app.include_router(risk_router)
    app.include_router(launch_router)

    # Optional add-on routes (best-effort)
    cfg_paths = [getattr(c, "_source_path", "") for c in cfgs]
    _maybe_attach_omar(app, cfg_paths=[p for p in cfg_paths if p], boot_status=boot_status)

    return app


app = create_app()
