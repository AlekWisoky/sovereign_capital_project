from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _text(value)


def intent_fingerprint(intent: Mapping[str, Any]) -> str:
    payload = json.dumps(_jsonable(intent), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def snapshot_operator_intent(runtime: Any, opp: Any, decision: Any | None) -> tuple[dict[str, Any], str]:
    """Capture immutable-at-decision operator intent for attribution.

    This is context, not authority. Governance, capital admission and execution
    remain authoritative. The returned structure is deep-copied so later
    operator changes cannot rewrite the historical decision's learning record.
    """
    controls = _dict(getattr(getattr(runtime, "_cc", None), "controls", None))
    if not controls:
        raw_controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if raw_controls is not None:
            for key in (
                "aggression_mode", "brain_mode", "defensive_mode", "control_mode",
                "auto_reinvest_enabled", "force_gas_mode", "force_send_mode",
            ):
                if hasattr(raw_controls, key):
                    controls[key] = getattr(raw_controls, key)

    goal = {}
    try:
        service = getattr(runtime, "_wealth_goal_service", None)
        if service is not None and hasattr(service, "state"):
            state = service.state(runtime)
            if isinstance(state, Mapping):
                goal = _dict(state.get("state"))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        goal = {}

    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    decision_meta = _dict(getattr(decision, "metadata", None)) if decision is not None else {}
    recommendation = _dict(
        brain.get("ai_recommendation")
        or brain.get("recommendation")
        or decision_meta.get("ai_recommendation")
        or decision_meta.get("recommendation")
    )

    intent = {
        "aggression_mode": _text(
            controls.get("aggression_mode") or brain.get("aggression_mode") or "balanced"
        ).lower(),
        "risk_multiplier": controls.get("risk_multiplier", brain.get("risk_multiplier")),
        "control_mode": _text(controls.get("control_mode") or ""),
        "brain_mode": _text(controls.get("brain_mode") or ""),
        "defensive_mode": bool(controls.get("defensive_mode", False)),
        "goal": {
            "target_amount": goal.get("targetAmount", goal.get("target_amount")),
            "timeframe_days": goal.get("timeframeDays", goal.get("timeframe_days")),
            "target_return_pct": goal.get("targetReturnPct", goal.get("target_return_pct")),
            "current_return_pct": goal.get("currentReturnPct", goal.get("current_return_pct")),
            "drawdown_pct": goal.get("drawdownPct", goal.get("drawdown_pct")),
        },
        "ai_recommendation": recommendation,
        "execution_preferences": {
            "force_gas_mode": _text(controls.get("force_gas_mode") or ""),
            "force_send_mode": _text(controls.get("force_send_mode") or ""),
        },
    }
    frozen = copy.deepcopy(_jsonable(intent))
    return frozen, intent_fingerprint(frozen)
