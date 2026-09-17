from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Header, Request

from ..alpha_marketplace.contracts import submission_contract
from ..jsonsafe import to_json_safe as json_safe
from ..runtime_services.control_state import unavailable_state
from ..security.auth import require_capability
from ..security.permissions import Capability

router = APIRouter(tags=["alpha-marketplace"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def require_admin_write(
    request: Request,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
):
    return require_capability(Capability.ADMIN_WRITE, request=request, x_admin_key=x_admin_key)


@router.get("/api/fund/alpha-marketplace")
def marketplace_snapshot(rt=Depends(get_runtime)) -> dict[str, Any]:
    store = getattr(rt, "_alpha_marketplace", None)
    if store is None:
        return json_safe(unavailable_state("alpha_marketplace_unavailable", extra={"contract": submission_contract(), "items": []}))
    payload = store.snapshot()
    items = list(payload.get("items") or [])
    sleeve_projection = project_strategy_sleeves(
        rt, strategy_ids=[str(item.get("strategyId") or "") for item in items]
    )
    projected = dict(sleeve_projection.get("sleeves") or {}) if bool(sleeve_projection.get("ok")) else {}
    for item in items:
        strategy_id = str(item.get("strategyId") or "")
        if strategy_id in projected:
            item.update(projected[strategy_id])
    return json_safe({
        "ok": True,
        "enabled": bool(payload.get("enabled")),
        "contract": submission_contract(),
        "sleeveProjection": sleeve_projection,
        "items": items,
    })


@router.post("/api/fund/alpha-marketplace", dependencies=[Depends(require_admin_write)])
def marketplace_submit(body: dict = Body(default={}), rt=Depends(get_runtime)) -> dict[str, Any]:
    payload = dict(body or {})
    action = str(payload.get("action") or "").strip().lower()
    store = getattr(rt, "_alpha_marketplace", None)
    if store is None:
        return json_safe(unavailable_state("alpha_marketplace_unavailable", include_error=True))
    if action == "review":
        return json_safe(store.set_governance(
            str(payload.get("submissionId") or ""),
            review_state=str(payload.get("reviewState") or "pending"),
            governance_status=str(payload.get("governanceStatus") or "pending"),
            reviewer=str(payload.get("reviewer") or ""),
            reason=str(payload.get("reason") or ""),
        ))
    if action == "promote":
        return json_safe(store.promote(
            str(payload.get("submissionId") or ""),
            score=payload.get("score"),
            risk_score=payload.get("riskScore"),
            reviewer=str(payload.get("reviewer") or ""),
        ))
    if action == "retire":
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        return json_safe(store.retire(
            str(payload.get("submissionId") or ""),
            evidence=evidence,
            reviewer=str(payload.get("reviewer") or ""),
        ))
    allowed = {"title", "contributor", "family", "thesis"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        return json_safe({"ok": False, "status": "invalid", "reason_code": "unknown_request_fields", "fields": unknown})
    missing = [field for field in allowed if not str(payload.get(field) or "").strip()]
    if missing:
        return json_safe({"ok": False, "status": "invalid", "reason_code": "missing_required_fields", "fields": sorted(missing)})
    return json_safe(store.submit(
        title=str(payload["title"]).strip(),
        contributor=str(payload["contributor"]).strip(),
        family=str(payload["family"]).strip(),
        thesis=str(payload["thesis"]).strip(),
    ))
