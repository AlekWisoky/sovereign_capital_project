from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..api import get_runtime
from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime_services.auxiliary_state_service import (
    CAPITAL_CONTRACT_VERSION,
    CAPITAL_POLICY_VERSION,
)
from ..runtime_services.command_center_service import CommandCenterService
from ..runtime_services.summary_read_contract import build_summary_read_contract
from ._route_helpers import attach_summary_contract

router = APIRouter()


def _service(runtime: Any) -> CommandCenterService:
    return getattr(runtime, "_command_center_service", None) or CommandCenterService()


@router.get("/api/commandcenter/snapshot")
async def commandcenter_snapshot(request: Request):
    runtime = get_runtime(request)
    return await _service(runtime).snapshot(runtime)


@router.post("/api/commandcenter/control", dependencies=[Depends(require_admin)])
async def commandcenter_control(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    result = _service(runtime).apply_controls(runtime, payload)
    return json_safe(result.payload)


@router.get("/api/commandcenter/audit/tail")
async def commandcenter_audit_tail(request: Request, limit: int = 200):
    runtime = get_runtime(request)
    # Audit history is an observability surface. Its read contract needs the
    # canonical contract versions, but it does not need a live capital-truth
    # projection. Avoid synchronously traversing the shared runtime/capital
    # state from this async request path.
    payload = _service(runtime).audit_tail(runtime, limit=int(limit))
    payload["summaryContract"] = build_summary_read_contract(
        family="command_center_audit",
        payload=payload,
        capital_contract={"contractVersion": CAPITAL_CONTRACT_VERSION},
        capital_policy={"contractVersion": CAPITAL_POLICY_VERSION},
        phase="command_center_audit_summary",
        read_model="command_center_audit_projection_v1",
    )
    return payload


@router.get("/api/commandcenter/explain")
async def commandcenter_explain(request: Request):
    runtime = get_runtime(request)
    return attach_summary_contract(
        await _service(runtime).explain(runtime),
        family="command_center_explain",
        read_model="command_center_explain_projection_v1",
        runtime=runtime,
    )
