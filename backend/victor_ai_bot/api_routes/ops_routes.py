from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin, require_broadcast_enabled
from ..config import load_config
from ..jsonsafe import json_safe
from ..presets import find_preset_path, get_preset, list_presets
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import (
    attach_summary_contract,
    coerce_canonical_bool,
    coerce_non_negative_int,
    coerce_non_negative_int_string,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    with_auto_trade_route_projection,
)
from ..runtime import MultiRuntimeBundle, RuntimeBundle

router = APIRouter(tags=["ops"])


def _disabled_unavailable(**extra: Any) -> Dict[str, Any]:
    payload = {"enabled": False}
    payload.update(extra)
    return unavailable_state("unavailable", extra=payload)


def _arbitrage_disabled_state(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            unavailable_state("arbitrage_unavailable", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="arbitrage_state",
        read_model="arbitrage_state_projection_v1",
        runtime=runtime,
    )


def _arbitrage_state_failed_payload(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload("arbitrage_state_failed", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="arbitrage_state",
        read_model="arbitrage_state_projection_v1",
        runtime=runtime,
    )


def _mev_disabled_state(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(_disabled_unavailable(), runtime=runtime),
        family="mev_state",
        read_model="mev_state_projection_v1",
        runtime=runtime,
    )


def _mev_state_failed_payload(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload("mev_state_failed", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="mev_state",
        read_model="mev_state_projection_v1",
        runtime=runtime,
    )


def get_runtime(request: Request):
    """Return the active RuntimeBundle (works in single- or multi-chain mode)."""
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


@router.get("/api/arbitrage/state")
async def arbitrage_state(request: Request):
    rt = get_runtime(request)
    if not hasattr(rt, "arbitrage_state"):
        return json_safe(_arbitrage_disabled_state(rt))
    return safe_json_route_call(
        lambda: attach_summary_contract(
            with_auto_trade_route_projection(rt.arbitrage_state(), runtime=rt),
            family="arbitrage_state",
            read_model="arbitrage_state_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: _arbitrage_state_failed_payload(rt),
    )


@router.post("/api/arbitrage/start", dependencies=[Depends(require_admin)])
async def arbitrage_start(request: Request):
    rt = get_runtime(request)
    try:
        ok = bool(rt.arbitrage_start())
        return json_safe({"ok": ok})
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return json_safe({"ok": False, "error": "arbitrage_start_failed"})


@router.post("/api/arbitrage/stop", dependencies=[Depends(require_admin)])
async def arbitrage_stop(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "arbitrage_stop"):
        ok = bool(await rt.arbitrage_stop())
        return json_safe({"ok": True, "stopped": ok})
    return json_safe({"ok": False, "error": "arbitrage_stop_failed"})


@router.get("/api/mev/state")
async def mev_state(request: Request):
    rt = get_runtime(request)
    if not hasattr(rt, "mev_state"):
        return json_safe(_mev_disabled_state(rt))
    return safe_json_route_call(
        lambda: attach_summary_contract(
            with_auto_trade_route_projection(rt.mev_state(), runtime=rt),
            family="mev_state",
            read_model="mev_state_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: _mev_state_failed_payload(rt),
    )


@router.post("/api/mev/start", dependencies=[Depends(require_admin)])
async def mev_start(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "mev_start"):
        ok = bool(rt.mev_start())
        return json_safe({"ok": True, "started": ok})
    return json_safe({"ok": False, "error": "mev_start_failed"})


@router.post("/api/mev/stop", dependencies=[Depends(require_admin)])
async def mev_stop(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "mev_stop"):
        ok = bool(await rt.mev_stop())
        return json_safe({"ok": True, "stopped": ok})
    return json_safe({"ok": False, "error": "mev_stop_failed"})


def _meta_disabled_state(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            unavailable_state("meta_unavailable", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="meta_state",
        read_model="meta_state_projection_v1",
        runtime=runtime,
    )


def _meta_state_failed_payload(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload("meta_state_failed", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="meta_state",
        read_model="meta_state_projection_v1",
        runtime=runtime,
    )


def _meta_action_unavailable(**extra: Any) -> Dict[str, Any]:
    return unavailable_state("meta_unavailable", include_error=True, extra=extra or None)


@router.get("/api/meta/state")
async def meta_state(request: Request):
    rt = get_runtime(request)
    if not hasattr(rt, "meta_state"):
        return json_safe(_meta_disabled_state(rt))
    return safe_json_route_call(
        lambda: attach_summary_contract(
            with_auto_trade_route_projection(rt.meta_state(), runtime=rt),
            family="meta_state",
            read_model="meta_state_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: _meta_state_failed_payload(rt),
    )


@router.post("/api/meta/start", dependencies=[Depends(require_admin)])
async def meta_start(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "meta_start"):
        ok = bool(rt.meta_start())
        return json_safe({"ok": True, "started": ok})
    return json_safe(_meta_action_unavailable(started=False))


@router.post("/api/meta/stop", dependencies=[Depends(require_admin)])
async def meta_stop(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "meta_stop"):
        ok = bool(await rt.meta_stop())
        return json_safe({"ok": True, "stopped": ok})
    return json_safe(_meta_action_unavailable(stopped=False))


@router.post("/api/meta/generate", dependencies=[Depends(require_admin)])
async def meta_generate(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "meta_generate"):
        return json_safe(rt.meta_generate())
    return json_safe(_meta_action_unavailable(candidates=[]))


@router.post("/api/meta/apply", dependencies=[Depends(require_admin)])
async def meta_apply(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    cand_id = str(payload.get("id") or payload.get("candidate_id") or "")
    if not cand_id:
        return json_safe({"ok": False, "error": "missing_id"})
    if hasattr(rt, "meta_apply"):
        return json_safe(rt.meta_apply(cand_id))
    return json_safe(_meta_action_unavailable(id=cand_id))


@router.post("/api/safety", dependencies=[Depends(require_admin)])
async def update_safety(request: Request, payload: Dict[str, Any] = Body(...)):
    staged_patch: Dict[str, Any] = {}
    for field in ("require_estimate_gas", "require_simulation"):
        if field not in payload:
            continue
        bool_ok, coerced_bool = coerce_canonical_bool(payload[field])
        if not bool_ok:
            return json_safe(
                invalid_request_payload("invalid_boolean_value", field=field, value=payload[field])
            )
        staged_patch[field] = coerced_bool

    for field in ("minProfitBps", "slippage_bps"):
        if field not in payload:
            continue
        int_ok, coerced_int = coerce_non_negative_int(payload[field])
        if not int_ok:
            return json_safe(
                invalid_request_payload("invalid_integer_value", field=field, value=payload[field])
            )
        staged_patch[field] = coerced_int

    for field in ("minProfitAbs", "max_borrow_amount"):
        if field not in payload:
            continue
        str_ok, coerced_int_string = coerce_non_negative_int_string(payload[field])
        if not str_ok:
            return json_safe(
                invalid_request_payload("invalid_integer_value", field=field, value=payload[field])
            )
        staged_patch[field] = coerced_int_string

    cfg = request.app.state.runtime.cfg  # type: ignore[attr-defined]
    s = cfg.safety
    rt = get_runtime(request)
    original_values: Dict[str, Any] = {field: getattr(s, field) for field in staged_patch}
    bankroll_cfg = getattr(getattr(rt, "_bankroll", None), "cfg", None)
    bankroll_original = None
    staged_bankroll = None
    if "max_borrow_amount" in staged_patch and bankroll_cfg is not None:
        bankroll_original = getattr(bankroll_cfg, "max_borrow_amount_wei", None)
        staged_bankroll = int(staged_patch["max_borrow_amount"])

    try:
        for field, value in staged_patch.items():
            setattr(s, field, value)
        if staged_bankroll is not None and bankroll_cfg is not None:
            bankroll_cfg.max_borrow_amount_wei = staged_bankroll
    except (AttributeError, RuntimeError, TypeError, ValueError):
        for field, value in original_values.items():
            try:
                setattr(s, field, value)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        if bankroll_cfg is not None and bankroll_original is not None:
            try:
                bankroll_cfg.max_borrow_amount_wei = bankroll_original
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        return json_safe(
            {
                "ok": False,
                "status": "unavailable",
                "reason_code": "safety_update_failed",
                "reason": "safety_update_failed",
                "error": "safety_update_failed",
            }
        )
    return {"ok": True}


@router.get("/api/gas/presets")
async def gas_presets(request: Request):
    cfg = request.app.state.runtime.cfg  # type: ignore[attr-defined]
    p = cfg.execution.gas_presets
    return json_safe(
        {
            "ok": True,
            "current_mode": cfg.execution.gas_mode,
            "presets": {
                "standard": {
                    "max_fee_gwei": p.standard_max_fee_gwei,
                    "priority_fee_gwei": p.standard_priority_fee_gwei,
                },
                "fast": {
                    "max_fee_gwei": p.fast_max_fee_gwei,
                    "priority_fee_gwei": p.fast_priority_fee_gwei,
                },
                "instant": {
                    "max_fee_gwei": p.instant_max_fee_gwei,
                    "priority_fee_gwei": p.instant_priority_fee_gwei,
                },
            },
        }
    )


@router.post(
    "/api/opportunities/trade",
    dependencies=[Depends(require_admin), Depends(require_broadcast_enabled)],
)
async def trade_by_id(request: Request, payload: Dict[str, Any] = Body(...)):
    opp_id = payload.get("id") or ""
    if not opp_id:
        return {"ok": False, "error": "missing id"}
    amount_in_override = payload.get("amount_in_override")
    res = await request.app.state.runtime.execute_opportunity_by_id(  # type: ignore[attr-defined]
        opp_id, mode="manual", amount_in_override=amount_in_override
    )
    return json_safe(
        {
            "ok": res.ok,
            "dry_run": res.dry_run,
            "reason": res.reason,
            "tx_hash": res.tx_hash,
            "plan": res.plan,
        }
    )


@router.post("/api/opportunities/simulate", dependencies=[Depends(require_admin)])
async def simulate_by_id(request: Request, payload: Dict[str, Any] = Body(...)):
    opp_id = payload.get("id") or ""
    if not opp_id:
        return {"ok": False, "error": "missing id"}
    amount_in_override = payload.get("amount_in_override")
    res = await request.app.state.runtime.execute_opportunity_by_id(  # type: ignore[attr-defined]
        opp_id,
        mode="simulate",
        amount_in_override=amount_in_override,
        force_dry_run=True,
    )
    return json_safe(
        {
            "ok": res.ok,
            "dry_run": True,
            "reason": res.reason,
            "tx_hash": None,
            "plan": res.plan,
        }
    )


@router.post("/api/tx/receipt", dependencies=[Depends(require_admin)])
async def poll_receipt(request: Request, payload: Dict[str, Any] = Body(...)):
    tx_hash = payload.get("tx_hash") or ""
    if not tx_hash:
        return {"ok": False, "error": "missing tx_hash"}
    out = await request.app.state.runtime.poll_and_update_receipt(tx_hash)  # type: ignore[attr-defined]
    return json_safe(out)


@router.get("/api/pnl/summary")
async def pnl_summary(request: Request, window: int = 50):
    out = await request.app.state.runtime.pnl_summary(window=window)  # type: ignore[attr-defined]
    return json_safe({"ok": True, "summary": out})


@router.get("/api/pnl/income")
async def pnl_income(window: int = 3600, rt=Depends(get_runtime)):
    return json_safe(await rt.pnl_income(window=window))


@router.get("/api/presets")
async def presets_list():
    return json_safe({"ok": True, "presets": list_presets()})


@router.get("/api/presets/{chain}/{name}")
async def presets_get(chain: str, name: str):
    return json_safe({"ok": True, "preset": get_preset(chain, name)})


@router.post("/api/presets/apply", dependencies=[Depends(require_admin)])
async def presets_apply(request: Request, payload: Dict[str, Any] = Body(...)):
    chain = str(payload.get("chain") or "")
    name = str(payload.get("name") or "default")
    auto_start_payload = payload.get("auto_start", True)
    ok, auto_start = coerce_canonical_bool(auto_start_payload)
    if not ok:
        return json_safe(
            invalid_request_payload(
                "invalid_boolean_value", field="auto_start", value=auto_start_payload
            )
        )

    p = find_preset_path(chain, name)
    new_cfg = load_config(str(p))

    old = request.app.state.runtime  # type: ignore[attr-defined]
    was_running = bool(getattr(old, "_task", None)) and not getattr(old, "_task").done()
    ws_clients = getattr(old, "_ws_clients", [])
    if ws_clients is None:
        ws_clients = []

    await old.stop()

    new_rt = RuntimeBundle(new_cfg)
    setattr(new_rt, "_ws_clients", ws_clients)

    request.app.state.runtime = new_rt  # type: ignore[attr-defined]
    if auto_start and was_running:
        new_rt.start()

    return json_safe(
        {
            "ok": True,
            "applied": {"chain": chain, "name": name, "path": str(p)},
            "active_chain": new_cfg.chain.name,
        }
    )


@router.get("/api/admin/state")
async def admin_state(request: Request):
    runtime = request.app.state.runtime  # type: ignore[attr-defined]
    snap = await runtime.admin_snapshot()  # type: ignore[attr-defined]
    snap["settings"] = {
        "auto_trading": runtime._auto_trading,  # type: ignore[attr-defined]
        "auto_reinvest_enabled": runtime.cfg.execution.auto_reinvest_enabled,  # type: ignore[attr-defined]
        "reinvest_rate": runtime.cfg.execution.reinvest_rate,  # type: ignore[attr-defined]
    }
    return attach_summary_contract(
        json_safe(snap),
        family="admin_state",
        read_model="admin_state_projection_v1",
        runtime=runtime,
    )
