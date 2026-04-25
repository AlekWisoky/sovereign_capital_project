from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request
from starlette import status

from ..deploy_mode import (
    is_public_mode,
    public_broadcast_override_enabled,
    public_broadcast_request_confirmed,
)
from .permissions import Capability


def _admin_key_matches(x_admin_key: str | None) -> bool:
    expected = os.environ.get("VICTOR_ADMIN_KEY", "").strip()
    if not expected:
        return os.environ.get("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "").strip() == "1"
    return str(x_admin_key or "").strip() == expected


def require_capability(
    capability: Capability,
    *,
    request: Request,
    x_admin_key: str | None = None,
    x_public_allow_broadcast: str | None = None,
) -> bool:
    cap = Capability(capability)
    allowed = _admin_key_matches(x_admin_key)
    if (
        cap
        in {
            Capability.ADMIN_READ,
            Capability.ADMIN_WRITE,
            Capability.GOVERNANCE,
            Capability.TREASURY_WRITE,
            Capability.EVOLUTION_WRITE,
        }
        and not allowed
    ):
        _audit(request, action="capability_denied", capability=cap.value, allowed=False)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin_key_required")
    if (
        cap == Capability.EXECUTE
        and is_public_mode()
        and not (
            public_broadcast_override_enabled()
            and public_broadcast_request_confirmed(x_public_allow_broadcast)
        )
    ):
        _audit(
            request,
            action="capability_denied",
            capability=cap.value,
            allowed=False,
            extra={"reason": "public_mode_broadcast_blocked"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="broadcast_disabled_in_public_mode"
        )
    _audit(request, action="capability_allowed", capability=cap.value, allowed=True)
    return True


def _audit(
    request: Request, *, action: str, capability: str, allowed: bool, extra: dict | None = None
) -> None:
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    rt = getattr(state, "runtime", None)
    store = getattr(rt, "_security_audit", None)
    if store is None:
        return
    chain_name = str(
        getattr(getattr(getattr(rt, "cfg", None), "chain", None), "name", "") or ""
    )
    store.record(
        action=action,
        allowed=allowed,
        capability=capability,
        subject="http",
        chain=chain_name,
        details=extra or {},
    )
