from __future__ import annotations
from typing import Any, Mapping, Sequence
from .jsonsafe import _BIGINT_KEY_HINTS

REQUIRED_METRICS_KEYS = {
    "flashLoans",
    "attempted",
    "succeeded",
    "failed",
    "last_block",
    "scan_ms",
    "last_error",
    "last_submitted_block",
    "gas_mode",
    "send_mode",
    "realized_profit_raw",
    "efficiency_pct",
    "success_rate_pct",
}

REQUIRED_OPPORTUNITY_KEYS = {
    "id",
    "chain",
    "strategy",
    "expected_profit_raw",
    "expected_profit_usd",
    "route",
    "min_outs",
    "can_execute",
    "created_at_ms",
    "meta",
}


def _is_mapping(x: Any) -> bool:
    return isinstance(x, Mapping)


def _is_seq(x: Any) -> bool:
    return isinstance(x, (list, tuple))


def is_bigint_key(k: str) -> bool:
    lk = k.lower()
    return any(h in lk for h in _BIGINT_KEY_HINTS)


def validate_bigint_strings(obj: Any, *, _key: str | None = None, _path: str = "$") -> None:
    """Ensures all bigint-like numeric fields serialize as strings (policy: key-hint based)."""
    if _is_mapping(obj):
        for k, v in obj.items():
            ks = str(k)
            validate_bigint_strings(v, _key=ks, _path=f"{_path}.{ks}")
        return
    if _is_seq(obj):
        for i, v in enumerate(obj):
            validate_bigint_strings(v, _key=_key, _path=f"{_path}[{i}]")
        return
    if _key and is_bigint_key(_key):
        # allow hex strings, decimal strings, or None
        if isinstance(obj, int) and not isinstance(obj, bool):
            raise ValueError(f"bigint field must be string, got int at {_path}")
    # otherwise ok


def validate_runtime_state(state: Mapping[str, Any]) -> None:
    # top-level
    for k in ("chain", "opportunities", "metrics", "rpc"):
        if k not in state:
            raise ValueError(f"missing key: {k}")

    if not isinstance(state["chain"], str):
        raise ValueError("chain must be string")

    opps = state["opportunities"]
    if not isinstance(opps, list):
        raise ValueError("opportunities must be list")

    metrics = state["metrics"]
    if not isinstance(metrics, Mapping):
        raise ValueError("metrics must be object")

    missing = REQUIRED_METRICS_KEYS.difference(metrics.keys())
    if missing:
        raise ValueError(f"missing metrics keys: {sorted(missing)}")

    for o in opps:
        if not isinstance(o, Mapping):
            raise ValueError("opportunity must be object")
        miss = REQUIRED_OPPORTUNITY_KEYS.difference(o.keys())
        if miss:
            raise ValueError(f"missing opportunity keys: {sorted(miss)}")
        # string fields
        for sf in ("expected_profit_raw", "expected_profit_usd"):
            if not isinstance(o.get(sf), str):
                raise ValueError(f"{sf} must be string")
        # route
        rt = o.get("route")
        if not isinstance(rt, Mapping) or "legs" not in rt or not isinstance(rt["legs"], list):
            raise ValueError("route.legs must be list")
        # min_outs
        mo = o.get("min_outs")
        if not isinstance(mo, list) or any(not isinstance(x, str) for x in mo):
            raise ValueError("min_outs must be list[str]")

    validate_bigint_strings(state)
