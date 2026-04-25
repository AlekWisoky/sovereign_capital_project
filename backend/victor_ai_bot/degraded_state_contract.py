from __future__ import annotations

import time
from typing import Any, Dict


def counted_bucket() -> Dict[str, Any]:
    return {"count": 0, "code": "", "degraded": False}


def init_counted_runtime(*, buckets: tuple[str, ...]) -> Dict[str, Any]:
    state: Dict[str, Any] = {name: counted_bucket() for name in buckets}
    state["degraded"] = False
    return state


def mark_counted_runtime(runtime: Dict[str, Any], bucket: str, code: str) -> None:
    entry = runtime.get(bucket)
    if not isinstance(entry, dict):
        entry = counted_bucket()
        runtime[bucket] = entry
    entry["count"] = int(entry.get("count") or 0) + 1
    entry["code"] = str(code or "")
    entry["degraded"] = True
    runtime["degraded"] = True


def status_bucket(*, include_action: bool = False, include_field: bool = False) -> Dict[str, Any]:
    bucket: Dict[str, Any] = {
        "ok": True,
        "last_error_code": "",
        "last_error": "",
        "last_ts": 0.0,
    }
    if include_action:
        bucket["last_action"] = ""
    if include_field:
        bucket["last_field"] = ""
    return bucket


def reset_status_bucket(
    bucket: Dict[str, Any], *, include_action: bool = False, include_field: bool = False
) -> None:
    bucket.clear()
    bucket.update(status_bucket(include_action=include_action, include_field=include_field))


def mark_status_bucket(
    bucket: Dict[str, Any],
    *,
    ok: bool,
    code: str = "",
    error: str = "",
    action: str = "",
    field: str = "",
    sticky_failure: bool = True,
) -> None:
    if bool(ok) and sticky_failure and not bool(bucket.get("ok", True)):
        bucket["last_ts"] = float(time.time())
        return
    bucket["ok"] = bool(ok)
    bucket["last_error_code"] = str(code or "")
    bucket["last_error"] = str(error or "")[:400]
    if "last_action" in bucket:
        bucket["last_action"] = str(action or "")
    if "last_field" in bucket:
        bucket["last_field"] = str(field or "")
    bucket["last_ts"] = float(time.time())


def status_runtime(**buckets: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "degraded": not all(bool(bucket.get("ok", True)) for bucket in buckets.values()),
        **{name: dict(bucket) for name, bucket in buckets.items()},
    }


def decision_contract(
    *,
    phase: str,
    reason_code: str,
    degraded: bool = False,
    blocked: bool = False,
    denied: bool = False,
    sticky_cycle: bool = False,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    code = str(reason_code or ("ok" if not (degraded or blocked or denied) else "unknown"))
    status = "ok"
    if denied:
        status = "denied"
    elif blocked:
        status = "blocked"
    elif degraded:
        status = "degraded"
    return {
        "phase": str(phase or "runtime"),
        "status": status,
        "reason_code": code,
        "degraded": bool(degraded or blocked or denied),
        "blocked": bool(blocked),
        "denied": bool(denied),
        "sticky_cycle": bool(sticky_cycle),
        "details": dict(details or {}),
    }


def attach_state_contract(
    payload: Dict[str, Any] | None,
    *,
    phase: str,
    reason_code: str,
    degraded: bool = False,
    blocked: bool = False,
    denied: bool = False,
    sticky_cycle: bool = False,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    out = dict(payload or {})
    contract = decision_contract(
        phase=phase,
        reason_code=reason_code,
        degraded=degraded,
        blocked=blocked,
        denied=denied,
        sticky_cycle=sticky_cycle,
        details=details,
    )
    out.setdefault("reason_code", contract["reason_code"])
    out["degraded"] = bool(out.get("degraded", False) or contract["degraded"])
    out["stateContract"] = contract
    return out


def contract_from_surface(
    payload: Dict[str, Any] | None,
    *,
    phase: str,
    default_reason: str = "ok",
    sticky_cycle: bool = False,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    surface = dict(payload or {})
    existing = (
        dict(surface.get("stateContract") or {})
        if isinstance(surface.get("stateContract"), dict)
        else {}
    )
    reason_code = str(
        surface.get("reason_code")
        or surface.get("reason")
        or surface.get("error")
        or existing.get("reason_code")
        or default_reason
        or "ok"
    )
    status = str(surface.get("status") or existing.get("status") or "").strip().lower()
    ok_value = surface.get("ok") if "ok" in surface else existing.get("status") == "ok"
    blocked = bool(
        surface.get("blocked", False)
        or surface.get("blockedAutoTrading", False)
        or existing.get("blocked", False)
    )
    denied = bool(surface.get("denied", False) or existing.get("denied", False))
    degraded = bool(surface.get("degraded", False) or existing.get("degraded", False))
    if status in {"blocked", "dropped", "paused"}:
        blocked = True
    if status in {"denied"}:
        denied = True
    if not degraded:
        degraded = bool(blocked or denied)
        if ok_value is False and not blocked and not denied:
            degraded = True
        if status in {"degraded", "failed", "unavailable"}:
            degraded = True
    if reason_code in {"", "ok"} and degraded:
        reason_code = str(default_reason or status or existing.get("reason_code") or "degraded")
    merged_details = dict(existing.get("details") or {})
    merged_details.update(dict(details or {}))
    return decision_contract(
        phase=str(existing.get("phase") or phase or "runtime"),
        reason_code=reason_code,
        degraded=degraded,
        blocked=blocked,
        denied=denied,
        sticky_cycle=bool(existing.get("sticky_cycle", False) or sticky_cycle),
        details=merged_details,
    )


def normalize_surface_contract(
    payload: Dict[str, Any] | None,
    *,
    phase: str,
    default_reason: str = "ok",
    sticky_cycle: bool = False,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    out = dict(payload or {})
    contract = contract_from_surface(
        out,
        phase=phase,
        default_reason=default_reason,
        sticky_cycle=sticky_cycle,
        details=details,
    )
    out.setdefault("reason_code", contract["reason_code"])
    out["degraded"] = bool(out.get("degraded", False) or contract["degraded"])
    out["stateContract"] = contract
    return out


def aggregate_state_contracts(
    *, phase: str, contracts: Dict[str, Dict[str, Any]] | None = None, sticky_cycle: bool = True
) -> Dict[str, Any]:
    items = {str(name): dict(contract or {}) for name, contract in dict(contracts or {}).items()}
    first_non_ok: tuple[str, Dict[str, Any]] | None = None
    for name, contract in items.items():
        if str(contract.get("status") or "ok") != "ok":
            first_non_ok = (name, contract)
            break
    if first_non_ok is None:
        return decision_contract(
            phase=phase,
            reason_code="ok",
            degraded=False,
            blocked=False,
            denied=False,
            sticky_cycle=sticky_cycle,
            details={"sources": items},
        )
    name, contract = first_non_ok
    return decision_contract(
        phase=phase,
        reason_code=str(contract.get("reason_code") or f"{name}:degraded"),
        degraded=bool(contract.get("degraded", False)),
        blocked=bool(contract.get("blocked", False)),
        denied=bool(contract.get("denied", False)),
        sticky_cycle=sticky_cycle,
        details={"source": name, "sources": items},
    )
