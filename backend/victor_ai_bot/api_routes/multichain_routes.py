from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ._route_helpers import invalid_request_payload
from ..runtime import MultiRuntimeBundle
from ..runtime_services.runtime_routes_service import RuntimeRoutesService
from ..runtime_services.summary_read_contract import build_summary_read_contract

router = APIRouter(tags=["multichain"])
_service = RuntimeRoutesService()


@router.get("/api/multichain/chains")
async def multichain_chains(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return json_safe({"ok": True, "active": rt._active_chain, "chains": rt.chains()})
    return json_safe(
        {
            "ok": True,
            "active": getattr(rt.cfg.chain, "name", ""),
            "chains": [getattr(rt.cfg.chain, "name", "")],
        }
    )


@router.post("/api/multichain/select", dependencies=[Depends(require_admin)])
async def multichain_select(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    chain = str(payload.get("chain") or "")
    if not chain:
        return json_safe({"ok": False, "error": "missing chain"})
    if isinstance(rt, MultiRuntimeBundle):
        ok = rt.select_chain(chain)
        return json_safe({"ok": ok, "active": rt._active_chain, "chains": rt.chains()})
    ok = chain == getattr(rt.cfg.chain, "name", "")
    return json_safe(
        {
            "ok": ok,
            "active": getattr(rt.cfg.chain, "name", ""),
            "chains": [getattr(rt.cfg.chain, "name", "")],
        }
    )


@router.get("/api/multichain/state")
async def multichain_state(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return await rt.snapshot_all()
    chain = getattr(rt.cfg.chain, "name", "")
    return {"active": chain, "chains": {chain: await rt.snapshot()}}


@router.get("/api/multichain/summary")
async def multichain_summary(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return json_safe(await rt.summary_all())
    chain = getattr(rt.cfg.chain, "name", "")
    chain_summary = await rt.summary()
    payload = {"active": chain, "chains": {chain: chain_summary}}
    payload["summaryContract"] = build_summary_read_contract(
        family="multichain_runtime",
        payload=payload,
        phase="multichain_runtime_summary",
        read_model="multichain_runtime_summary_projection_v1",
    )
    return json_safe(payload)


@router.post("/api/multichain/settings", dependencies=[Depends(require_admin)])
async def multichain_settings(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    chain = str(payload.get("chain") or "").strip()
    patch_payload = {k: v for k, v in payload.items() if k != "chain"}
    ok, patch = _service.validate_settings_patch(patch_payload)
    if not ok:
        return json_safe(patch)
    if isinstance(rt, MultiRuntimeBundle):
        target = chain or rt._active_chain
        if target not in set(rt.chains()):
            return json_safe(invalid_request_payload("unknown_chain", field="chain", value=target))
        ok = rt.set_settings_for(target, **patch)
        return json_safe({"ok": ok, "active": rt._active_chain, "chains": rt.chains()})
    active_chain = str(getattr(rt.cfg.chain, "name", "") or "")
    if chain and chain != active_chain:
        return json_safe(invalid_request_payload("unknown_chain", field="chain", value=chain))
    rt.set_settings(**patch)
    return json_safe(
        {
            "ok": True,
            "active": active_chain,
            "chains": [active_chain],
        }
    )
