from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..pathing import canonical_data_dir
from ..runtime import MultiRuntimeBundle
from ..rft.episode_builder import build_episodes, export_episodes_jsonl
from ..rft.graders.composite import score_proposal
from ..rft.replay.bundle import export_replay_bundle, load_replay_bundle
from ..rft.replay.verifier import verify_replay_bundle
from ..rft.schema import ProposalOutput

router = APIRouter(prefix="/api/rft", tags=["rft"])

_SAFE_RFT_ROUTE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
)


def _data_dir() -> str:
    return canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))


def _active_runtime(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


def _episodes(limit: int = 20):
    return build_episodes(_data_dir(), limit=int(limit or 0), top_k=20)


def _command_center_episode_export_enabled(runtime: Any) -> bool:
    controls = getattr(getattr(runtime, "_cc", None), "controls", None)
    if controls is None:
        return False
    try:
        return bool(getattr(controls, "rft_episode_export_enabled", False))
    except _SAFE_RFT_ROUTE_EXCEPTIONS:
        return False


def _append_rft_export_audit(runtime: Any, *, path: str, count: int, reason: str) -> None:
    cc = getattr(runtime, "_cc", None)
    audit = getattr(cc, "audit", None)
    if audit is None:
        return
    try:
        audit.append(
            "rft_episode_export",
            {"path": str(path), "count": int(count)},
            actor="operator",
            reason=str(reason or ""),
        )
    except _SAFE_RFT_ROUTE_EXCEPTIONS:
        return


@router.get("/schema/proposal")
def proposal_schema():
    return json_safe({"ok": True, "schema": ProposalOutput.json_schema_draft07()})


@router.get("/episodes/sample")
def sample_episodes(limit: int = Query(default=5, ge=1, le=100)):
    eps = _episodes(limit=limit)
    return json_safe({"ok": True, "items": [e.model_dump() for e in eps]})


@router.post("/episodes/export", dependencies=[Depends(require_admin)])
def export_episodes(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = _active_runtime(request)
    rft_cfg = (
        getattr(getattr(rt.cfg.execution, "rft", None), "episode_export_enabled", False)
        if hasattr(rt, "cfg")
        else False
    )
    cc_enabled = _command_center_episode_export_enabled(rt)
    if not (rft_cfg or cc_enabled):
        return json_safe({"ok": False, "error": "episode_export_disabled"})
    reason = str(payload.get("reason") or "")
    limit = int(payload.get("limit") or 0)
    ts = int(time.time())
    out_name = str(payload.get("filename") or f"xdv_rft_episodes_{ts}.jsonl")
    out_path = os.path.join(_data_dir(), "rft", "exports", out_name)
    res = export_episodes_jsonl(
        _data_dir(),
        out_path,
        limit=limit,
        top_k=int(getattr(getattr(rt.cfg.execution, "rft", None), "snapshot_top_k", 20) or 20),
    )
    _append_rft_export_audit(
        rt,
        path=out_path,
        count=int(res.get("count") or 0),
        reason=reason,
    )
    return json_safe(
        {"ok": True, "count": int(res.get("count") or 0), "path": out_path, "reason": reason}
    )


@router.get("/replay/bundle/{event_id}")
def get_replay_bundle(event_id: str):
    bundle = load_replay_bundle(_data_dir(), event_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="bundle_not_found")
    return json_safe({"ok": True, "bundle": bundle})


@router.post("/replay/verify")
def verify_replay(payload: Dict[str, Any] = Body(...)):
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else None
    if bundle is None:
        event_id = str(payload.get("event_id") or "")
        bundle = load_replay_bundle(_data_dir(), event_id)
    if bundle is None:
        return json_safe({"ok": False, "error": "bundle_not_found"})
    return json_safe(verify_replay_bundle(bundle))


def _find_episode(episode_id: str):
    for ep in build_episodes(_data_dir(), limit=0, top_k=20):
        if str(ep.context.episode_id) == str(episode_id):
            return ep
    return None


@router.get("/grader/score", dependencies=[Depends(require_admin)])
def score_get(request: Request, episode_id: str = Query(...), proposal: str = Query(...)):
    try:
        proposal_obj = json.loads(proposal)
    except json.JSONDecodeError:
        return json_safe({"ok": False, "error": "invalid_proposal_json"})
    ep = _find_episode(episode_id)
    if ep is None:
        return json_safe({"ok": False, "error": "episode_not_found"})
    rt = _active_runtime(request)
    weights = (
        getattr(getattr(rt.cfg.execution, "rft", None), "grader_weights", {})
        if hasattr(rt, "cfg")
        else {}
    )
    res = score_proposal(ep.context, proposal_obj, weights=weights)
    return json_safe({"ok": True, "score": res.model_dump()})


@router.post("/grader/score", dependencies=[Depends(require_admin)])
def score_post(request: Request, payload: Dict[str, Any] = Body(...)):
    episode_id = str(payload.get("episode_id") or "")
    proposal_obj: Dict[str, Any] = (
        dict(payload.get("proposal") or {}) if isinstance(payload.get("proposal"), dict) else {}
    )
    ep = _find_episode(episode_id)
    if ep is None:
        return json_safe({"ok": False, "error": "episode_not_found"})
    rt = _active_runtime(request)
    weights = (
        getattr(getattr(rt.cfg.execution, "rft", None), "grader_weights", {})
        if hasattr(rt, "cfg")
        else {}
    )
    res = score_proposal(ep.context, proposal_obj, weights=weights)
    return json_safe({"ok": True, "score": res.model_dump()})
