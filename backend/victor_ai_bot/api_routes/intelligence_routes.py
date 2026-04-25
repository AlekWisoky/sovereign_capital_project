from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends

from ..caq_kds.bus import BUS
from ..caq_kds.reliability import tracker as reliability_tracker
from ..caq_kds.self_evolution import engine as kds_engine
from ..caq_kds.xai import engine as xai_engine
from ..jsonsafe import json_safe
from ..pathing import canonical_data_dir
from ..runtime import MultiRuntimeBundle, RuntimeBundle
from ._route_helpers import attach_summary_contract

router = APIRouter(tags=["intelligence"])

_SAFE_RUNTIME_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


def _data_dir() -> str:
    return canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))


def _xai_storage_state(eng: Any) -> Dict[str, Any]:
    audit = getattr(eng, "audit", None)
    state_fn = getattr(audit, "state", None)
    if callable(state_fn):
        try:
            state = state_fn()
        except _SAFE_RUNTIME_EXCEPTIONS:
            return {
                "append": {
                    "ok": False,
                    "last_error_code": "xai_storage_state_failed",
                    "last_error": "runtime_error",
                },
                "degraded": True,
            }
        return dict(state or {}) if isinstance(state, dict) else {}
    return {}


@router.get("/api/xai/latest")
def xai_latest(limit: int = 50, rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    eng = xai_engine(data_dir=_data_dir(), chain=str(rt.cfg.chain.name))
    return json_safe(
        attach_summary_contract(
            {
                "ok": True,
                "items": eng.audit.latest(limit=int(limit)),
                "storage": _xai_storage_state(eng),
            },
            family="xai_latest",
            read_model="xai_latest_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/xai/decision/{decision_id}")
def xai_get(decision_id: str, rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    eng = xai_engine(data_dir=_data_dir(), chain=str(rt.cfg.chain.name))
    item = eng.audit.get(str(decision_id))
    return json_safe(
        attach_summary_contract(
            {"ok": bool(item is not None), "item": item, "storage": _xai_storage_state(eng)},
            family="xai_decision",
            read_model="xai_decision_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/xai/multichain/latest")
def xai_latest_multichain(
    limit: int = 50, rt: MultiRuntimeBundle = Depends(MultiRuntimeBundle.dep)
):
    out = []
    storage: Dict[str, Any] = {}
    chains = rt.chains() or []
    for name in chains[:12]:
        try:
            eng = xai_engine(data_dir=_data_dir(), chain=str(name))
            out.extend(eng.audit.latest(limit=max(5, int(limit) // max(1, len(chains)))))
            storage[str(name)] = _xai_storage_state(eng)
        except _SAFE_RUNTIME_EXCEPTIONS:
            continue
    try:
        out.sort(key=lambda x: float(x.get("ts", 0.0)), reverse=True)
    except _SAFE_RUNTIME_EXCEPTIONS:
        pass
    return json_safe(
        attach_summary_contract(
            {"ok": True, "items": out[: int(limit)], "storage": storage},
            family="xai_multichain",
            read_model="xai_multichain_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/reliability/state")
def reliability_state(rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    tr = reliability_tracker(data_dir=_data_dir(), chain=str(rt.cfg.chain.name))
    return json_safe(
        attach_summary_contract(
            {"ok": True, "state": tr.state()},
            family="reliability_state",
            read_model="reliability_state_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/reliability/multichain/state")
def reliability_state_multichain(rt: MultiRuntimeBundle = Depends(MultiRuntimeBundle.dep)):
    out = {}
    for name in (rt.chains() or [])[:20]:
        try:
            out[str(name)] = reliability_tracker(data_dir=_data_dir(), chain=str(name)).state()
        except _SAFE_RUNTIME_EXCEPTIONS:
            continue
    return json_safe(
        attach_summary_contract(
            {"ok": True, "states": out},
            family="reliability_multichain",
            read_model="reliability_multichain_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/kds/state")
def kds_state(rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    eng = kds_engine(data_dir=_data_dir(), chain=str(rt.cfg.chain.name))
    return json_safe(
        attach_summary_contract(
            {"ok": True, "state": eng.state()},
            family="kds_state",
            read_model="kds_state_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/kds/multichain/state")
def kds_state_multichain(rt: MultiRuntimeBundle = Depends(MultiRuntimeBundle.dep)):
    out = {}
    for name in (rt.chains() or [])[:20]:
        try:
            out[str(name)] = kds_engine(data_dir=_data_dir(), chain=str(name)).state()
        except _SAFE_RUNTIME_EXCEPTIONS:
            continue
    return json_safe(
        attach_summary_contract(
            {"ok": True, "states": out},
            family="kds_multichain",
            read_model="kds_multichain_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/inl/explain/opportunity/{opp_id}")
def inl_explain_opportunity(opp_id: str, rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    try:
        opp = next(
            (
                o
                for o in (getattr(rt, "_opps", []) or [])
                if str(getattr(o, "id", "")) == str(opp_id)
            ),
            None,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        opp = None
    if opp is None:
        return json_safe({"ok": False, "error": "opportunity_not_found"})
    meta = dict(opp.meta or {}) if hasattr(opp, "meta") and isinstance(opp.meta, dict) else {}
    brain = dict(meta.get("brain") or {}) if isinstance(meta.get("brain"), dict) else {}
    overlay = dict(meta.get("overlay") or {}) if isinstance(meta.get("overlay"), dict) else {}
    legs = int(len(getattr(getattr(opp, "route", None), "legs", []) or []))
    bus_snapshot = BUS.snapshot() if isinstance(BUS.snapshot(), dict) else {}
    return json_safe(
        {
            "ok": True,
            "opportunity_id": str(opp_id),
            "strategy": str(getattr(opp, "strategy", "")),
            "why_this_strategy": {
                "regime": str(overlay.get("regime_label", "unknown")),
                "margin_ratio": float(meta.get("margin_ratio", 0.0) or 0.0),
                "p_success": float(brain.get("p_success", 0.0) or 0.0),
                "ev_wei": str(brain.get("ev_wei", "0")),
                "consensus_score": float(overlay.get("consensus_score", 0.0) or 0.0),
                "legs": legs,
            },
            "show_regime_confidence": {
                "label": str(overlay.get("regime_label", "unknown")),
                "confidence": float((bus_snapshot.get("behaveagent") or {}).get("confidence", 0.0)),
            },
            "explain_risk_path": {
                "mev_risk": float(overlay.get("mev_risk", 0.0) or 0.0),
                "gas_mode": str(brain.get("gas_mode", "standard")),
                "safety": dict(meta.get("safety") or {}),
            },
            "intent_id": str(meta.get("intent_id", "")),
        }
    )


@router.post("/api/inl/scenario_sweep")
def inl_scenario_sweep(payload: Dict[str, Any], rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    base = dict(payload or {})
    changes = list(base.get("changes") or [])
    out = []
    for c in changes[:25]:
        try:
            sl = int(c.get("slippage_bps", getattr(rt.cfg.safety, "slippage_bps", 50)))
            mpb = int(c.get("minProfitBps", getattr(rt.cfg.safety, "minProfitBps", 0)))
            out.append({"slippage_bps": sl, "minProfitBps": mpb, "note": "sweep_stub"})
        except _SAFE_RUNTIME_EXCEPTIONS:
            continue
    return json_safe({"ok": True, "scenarios": out})


@router.get("/api/inl/daily_digest")
async def inl_daily_digest(rt: RuntimeBundle = Depends(RuntimeBundle.dep)):
    try:
        pnl = await rt.pnl_summary(window=100)
    except _SAFE_RUNTIME_EXCEPTIONS:
        pnl = {}
    beh = rt.behaveagent_state()
    bl = rt.blockspace_state()
    return json_safe(
        attach_summary_contract(
            {"ok": True, "pnl": pnl, "behaveagent": beh, "blockspace": bl},
            family="inl_daily_digest",
            read_model="inl_daily_digest_projection_v1",
            runtime=rt,
        )
    )
