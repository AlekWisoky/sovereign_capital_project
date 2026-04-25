from __future__ import annotations

from fastapi import APIRouter, Request

from ._route_helpers import attach_summary_contract

router = APIRouter(prefix="/api/engines", tags=["engines"])


@router.get("/state")
async def engine_state(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if hasattr(rt, "engine_state"):
        return attach_summary_contract(
            rt.engine_state(),
            family="engine_state",
            read_model="engine_state_projection_v1",
            runtime=rt,
        )
    return attach_summary_contract(
        {"items": [], "capabilities": {}, "summary": {"engines": []}},
        family="engine_state",
        read_model="engine_state_projection_v1",
        runtime=rt,
    )
