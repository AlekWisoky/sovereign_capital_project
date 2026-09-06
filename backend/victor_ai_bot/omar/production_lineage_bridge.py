from __future__ import annotations

import inspect
from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity
from ..operator_intent import resolve_operator_intent

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _lineage_matches(
    outcome: Any, *, decision_id: str, correlation_id: str, opportunity_id: str
) -> bool:
    row = _dict(outcome)
    if _text(row.get("status")).lower() != "settled":
        return False
    if decision_id and _text(row.get("decision_id")) != decision_id:
        return False
    if correlation_id and _text(row.get("correlation_id")) != correlation_id:
        return False
    if opportunity_id and _text(row.get("opportunity_id")) != opportunity_id:
        return False
    return True


def _patch_omar_context() -> None:
    """Feed operator intent into OMAR without changing its authority boundary."""
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_omar_context", None)
    if original is None or getattr(original, "_operator_intent_patched", False):
        return

    def wrapped(self: Any, opp: Any, *, p_success: float, ev_wei: int):
        context = dict(original(self, opp, p_success=p_success, ev_wei=ev_wei) or {})
        intent = resolve_operator_intent(self)
        goal = _dict(intent.get("goal"))
        recommendation = _dict(intent.get("ai_recommendation"))
        context.update(
            {
                "aggression_mode": _text(intent.get("aggression_mode")) or "balanced",
                "risk_multiplier": float(intent.get("risk_multiplier") or 1.0),
                "goal_horizon_compatibility": float(goal.get("horizon_compatibility") or 1.0),
                "goal_target_amount": _text(goal.get("target_amount")),
                "goal_id": _text(goal.get("goal_id")),
                "goal_revision": int(goal.get("goal_revision") or 1),
                "ai_recommendation_action": _text(recommendation.get("action")) or "none",
                "ai_recommendation_posture": _text(recommendation.get("posture")) or "none",
                "ai_recommendation_confidence": float(recommendation.get("confidence") or 0.0),
            }
        )
        return context

    wrapped._operator_intent_patched = True
    RuntimeDecisionFacade._omar_context = wrapped


def _patch_decision_identity() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        intent = resolve_operator_intent(self)
        ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(
                getattr(getattr(self, "cfg", None), "chain", None).name
                if getattr(getattr(self, "cfg", None), "chain", None) is not None
                else "chain"
            ),
            current_block=int(current_block),
            operator_intent=intent,
        )
        return original(self, opp, decision, current_block=current_block)

    wrapped._production_identity_patched = True
    RuntimeDecisionFacade._apply_omar_to_candidate = wrapped


def _patch_execution_identity() -> None:
    from victor_ai_bot.runtime_services.execution_service import ExecutionService

    original = getattr(ExecutionService, "handle_post_execute_bookkeeping", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    async def wrapped(*args: Any, **kwargs: Any):
        signature = inspect.signature(original)
        bound = signature.bind_partial(*args, **kwargs)
        runtime = bound.arguments.get("runtime")
        opp = bound.arguments.get("opp") or bound.arguments.get("opportunity")
        decision = bound.arguments.get("decision")
        result = bound.arguments.get("result")
        if runtime is not None and opp is not None:
            try:
                ensure_decision_identity(
                    opp,
                    decision,
                    chain_name=_text(
                        getattr(getattr(runtime, "cfg", None), "chain", None).name
                        if getattr(getattr(runtime, "cfg", None), "chain", None) is not None
                        else "chain"
                    ),
                    current_block=int(bound.arguments.get("bn") or 0),
                    operator_intent=resolve_operator_intent(runtime),
                )
                lineage = lineage_from_opportunity(opp)
                if result is not None:
                    plan = _dict(getattr(result, "plan", None))
                    plan["canonical_lineage"] = dict(lineage)
                    plan["canonical_decision_id"] = lineage["decision_id"]
                    plan["correlation_id"] = lineage["correlation_id"]
                    plan["operator_intent_fingerprint"] = lineage["operator_intent_fingerprint"]
                    result.plan = plan
            except _SAFE:
                pass
        return await original(*args, **kwargs)

    wrapped._production_identity_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _patch_settlement_resolution() -> None:
    from victor_ai_bot.omar import lifecycle_bridge

    original = getattr(lifecycle_bridge, "_canonical_settled_outcome", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(runtime: Any, result: Any, opp: Any):
        outcome = original(runtime, result, opp)
        if outcome is None:
            return None
        lineage = lineage_from_opportunity(opp)
        if not _lineage_matches(
            outcome,
            decision_id=lineage["decision_id"],
            correlation_id=lineage["correlation_id"],
            opportunity_id=_text(getattr(opp, "id", "")),
        ):
            return None
        try:
            if isinstance(outcome, dict):
                outcome["operator_intent_fingerprint"] = lineage["operator_intent_fingerprint"]
        except (AttributeError, TypeError):
            pass
        return outcome

    wrapped._production_identity_patched = True
    lifecycle_bridge._canonical_settled_outcome = wrapped


def install_production_lineage_bridge() -> None:
    try:
        _patch_omar_context()
        _patch_decision_identity()
        _patch_execution_identity()
        _patch_settlement_resolution()
    except _SAFE:
        return
