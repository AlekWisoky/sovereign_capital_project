from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..agents import all_mandates
from ..jsonsafe import to_json_safe as json_safe
from ._route_helpers import attach_summary_contract, degraded_payload, safe_json_route_call

router = APIRouter(tags=["agents"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/agents/state")
def agents_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: attach_summary_contract(
            rt.agent_hub_state(),
            family="agent_hub",
            read_model="agent_hub_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            degraded_payload(
                "agent_hub_state_failed",
                extra={"state": {}, "attribution": {"agents": []}, "weights": {}},
            ),
            family="agent_hub",
            read_model="agent_hub_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/agents/attribution")
def agents_attribution(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: attach_summary_contract(
            rt.agent_attribution_state(),
            family="agent_attribution",
            read_model="agent_attribution_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            degraded_payload(
                "agent_attribution_failed",
                extra={"agents": []},
            ),
            family="agent_attribution",
            read_model="agent_attribution_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/agents/catalog")
def agents_catalog():
    return json_safe({"ok": True, "agents": all_mandates()})
