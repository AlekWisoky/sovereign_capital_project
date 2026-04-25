"""Deployment mode gates.

This repo is often run behind port-forwarded sandbox URLs (e.g., ChainIDE) where
the backend may be reachable on the public internet.

We support two modes:

1) private (default): normal behavior; endpoints can broadcast txs when configured.
2) public: safe-by-default; backend WILL NOT broadcast transactions.
   - withdraw_mode is forced to "txdata" (wallet signs client-side)
   - execution.dry_run is forced to True
   - endpoints that could broadcast are disabled unless explicitly overridden

Explicit override (NOT recommended): set VICTOR_PUBLIC_ALLOW_BROADCAST=1 and
include header X-Public-Allow-Broadcast: 1 on the specific request.
"""

from __future__ import annotations

import os

_SAFE_PUBLIC_DEFAULT_ASSIGN_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def deployment_mode() -> str:
    return (os.environ.get("VICTOR_DEPLOYMENT_MODE", "private") or "private").strip().lower()


def is_public_mode() -> bool:
    return deployment_mode() == "public"


def public_broadcast_override_enabled() -> bool:
    # Strongly discouraged. See docs/SECURITY_MODEL.md.
    return (os.environ.get("VICTOR_PUBLIC_ALLOW_BROADCAST", "") or "").strip() == "1"


def public_broadcast_request_confirmed(header_value: str | None) -> bool:
    return (header_value or "").strip() == "1"


def enforce_public_defaults(cfg) -> None:
    """Mutate cfg in-place to enforce safe defaults for public deployments."""
    if not is_public_mode():
        return

    # Always force txdata (client signs) in public mode.
    try:
        cfg.execution.withdraw_mode = "txdata"
    except _SAFE_PUBLIC_DEFAULT_ASSIGN_EXCEPTIONS:
        pass

    # Force dry-run unless operator enables the explicit override.
    if not public_broadcast_override_enabled():
        try:
            cfg.execution.dry_run = True
        except _SAFE_PUBLIC_DEFAULT_ASSIGN_EXCEPTIONS:
            pass

        # Force auto-trading off; keep scanning + WS + dashboards.
        try:
            cfg.execution.auto_trading = False
        except _SAFE_PUBLIC_DEFAULT_ASSIGN_EXCEPTIONS:
            pass
