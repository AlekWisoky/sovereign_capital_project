from __future__ import annotations

import inspect
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import to_json_safe as json_safe
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import attach_summary_contract, degraded_payload, safe_json_route_call

router = APIRouter(tags=["advanced"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def _meta_candidates_payload(rt: Any, limit: int) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    state = (
        rt.meta_state()
        if hasattr(rt, "meta_state")
        else unavailable_state("meta_unavailable", extra={"enabled": False})
    )
    if not isinstance(state, dict):
        state = unavailable_state("meta_state_failed", include_error=True)

    items = list((state.get("last_candidates") or []))[:limit]
    if items:
        return {"ok": True, "items": items}

    if hasattr(rt, "meta_generate"):
        gen = rt.meta_generate() or {}
        if isinstance(gen, dict) and gen.get("ok") is False:
            payload = dict(gen)
            payload.setdefault("items", [])
            return payload
        items = list((gen.get("candidates") or []))[:limit]
        return {"ok": True, "items": items}

    if state.get("ok") is False or state.get("status") == "unavailable":
        payload = dict(state)
        payload.setdefault("items", [])
        return payload

    return {"ok": True, "items": []}


@router.get("/api/meta/candidates")
def meta_candidates(request: Request, limit: int = 10, rt=Depends(get_runtime)):
    del request
    return safe_json_route_call(
        lambda: attach_summary_contract(
            _meta_candidates_payload(rt, limit),
            family="meta_candidates",
            read_model="meta_candidates_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            degraded_payload(
                "meta_candidates_failed",
                extra={"items": [], "candidates": []},
            ),
            family="meta_candidates",
            read_model="meta_candidates_projection_v1",
            runtime=rt,
        ),
    )


@router.post("/api/stress/evaluate", dependencies=[Depends(require_admin)])
async def stress_evaluate(
    request: Request, payload: Dict[str, Any] = Body(...), rt=Depends(get_runtime)
):
    del request
    scenario = str((payload or {}).get("scenario") or "noise_injection")
    if hasattr(rt, "stress_evaluate"):
        result = rt.stress_evaluate(scenario=scenario)
        if inspect.isawaitable(result):
            result = await result
        return json_safe(result)
    return json_safe({"ok": False, "error": "stress_unavailable"})
