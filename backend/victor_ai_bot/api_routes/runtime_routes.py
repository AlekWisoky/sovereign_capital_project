from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime import MultiRuntimeBundle
from ..runtime_services.runtime_routes_service import RuntimeRoutesService
from ._route_helpers import attach_summary_contract, safe_json_route_call

router = APIRouter(tags=["runtime"])
_service = RuntimeRoutesService()


def get_runtime(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/api/deploy/info")
async def deploy_info():
    return _service.deploy_info()


@router.get("/api/state")
async def state(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    return attach_summary_contract(
        await rt.snapshot(),
        family="runtime_state",
        read_model="runtime_state_projection_v1",
        runtime=rt,
    )


@router.get("/api/brain/state")
async def brain_state(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    return safe_json_route_call(
        lambda: attach_summary_contract(
            rt.brain_state(),
            family="brain_state",
            read_model="brain_state_projection_v1",
            runtime=rt,
        ),
        fallback=attach_summary_contract(
            {"ok": False, "error": "brain_unavailable"},
            family="brain_state",
            read_model="brain_state_projection_v1",
            runtime=rt,
        ),
    )


@router.post("/api/runtime/start", dependencies=[Depends(require_admin)])
async def start_runtime(request: Request):
    request.app.state.runtime.start()  # type: ignore[attr-defined]
    return {"ok": True}


@router.post("/api/runtime/stop", dependencies=[Depends(require_admin)])
async def stop_runtime(request: Request):
    await request.app.state.runtime.stop()  # type: ignore[attr-defined]
    return {"ok": True}


@router.post("/api/settings", dependencies=[Depends(require_admin)])
async def update_settings(request: Request, payload: dict = Body(...)):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    ok, normalized = _service.validate_settings_patch(payload)
    if not ok:
        return json_safe(normalized)
    rt.set_settings(**normalized)
    return {"ok": True}
