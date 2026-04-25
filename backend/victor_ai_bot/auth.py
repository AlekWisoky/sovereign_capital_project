from __future__ import annotations

from fastapi import Header, Request

from .security.auth import require_capability
from .security.permissions import Capability


def require_admin(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
) -> bool:
    return require_capability(Capability.ADMIN_WRITE, request=request, x_admin_key=x_admin_key)


def require_broadcast_enabled(
    request: Request,
    x_public_allow_broadcast: str | None = Header(default=None, alias="X-Public-Allow-Broadcast"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> bool:
    return require_capability(
        Capability.EXECUTE,
        request=request,
        x_public_allow_broadcast=x_public_allow_broadcast,
        x_admin_key=x_admin_key,
    )
