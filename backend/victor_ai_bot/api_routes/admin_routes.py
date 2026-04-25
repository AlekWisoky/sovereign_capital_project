from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from ..jsonsafe import to_json_safe as json_safe
from ..security.auth import require_capability
from ..security.permissions import Capability

router = APIRouter(tags=["admin"])


def require_admin_read(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_READ, request=request, x_admin_key=x_admin_key)


@router.get("/api/admin/capabilities", dependencies=[Depends(require_admin_read)])
def admin_capabilities():
    return json_safe({"ok": True, "capabilities": [c.value for c in Capability]})
