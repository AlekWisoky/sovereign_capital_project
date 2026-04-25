from __future__ import annotations
import os
import logging
from typing import Any, List, Tuple

log = logging.getLogger("victor.config")

_SAFE_ITER_EXCEPTIONS = (TypeError, ValueError, RuntimeError)
_SAFE_INT_EXCEPTIONS = (TypeError, ValueError, OverflowError)


def _coerce_listlike(x: Any, *, field: str) -> Tuple[List[Any], List[str]]:
    if x is None:
        return [], []
    if isinstance(x, list):
        return list(x), []
    if isinstance(x, (tuple, set)):
        return list(x), []
    if isinstance(x, str):
        return [], [f"WARN: {field} is not list-like"]
    try:
        return list(x), []
    except _SAFE_ITER_EXCEPTIONS:
        return [], [f"WARN: {field} is not list-like"]


def _coerce_intish(x: Any, *, default: int = 0) -> Tuple[int, bool]:
    if isinstance(x, bool):
        return int(x), False
    if isinstance(x, int):
        return x, False
    if isinstance(x, float):
        if x != x or x in {float('inf'), float('-inf')}:
            return int(default), True
        return int(x), False
    if isinstance(x, bytes):
        try:
            return int(x.decode("utf-8", errors="ignore") or default), False
        except _SAFE_INT_EXCEPTIONS:
            return int(default), True
    if isinstance(x, str):
        try:
            return int(x or default), False
        except _SAFE_INT_EXCEPTIONS:
            return int(default), True
    return int(default), True


def validate_config(cfg: Any) -> Tuple[bool, List[str]]:
    """Return (ok, issues). If ok=False, issues contain fatal errors."""
    issues: List[str] = []
    chain = getattr(cfg, "chain", None)
    exec_cfg = getattr(cfg, "execution", None)
    safety = getattr(cfg, "safety", None)

    rpc_read, warns = _coerce_listlike(getattr(chain, "rpc_read", []), field="chain.rpc_read")
    issues.extend(warns)
    if not rpc_read:
        issues.append("chain.rpc_read is empty (scanner cannot run)")
    # In private mode we still may need rpc_send for receipt polling / gas, but dry-run can tolerate.
    rpc_send, warns = _coerce_listlike(getattr(chain, "rpc_send", []), field="chain.rpc_send")
    issues.extend(warns)
    if not rpc_send and not bool(getattr(exec_cfg, "dry_run", True)):
        issues.append("chain.rpc_send is empty but execution.dry_run=false (cannot send txs)")

    send_mode = str(getattr(exec_cfg, "send_mode", "public") or "public")
    rpc_private, warns = _coerce_listlike(getattr(chain, "rpc_private", []), field="chain.rpc_private")
    issues.extend(warns)
    if send_mode in {"private", "protected_rpc"} and not rpc_private:
        # warning only
        issues.append(
            "WARN: send_mode is private/protected_rpc but chain.rpc_private is empty (will fallback to rpc_send)"
        )

    # Borrow sizing sanity
    base_borrow_i, invalid_base_borrow = _coerce_intish(
        getattr(exec_cfg, "base_borrow_amount", "0"),
        default=0,
    )
    if invalid_base_borrow:
        issues.append("WARN: execution.base_borrow_amount is not a valid integer string")

    if base_borrow_i <= 0:
        # allow if any configured pair has amount_in
        found = False
        for lst_name in ("v3_pairs", "curve_pools", "balancer_pools"):
            pools, warns = _coerce_listlike(getattr(chain, lst_name, []), field=f"chain.{lst_name}")
            issues.extend(warns)
            for p in pools:
                if not isinstance(p, dict):
                    continue
                amount_in, invalid_amount = _coerce_intish(p.get("amount_in", "0"), default=0)
                if invalid_amount:
                    continue
                if amount_in > 0:
                    found = True
                    break
            if found:
                break
        if not found:
            issues.append(
                "WARN: amount_in resolves to 0 (set execution.base_borrow_amount or any pool amount_in)"
            )

    # Live-mode requirements
    if not bool(getattr(exec_cfg, "dry_run", True)):
        executor = str(getattr(exec_cfg, "executor_address", "") or "")
        if not executor:
            issues.append("execution.executor_address missing for live mode")
        key_env = str(
            getattr(exec_cfg, "private_key_env", "VICTOR_PRIVATE_KEY") or "VICTOR_PRIVATE_KEY"
        )
        if not os.environ.get(key_env, "").strip():
            issues.append(f"missing private key env var: {key_env}")

    # Safety sanity
    if safety is not None:
        _, invalid_slippage = _coerce_intish(getattr(safety, "slippage_bps", 50), default=50)
        if invalid_slippage:
            issues.append("WARN: safety.slippage_bps is not int")

    # Determine fatal vs warnings
    fatals = [x for x in issues if not x.startswith("WARN:")]
    ok = len(fatals) == 0
    return ok, issues


def enforce_or_warn(cfg: Any) -> None:
    strict = os.environ.get("VICTOR_VALIDATE_CONFIG", "").strip() == "1"
    ok, issues = validate_config(cfg)
    for it in issues:
        if it.startswith("WARN:"):
            log.warning(it.replace("WARN: ", ""))
        else:
            log.error(it)
    if strict and not ok:
        raise ValueError("config_validation_failed")
