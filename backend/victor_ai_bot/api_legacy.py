from __future__ import annotations
from fastapi import APIRouter, Request
from .runtime import MultiRuntimeBundle

router = APIRouter()


def get_runtime(request: Request):
    """Return the active RuntimeBundle (works in single- or multi-chain mode)."""
    rt = request.app.state.runtime  # type: ignore
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


# Core runtime route ownership moved to api_routes.runtime_routes.


# -------------------------
# Multi-chain route ownership moved to api_routes.multichain_routes.
# -------------------------


# Runtime control and brain-state route ownership moved to api_routes.runtime_routes.


# -------------------------
# Sovereign Command Center (additive)
# -------------------------


# Command center routes moved to dedicated api_routes.command_center_routes.

# -------------------------
# Phase 14+/19 superstructure and governance state route ownership moved to
# api_routes.superstructure_routes.
# -------------------------


# -------------------------
# Phase 20: FIOA (FIU-inspired Operational Independence)
# -------------------------


# Phase 20/21 FIOA and narrative route ownership moved to api_routes.overlay_routes.


# -------------------------
# Phase 17 command routes moved to api_routes.operator_command_routes.
# -------------------------


# -------------------------
# Remaining HTTP control/ops route ownership moved to api_routes.ops_routes.
# -------------------------


# -------------------------
# Remaining admin HTML and websocket route ownership moved to
# api_routes.frontend_routes.
# -------------------------

# -------------------------
# Withdraw profits (executor)
# -------------------------
# Route ownership moved to dedicated api_routes.withdraw_routes.

# -------------------------
# CAQ-KDS / INL route ownership moved to api_routes.intelligence_routes.
# -------------------------


# -------------------------
# Blockchain Agent Standard: governance + human interface API
# -------------------------


# -------------------------
# Governance intent + treasury goal route ownership moved to canonical api_routes modules.
# -------------------------


# Analytics route ownership moved to api_routes.analytics_routes.
