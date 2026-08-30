from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


_VALID_AGGRESSION = {"conservative", "balanced", "aggressive"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _controls(runtime: Any) -> Any:
    try:
        command_center = getattr(runtime, "_cc", None)
        return getattr(command_center, "controls", None)
    except (AttributeError, TypeError, ValueError):
        return None


def _aggression_and_risk(runtime: Any) -> tuple[str, float]:
    controls = _controls(runtime)
    aggression = _text(getattr(controls, "aggression_mode", "balanced")).lower()
    if aggression not in _VALID_AGGRESSION:
        aggression = "balanced"
    risk_multiplier = max(
        0.10,
        min(1.0, _number(getattr(controls, "risk_multiplier", 1.0), 1.0)),
    )
    return aggression, round(risk_multiplier, 6)


def _recommendation(runtime: Any) -> dict[str, Any]:
    """Read the latest operator-facing AI recommendation without authority."""
    for attr in (
        "_ai_recommendation",
        "_recommendation",
        "_launch_recommendation",
    ):
        try:
            value = getattr(runtime, attr, None)
            if isinstance(value, Mapping):
                return dict(value)
        except (AttributeError, TypeError, ValueError):
            continue
    return {}


def _goal_state(runtime: Any) -> dict[str, Any]:
    try:
        service = getattr(runtime, "_wealth_goal_service", None)
        if service is None or not hasattr(service, "state"):
            return {}
        raw = service.state(runtime)
        if not isinstance(raw, Mapping):
            return {}
        return dict(raw.get("state") or raw)
    except (AttributeError, KeyError, TypeError, ValueError):
        return {}


def _goal_snapshot(goal_state: Mapping[str, Any]) -> dict[str, Any]:
    goal = _dict(goal_state.get("goal"))
    target_amount = goal.get("target_amount") or goal.get("target_wealth_usd") or goal.get(
        "target_capital_usd"
    )
    target_return_pct = goal.get("target_return_percentage") or goal.get("target_return_pct")
    timeframe_days = goal.get("timeframe_days")
    if not timeframe_days and goal.get("time_horizon_seconds"):
        timeframe_days = _number(goal.get("time_horizon_seconds")) / 86400.0
    meta = _dict(goal_state.get("meta"))
    return {
        "target_amount": _text(target_amount),
        "target_return_pct": round(_number(target_return_pct), 6),
        "timeframe_days": round(_number(timeframe_days), 6),
        "goal_id": _text(meta.get("active_goal_id")),
        "goal_revision": int(_number(meta.get("goal_revision"), 1)),
        "current_return_pct": round(
            _number(goal_state.get("currentReturnPct") or goal_state.get("current_return_pct")),
            6,
        ),
        "drawdown_pct": round(
            _number(goal_state.get("drawdownPct") or goal_state.get("drawdown_pct")),
            6,
        ),
    }


def _recommendation_snapshot(recommendation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(recommendation),
        "action": _text(recommendation.get("action")),
        "posture": _text(recommendation.get("posture")),
        "confidence": round(_number(recommendation.get("confidence")), 6),
        "source": _text(recommendation.get("source") or recommendation.get("kind")),
    }


def resolve_operator_intent(runtime: Any) -> dict[str, Any]:
    """Return effective human/goal/recommendation intent, not execution authority."""
    aggression, risk_multiplier = _aggression_and_risk(runtime)
    return {
        "aggression_mode": aggression,
        "risk_multiplier": risk_multiplier,
        "goal": _goal_snapshot(_goal_state(runtime)),
        "ai_recommendation": _recommendation_snapshot(_recommendation(runtime)),
        "authority": "operator_intent_only",
    }


def intent_fingerprint(intent: Mapping[str, Any]) -> str:
    """Stable attribution fingerprint; never use it as the learning state key."""
    payload = json.dumps(dict(intent), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
