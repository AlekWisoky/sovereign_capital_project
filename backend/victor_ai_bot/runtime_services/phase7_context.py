from __future__ import annotations

from typing import Any, Dict

from ..identity import identity_from
from ..omar.operator_intent import capture_operator_intent
from .runtime_context import build_runtime_access_snapshot


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _action_from(decision: Any, opp: Any, result: Any = None) -> str:
    for source in (decision, result, opp):
        if source is None:
            continue
        for name in ("action", "selected_action"):
            value = getattr(source, name, None)
            if value not in (None, ""):
                return str(value)
        meta = getattr(source, "meta", None)
        if isinstance(meta, dict):
            brain = _safe_dict(meta.get("brain"))
            for value in (meta.get("action"), brain.get("action"), brain.get("selected_action")):
                if value not in (None, ""):
                    return str(value)
    return ""


def build_phase7_execution_context(
    runtime: Any,
    opp: Any,
    decision: Any,
    *,
    latency_ms: int = 0,
    result: Any = None,
) -> Dict[str, Any]:
    """Capture the Phase 7 decision-time context once for execution and learning.

    This is an attribution snapshot, not an authority layer. It deliberately
    reuses the canonical runtime-access snapshot and operator-intent snapshot;
    governance, capital authority, and execution gates remain authoritative.
    """
    access = build_runtime_access_snapshot(runtime)
    intent = capture_operator_intent(runtime, decision=decision)
    identity = identity_from(decision) or identity_from(opp) or identity_from(result)
    identity_payload = identity.to_dict() if identity is not None else {}
    action = _action_from(decision, opp, result)
    return {
        "schema_version": 1,
        "decision": {
            "decision_id": str(identity_payload.get("decision_id") or ""),
            "correlation_id": str(identity_payload.get("correlation_id") or ""),
            "action": action,
            "policy_version": str(
                getattr(decision, "policy_version", "")
                or _safe_dict(getattr(decision, "metadata", None)).get("policy_version")
                or ""
            ),
        },
        "execution": {
            "execution_id": str(identity_payload.get("execution_id") or ""),
            "latency_ms": int(max(0, int(latency_ms or 0))),
        },
        "operator_intent": intent.to_dict(),
        "runtime_access": {
            "chain_id": int(access.chain_id),
            "regime": str(access.regime),
            "public_mode": bool(access.public_mode),
            "force_send_mode": str(access.force_send_mode),
            "wealth_goal": dict(access.wealth_goal),
            "drawdown_state": dict(access.drawdown_state),
            "kill_switch_state": dict(access.kill_switch_state),
            "treasury_state": dict(access.treasury_state),
        },
        "latency": {
            "observed_ms": int(max(0, int(latency_ms or 0))),
            "hot_path_snapshot": True,
        },
    }


def attach_phase7_execution_context(target: Any, context: Dict[str, Any]) -> Any:
    """Attach a read-only attribution snapshot to mutable execution metadata."""
    if target is None:
        return target
    payload = dict(context or {})
    try:
        plan = getattr(target, "plan", None)
        if isinstance(plan, dict):
            plan["phase7_context"] = payload
            decision = _safe_dict(payload.get("decision"))
            plan.setdefault("lineage", {}).update(
                {
                    "decision_id": str(decision.get("decision_id") or ""),
                    "correlation_id": str(decision.get("correlation_id") or ""),
                    "action": str(decision.get("action") or ""),
                }
            )
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        meta = getattr(target, "meta", None)
        if isinstance(meta, dict):
            meta["phase7_context"] = payload
    except (AttributeError, TypeError, ValueError):
        pass
    return target
