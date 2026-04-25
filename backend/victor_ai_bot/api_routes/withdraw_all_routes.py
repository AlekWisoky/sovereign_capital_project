from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import to_json_safe as json_safe
from ._route_helpers import attach_summary_contract
from .withdraw_routes import _preview_request_body_error, _reject, _runtime

router = APIRouter(tags=["withdraw"])


@router.get("/api/withdraw/all/state", dependencies=[Depends(require_admin)])
async def withdraw_all_state(request: Request):
    runtime = _runtime(request)
    svc = getattr(runtime, "_withdraw_all_service", None)
    if svc is None:
        return json_safe(
            attach_summary_contract(
                _reject("withdraw_all_service_unavailable"),
                family="withdraw_all_state",
                read_model="withdraw_all_state_projection_v1",
                runtime=runtime,
            )
        )
    return json_safe(
        attach_summary_contract(
            await svc.state(runtime),
            family="withdraw_all_state",
            read_model="withdraw_all_state_projection_v1",
            runtime=runtime,
        )
    )


@router.post("/api/withdraw/all/config", dependencies=[Depends(require_admin)])
async def withdraw_all_config(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = _runtime(request)
    svc = getattr(runtime, "_withdraw_all_service", None)
    if svc is None:
        return json_safe(_reject("withdraw_all_service_unavailable"))
    return json_safe(svc.configure(runtime, payload))


@router.post("/api/withdraw/all/preview", dependencies=[Depends(require_admin)])
async def withdraw_all_preview(request: Request):
    invalid = await _preview_request_body_error(request)
    if invalid is not None:
        return json_safe(
            attach_summary_contract(
                invalid,
                family="withdraw_all_preview",
                read_model="withdraw_all_preview_projection_v1",
            )
        )
    runtime = _runtime(request)
    svc = getattr(runtime, "_withdraw_all_service", None)
    if svc is None:
        return json_safe(
            attach_summary_contract(
                _reject("withdraw_all_service_unavailable"),
                family="withdraw_all_preview",
                read_model="withdraw_all_preview_projection_v1",
                runtime=runtime,
            )
        )
    return json_safe(
        attach_summary_contract(
            await svc.preview(runtime),
            family="withdraw_all_preview",
            read_model="withdraw_all_preview_projection_v1",
            runtime=runtime,
        )
    )


@router.post("/api/withdraw/all/execute", dependencies=[Depends(require_admin)])
async def withdraw_all_execute(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = _runtime(request)
    svc = getattr(runtime, "_withdraw_all_service", None)
    if svc is None:
        return json_safe(_reject("withdraw_all_service_unavailable"))
    return json_safe(await svc.execute(runtime, payload))
