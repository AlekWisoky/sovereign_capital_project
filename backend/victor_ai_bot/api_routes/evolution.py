from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..runtime_services.control_state import unavailable_state
from ._route_helpers import attach_summary_contract, degraded_payload, safe_json_route_call

router = APIRouter(tags=["evolution"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/evolution/state")
def evolution_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: attach_summary_contract(
            (
                rt.meta_state()
                if hasattr(rt, "meta_state")
                else unavailable_state(
                    "meta_unavailable",
                    include_error=True,
                    extra={"enabled": False},
                )
            ),
            family="evolution_state",
            read_model="evolution_state_projection_v1",
            runtime=rt,
        ),
        fallback=attach_summary_contract(
            unavailable_state(
                "meta_unavailable",
                include_error=True,
                extra={"enabled": False},
            ),
            family="evolution_state",
            read_model="evolution_state_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            degraded_payload(
                "meta_state_failed",
                extra={"enabled": False},
            ),
            family="evolution_state",
            read_model="evolution_state_projection_v1",
            runtime=rt,
        ),
    )
