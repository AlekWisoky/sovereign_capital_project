from __future__ import annotations

from typing import Any, Dict


_VALID_LEVELS = {"LOW", "MODERATE", "HIGH", "MAXIMUM"}


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _level_rank(level: str) -> int:
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "MAXIMUM": 3}
    return int(order.get(str(level or "LOW").upper(), 0))


def treasury_governance_view(treasury_state: Dict[str, Any] | None) -> Dict[str, Any]:
    state = _safe_dict(treasury_state)
    governance = _safe_dict(state.get("governance"))
    aggressiveness = _safe_dict(state.get("aggressiveness"))

    raw_level = str(
        governance.get("raw_aggressiveness_level")
        or aggressiveness.get("aggressiveness_level")
        or state.get("effective_aggressiveness_level")
        or "LOW"
    ).upper()

    effective_level = str(
        governance.get("effective_aggressiveness_level")
        or state.get("effective_aggressiveness_level")
        or raw_level
    ).upper()

    raw_cap = _safe_float(
        governance.get("raw_borrow_mult_target_cap"),
        _safe_float(
            state.get("borrow_mult_target_cap"),
            _safe_float(aggressiveness.get("borrow_mult_target_cap"), 1.0),
        ),
    )
    if raw_cap <= 0:
        raw_cap = 1.0

    effective_cap = _safe_float(
        governance.get("effective_borrow_mult_target_cap"),
        _safe_float(
            state.get("effective_borrow_mult_target_cap"),
            _safe_float(aggressiveness.get("effective_borrow_mult_target_cap"), raw_cap),
        ),
    )
    if effective_cap <= 0:
        effective_cap = raw_cap

    blocked = _safe_bool(governance.get("blocked", False))
    ok = _safe_bool(governance.get("ok", not blocked))
    if blocked:
        ok = False

    reason = str(governance.get("reason") or ("ok" if ok else "treasury_governance_blocked"))
    reason_codes = governance.get("reason_codes") or ([] if ok else [reason])
    if not isinstance(reason_codes, list):
        reason_codes = [str(reason)] if not ok else []

    approved_by_human = _safe_bool(
        governance.get("approved_by_human")
        or state.get("approved_by_human")
        or state.get("governance_approved")
    )
    max_without = str(
        governance.get("max_aggressiveness_without_approval")
        or state.get("max_aggressiveness_without_approval")
        or "HIGH"
    ).upper()
    if max_without not in _VALID_LEVELS:
        max_without = "HIGH"

    allow_maximum = _safe_bool(governance.get("allow_maximum") or state.get("allow_maximum"))

    if not ok and effective_cap > 1.0:
        effective_cap = 1.0

    return {
        "ok": ok,
        "blocked": not ok,
        "reason": reason,
        "reason_code": reason,
        "reason_codes": [str(x) for x in reason_codes],
        "raw_aggressiveness_level": raw_level,
        "effective_aggressiveness_level": effective_level,
        "raw_borrow_mult_target_cap": float(raw_cap),
        "effective_borrow_mult_target_cap": float(effective_cap),
        "approved_by_human": approved_by_human,
        "max_aggressiveness_without_approval": max_without,
        "allow_maximum": allow_maximum,
        "urgency_factor": _safe_float(
            governance.get("urgency_factor"), aggressiveness.get("urgency_factor") or 0.0
        ),
        "suggested_next_action": str(
            governance.get("suggested_next_action")
            or ("continue_treasury_plan" if ok else "refresh_treasury_governance")
        ),
    }


__all__ = ["treasury_governance_view"]
