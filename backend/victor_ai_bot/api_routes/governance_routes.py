from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime import RuntimeBundle
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import (
    attach_summary_contract,
    degraded_payload,
    safe_json_route_call,
    with_auto_trade_route_projection,
)

router = APIRouter(tags=["governance"])


def _governance_unavailable(
    *,
    intent_id: str | None = None,
    threat: bool = False,
    runtime: Any | None = None,
) -> dict:
    payload = unavailable_state(
        "governance_disabled",
        include_reason=False,
        include_error=True,
        extra={"enabled": False},
    )
    if intent_id is not None:
        payload["intent_id"] = str(intent_id)
    if threat:
        payload["threat"] = {}
    return attach_summary_contract(
        with_auto_trade_route_projection(payload, runtime=runtime),
        family="governance_intent" if intent_id is not None else "governance_threat",
        read_model=(
            "governance_intent_projection_v1"
            if intent_id is not None
            else "governance_threat_projection_v1"
        ),
        runtime=runtime,
    )


def _governance_intent_failed_payload(intent_id: str, runtime: Any | None = None) -> dict:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload(
                "governance_intent_failed",
                extra={"intent_id": str(intent_id), "enabled": False},
            ),
            runtime=runtime,
        ),
        family="governance_intent",
        read_model="governance_intent_projection_v1",
        runtime=runtime,
    )


def _governance_threat_failed_payload(runtime: Any | None = None) -> dict:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload(
                "governance_threat_status_failed",
                extra={"enabled": False, "threat": {}},
            ),
            runtime=runtime,
        ),
        family="governance_threat",
        read_model="governance_threat_projection_v1",
        runtime=runtime,
    )


@router.get("/api/governance/intent/{intent_id}")
def view_intent(intent_id: str, rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    def _payload() -> dict:
        if getattr(rt, "_gov", None) is None:
            return _governance_unavailable(intent_id=str(intent_id), runtime=rt)
        return attach_summary_contract(
            with_auto_trade_route_projection(
                rt._gov.view_intent(intent_id=str(intent_id)),
                runtime=rt,
            ),
            family="governance_intent",
            read_model="governance_intent_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda exc: _governance_intent_failed_payload(
            intent_id=str(intent_id), runtime=rt
        ),
    )


@router.post("/api/governance/intent/{intent_id}/approve")
def approve_intent(
    intent_id: str,
    rt: RuntimeBundle = Depends(RuntimeBundle.dep),
    _: bool = Depends(require_admin),
):
    if getattr(rt, "_gov", None) is None:
        return json_safe({**_governance_unavailable(intent_id=str(intent_id)), "approved": False})
    approved = bool(rt._gov.approve_intent(intent_id=str(intent_id), reviewer="human"))
    return json_safe(
        {"ok": approved, "approved": approved, "intent_id": str(intent_id), "reviewer": "human"}
    )


@router.post("/api/governance/intent/{intent_id}/reject")
def reject_intent(
    intent_id: str,
    rt: RuntimeBundle = Depends(RuntimeBundle.dep),
    _: bool = Depends(require_admin),
):
    if getattr(rt, "_gov", None) is None:
        return json_safe({**_governance_unavailable(intent_id=str(intent_id)), "rejected": False})
    rejected = bool(rt._gov.reject_intent(intent_id=str(intent_id), reviewer="human"))
    return json_safe(
        {"ok": rejected, "rejected": rejected, "intent_id": str(intent_id), "reviewer": "human"}
    )


@router.get("/api/governance/threat_status")
def threat_status(rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    def _payload() -> dict:
        if getattr(rt, "_gov", None) is None:
            return _governance_unavailable(threat=True, runtime=rt)
        return attach_summary_contract(
            with_auto_trade_route_projection(
                {"ok": True, "threat": rt._gov.threat.snapshot()},
                runtime=rt,
            ),
            family="governance_threat",
            read_model="governance_threat_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda exc: _governance_threat_failed_payload(runtime=rt),
    )
