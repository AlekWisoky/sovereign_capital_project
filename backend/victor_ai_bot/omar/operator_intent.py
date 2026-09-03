from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class OperatorIntentSnapshot:
    """Immutable decision-time snapshot of human and goal intent.

    This is context, not authority: governance, capital authority, and execution
    gates remain the final arbiters. The snapshot exists so OMAR can later learn
    which operator posture and recommendation produced an observed outcome.
    """

    control_mode: str = ""
    aggression_mode: str = "balanced"
    brain_mode: str = "off"
    risk_multiplier: float = 1.0
    force_send_mode: str = ""
    force_gas_mode: str = ""
    desired_wealth_goal: Dict[str, Any] = field(default_factory=dict)
    ai_recommendation: Dict[str, Any] = field(default_factory=dict)
    source: str = "runtime"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def capture_operator_intent(runtime: Any, decision: Any = None) -> OperatorIntentSnapshot:
    """Capture operator controls, wealth goal, and decision recommendation."""
    controls = None
    try:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
    except (AttributeError, TypeError, ValueError):
        controls = None

    goal: Dict[str, Any] = {}
    try:
        service = getattr(runtime, "_wealth_goal_service", None)
        if service is not None and hasattr(service, "state"):
            goal = _dict(service.state(runtime))
    except (AttributeError, KeyError, TypeError, ValueError):
        goal = {}

    risk_multiplier = 1.0
    try:
        from ..caq_kds.bus import BUS

        snapshot = _dict(BUS.snapshot())
        command = _dict(snapshot.get("command"))
        command_data = _dict(command.get("data"))
        risk_multiplier = max(0.10, min(1.0, _number(command_data.get("risk_multiplier"), 1.0)))
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        risk_multiplier = 1.0

    recommendation: Dict[str, Any] = {}
    if decision is not None:
        try:
            recommendation = {
                "action": _text(getattr(decision, "action", "")),
                "opp_id": _text(getattr(decision, "opp_id", "")),
                "route_id": _text(getattr(decision, "route_id", "")),
                "size_mult": _number(getattr(decision, "size_mult", 1.0), 1.0),
                "borrow_mult": _number(getattr(decision, "borrow_mult", 1.0), 1.0),
                "gas_mode": _text(getattr(decision, "gas_mode", "")),
                "p_success": _number(getattr(decision, "p_success", 0.0), 0.0),
                "ev_wei": int(getattr(decision, "ev_wei", 0) or 0),
                "reason": _text(getattr(decision, "reason", "")),
                "rl_state": _text(getattr(decision, "rl_state", "")),
                "rl_action_index": int(getattr(decision, "rl_action_index", -1) or -1),
            }
        except (AttributeError, TypeError, ValueError, OverflowError):
            recommendation = {}

    return OperatorIntentSnapshot(
        control_mode=_text(getattr(controls, "control_mode", "")),
        aggression_mode=_text(getattr(controls, "aggression_mode", "balanced")) or "balanced",
        brain_mode=_text(getattr(controls, "brain_mode", "")),
        risk_multiplier=risk_multiplier,
        force_send_mode=_text(getattr(controls, "force_send_mode", "")),
        force_gas_mode=_text(getattr(controls, "force_gas_mode", "")),
        desired_wealth_goal=goal,
        ai_recommendation=recommendation,
    )
