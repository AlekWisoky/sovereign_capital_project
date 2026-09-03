from __future__ import annotations

from typing import Any, Dict


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_INT_EXCEPTIONS = (TypeError, ValueError, OverflowError)

GOAL_PATCH_FIELDS = frozenset(
    {
        "target_return_percentage",
        "target_return_pct",
        "time_horizon_seconds",
        "timeframe_days",
        "risk_tolerance",
        "max_drawdown_pct",
        "capital_commitment_pct",
    }
)

_CANONICAL_GOAL_FIELDS = (
    "target_return_percentage",
    "time_horizon_seconds",
    "risk_tolerance",
    "max_drawdown_pct",
    "capital_commitment_pct",
)


def clamp_float(x: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        v = float(default)
    return max(float(lo), min(float(hi), float(v)))


def clamp_int(x: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(x)
    except _SAFE_INT_EXCEPTIONS:
        v = int(default)
    return max(int(lo), min(int(hi), int(v)))


def normalize_goal_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    risk = str((payload or {}).get("risk_tolerance") or "moderate").strip().lower()
    if risk not in {"conservative", "moderate", "aggressive"}:
        risk = "moderate"
    timeframe_days = clamp_int(
        (payload or {}).get("timeframe_days")
        or ((payload or {}).get("time_horizon_seconds", 0) // 86400),
        1,
        365,
        30,
    )
    target_return_pct = clamp_float(
        (payload or {}).get("target_return_percentage") or (payload or {}).get("target_return_pct"),
        0.5,
        100.0,
        8.0,
    )
    max_drawdown_pct = clamp_float((payload or {}).get("max_drawdown_pct"), 1.0, 50.0, 10.0)
    capital_commitment_pct = clamp_float(
        (payload or {}).get("capital_commitment_pct"), 1.0, 100.0, 25.0
    )
    return {
        "target_return_percentage": target_return_pct,
        "target_return_pct": target_return_pct,
        "time_horizon_seconds": timeframe_days * 86400,
        "timeframe_days": timeframe_days,
        "risk_tolerance": risk,
        "max_drawdown_pct": max_drawdown_pct,
        "capital_commitment_pct": capital_commitment_pct,
    }


def resolve_goal_patch_payload(
    payload: Dict[str, Any], *, current_goal: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    current = dict(current_goal or {})
    normalized = normalize_goal_payload(payload)

    def _current_float(*keys: str, default: float) -> float:
        for key in keys:
            if key in current and current[key] is not None:
                try:
                    return float(current[key])
                except _SAFE_FLOAT_EXCEPTIONS:
                    continue
        return float(default)

    def _current_int(*keys: str, default: int) -> int:
        for key in keys:
            if key in current and current[key] is not None:
                try:
                    return int(current[key])
                except _SAFE_INT_EXCEPTIONS:
                    continue
        return int(default)

    def _current_str(*keys: str, default: str) -> str:
        for key in keys:
            if key in current and current[key] is not None:
                value = str(current[key]).strip()
                if value:
                    return value
        return str(default)

    update_target = "target_return_percentage" in payload or "target_return_pct" in payload
    update_horizon = "time_horizon_seconds" in payload or "timeframe_days" in payload
    update_risk = "risk_tolerance" in payload
    update_drawdown = "max_drawdown_pct" in payload
    update_commitment = "capital_commitment_pct" in payload

    target_return_percentage = (
        float(normalized["target_return_percentage"])
        if update_target
        else _current_float(
            "target_return_percentage",
            "target_return_pct",
            default=float(normalized["target_return_percentage"]),
        )
    )
    time_horizon_seconds = (
        int(normalized["time_horizon_seconds"])
        if update_horizon
        else _current_int("time_horizon_seconds", default=int(normalized["time_horizon_seconds"]))
    )
    risk_tolerance = (
        str(normalized["risk_tolerance"])
        if update_risk
        else _current_str("risk_tolerance", default=str(normalized["risk_tolerance"]))
    )
    max_drawdown_pct = (
        float(normalized["max_drawdown_pct"])
        if update_drawdown
        else _current_float("max_drawdown_pct", default=float(normalized["max_drawdown_pct"]))
    )
    capital_commitment_pct = (
        float(normalized["capital_commitment_pct"])
        if update_commitment
        else _current_float(
            "capital_commitment_pct", default=float(normalized["capital_commitment_pct"])
        )
    )

    timeframe_days = max(1, int(round(time_horizon_seconds / 86400.0)))
    return {
        "target_return_percentage": target_return_percentage,
        "target_return_pct": target_return_percentage,
        "time_horizon_seconds": time_horizon_seconds,
        "timeframe_days": timeframe_days,
        "risk_tolerance": risk_tolerance,
        "max_drawdown_pct": max_drawdown_pct,
        "capital_commitment_pct": capital_commitment_pct,
    }


def goal_patch_requested(payload: Dict[str, Any]) -> bool:
    return any(str(key) in GOAL_PATCH_FIELDS for key in dict(payload or {}).keys())


def goal_patch_changes_state(
    resolved: Dict[str, Any], *, current_goal: Dict[str, Any] | None = None
) -> bool:
    current = resolve_goal_patch_payload({}, current_goal=dict(current_goal or {}))
    for field in _CANONICAL_GOAL_FIELDS:
        if current.get(field) != resolved.get(field):
            return True
    return False


def recommend_goal(
    *, current_return_pct: float, risk_tolerance: str = "moderate", previous_target_pct: float = 0.0
) -> Dict[str, Any]:
    risk = str(risk_tolerance or "moderate").lower()
    base_target = 6.0 if risk == "conservative" else (10.0 if risk == "moderate" else 14.0)
    baseline_timeframe = 30 if risk == "conservative" else (21 if risk == "moderate" else 14)
    if previous_target_pct > 0 and current_return_pct >= previous_target_pct:
        next_target = max(previous_target_pct + 2.0, round(previous_target_pct * 1.2, 2))
    else:
        next_target = max(
            base_target, round(max(current_return_pct + 2.0, previous_target_pct or 0.0), 2)
        )
    max_drawdown = 8.0 if risk == "conservative" else (12.0 if risk == "moderate" else 18.0)
    commitment = 22.0 if risk == "conservative" else (35.0 if risk == "moderate" else 50.0)
    return normalize_goal_payload(
        {
            "target_return_pct": next_target,
            "timeframe_days": baseline_timeframe,
            "risk_tolerance": risk,
            "max_drawdown_pct": max_drawdown,
            "capital_commitment_pct": commitment,
        }
    )
