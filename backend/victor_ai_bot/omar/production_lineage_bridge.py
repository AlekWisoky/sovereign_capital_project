from __future__ import annotations

import inspect
import os
from typing import Any, Mapping

from ..decision_identity import (
    ensure_decision_identity,
    lineage_from_opportunity,
    snapshot_operator_intent,
)
from ..operator_intent import resolve_operator_intent

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_ACTIONS = {"WAIT", "DEFEND", "SEEK_OPP", "INCREASE_RISK", "DECREASE_RISK", "EXECUTE"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _lineage_matches(outcome: Any, *, decision_id: str, correlation_id: str, opportunity_id: str) -> bool:
    row = _dict(outcome)
    if _text(row.get("status")).lower() != "settled":
        return False
    if decision_id and _text(row.get("decision_id") or row.get("canonical_decision_id")) != decision_id:
        return False
    if correlation_id and _text(row.get("correlation_id")) != correlation_id:
        return False
    if opportunity_id and _text(row.get("opportunity_id")) != opportunity_id:
        return False
    return True


def _patch_omar_context() -> None:
    """Feed the canonical operator-intent snapshot into OMAR decision context."""
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_omar_context", None)
    if original is None or getattr(original, "_operator_intent_patched", False):
        return

    def wrapped(self: Any, opp: Any, *, p_success: float, ev_wei: int):
        context = dict(original(self, opp, p_success=p_success, ev_wei=ev_wei) or {})
        intent = context.get("operator_intent")
        if not isinstance(intent, Mapping):
            intent = snapshot_operator_intent(self)
        intent = dict(intent)
        goal = _dict(intent.get("goal"))
        recommendation = _dict(intent.get("ai_recommendation"))
        context.update(
            {
                "operator_intent": intent,
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
    """Replace the old OMAR-generated identity path with the canonical production path."""
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_canonical_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        # This is the canonical decision boundary: capture operator intent once,
        # then create/preserve the identity before OMAR can observe the decision.
        intent = snapshot_operator_intent(self)
        chain_cfg = getattr(getattr(self, "cfg", None), "chain", None)
        chain_name = _text(getattr(chain_cfg, "name", "chain")) or "chain"
        identity = ensure_decision_identity(
            opp,
            decision,
            chain_name=chain_name,
            current_block=int(current_block),
            operator_intent=intent,
        )

        omar = getattr(self, "_omar", None)
        if omar is None or not bool(getattr(omar, "enabled", False)):
            return opp, decision

        try:
            bm = _dict(_dict(getattr(opp, "meta", None)).get("brain"))
            p_success = float(bm.get("p_success") or getattr(decision, "p_success", 0.0) or 0.0)
            ev_wei = int(bm.get("ev_wei") or getattr(decision, "ev_wei", 0) or 0)
            context = dict(self._omar_context(opp, p_success=p_success, ev_wei=ev_wei) or {})
            context["operator_intent"] = dict(intent)
            context["canonical_decision_id"] = identity.decision_id
            context["correlation_id"] = identity.correlation_id

            rec = omar.recommend(context)
            learning_action = _text(getattr(rec, "action", ""))
            if learning_action not in _ACTIONS:
                learning_action = "EXECUTE"

            if isinstance(getattr(opp, "meta", None), dict):
                brain = _dict(opp.meta.get("brain"))
                brain["canonical_decision_id"] = identity.decision_id
                brain["correlation_id"] = identity.correlation_id
                brain.pop("omar_decision_id", None)
                brain["omar_action"] = learning_action
                brain["omar_state_key"] = str(getattr(rec, "state_key", ""))
                brain["omar_confidence"] = float(getattr(rec, "confidence", 0.0) or 0.0)
                brain["omar_trained"] = bool(getattr(rec, "trained", False))
                brain["omar_observations"] = int(getattr(rec, "observations", 0) or 0)
                brain["omar_reason"] = _text(getattr(rec, "reason", ""))
                brain["operator_intent"] = dict(intent)
                opp.meta["brain"] = brain
                opp.meta["omar"] = rec.to_dict()

            metadata = {
                "current_block": int(current_block),
                "ev_wei": int(ev_wei),
                "p_success": float(p_success),
                "canonical_decision_id": identity.decision_id,
                "correlation_id": identity.correlation_id,
                "operator_intent": dict(intent),
                "recommendation": rec.to_dict(),
            }

            if bool(getattr(rec, "veto", False)):
                omar.observe_decision(
                    decision_id=identity.decision_id,
                    opportunity_id=_text(getattr(opp, "id", "")),
                    route_id=_text(getattr(opp, "route_id", "")),
                    action=learning_action,
                    state_key=str(getattr(rec, "state_key", "")),
                    context=context,
                    metadata=metadata,
                )
                return None, decision

            if decision is None:
                decision = TradeDecision(
                    action="trade",
                    opp_id=_text(getattr(opp, "id", "")),
                    route_id=_text(getattr(opp, "route_id", "")),
                    size_mult=float(getattr(rec, "size_mult", 1.0) or 1.0),
                    borrow_mult=1.0,
                    gas_mode=_text(getattr(rec, "gas_mode", "standard")) or "standard",
                    p_success=p_success,
                    ev_wei=ev_wei,
                    reason="omar_selected",
                    rl_state="",
                    rl_action_index=-1,
                    portfolio=[_text(getattr(opp, "id", ""))],
                )
            else:
                decision.size_mult = min(float(getattr(decision, "size_mult", 1.0) or 1.0), float(getattr(rec, "size_mult", 1.0) or 1.0))
                decision.borrow_mult = min(float(getattr(decision, "borrow_mult", 1.0) or 1.0), 1.0)
                if _text(getattr(rec, "gas_mode", "")) in {"standard", "fast", "instant"}:
                    decision.gas_mode = _text(getattr(rec, "gas_mode"))

            ensure_decision_identity(
                opp,
                decision,
                chain_name=chain_name,
                current_block=int(current_block),
                operator_intent=intent,
            )
            decision.metadata["canonical_decision_id"] = identity.decision_id
            decision.metadata["correlation_id"] = identity.correlation_id
            decision.metadata["operator_intent"] = dict(intent)

            if isinstance(getattr(opp, "meta", None), dict):
                brain = _dict(opp.meta.get("brain"))
                brain["size_mult_omar"] = float(getattr(decision, "size_mult", 1.0) or 1.0)
                brain["gas_mode_omar"] = _text(getattr(decision, "gas_mode", "standard")) or "standard"
                brain["canonical_decision_id"] = identity.decision_id
                brain["correlation_id"] = identity.correlation_id
                brain["operator_intent"] = dict(intent)
                opp.meta["brain"] = brain

            omar.observe_decision(
                decision_id=identity.decision_id,
                opportunity_id=_text(getattr(opp, "id", "")),
                route_id=_text(getattr(opp, "route_id", "")),
                action=learning_action,
                state_key=str(getattr(rec, "state_key", "")),
                context=context,
                metadata=metadata,
            )
            return opp, decision
        except _SAFE:
            return opp, decision

    from ..decision_engine import TradeDecision

    wrapped._canonical_identity_patched = True
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
                    operator_intent=snapshot_operator_intent(runtime),
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
                outcome["canonical_decision_id"] = lineage["decision_id"]
                outcome["operator_intent_fingerprint"] = lineage["operator_intent_fingerprint"]
        except (AttributeError, TypeError):
            pass
        return outcome

    wrapped._production_identity_patched = True
    lifecycle_bridge._canonical_settled_outcome = wrapped


def _patch_learning_identity() -> None:
    """Make decision->outcome learning identity durable, idempotent, and fail-closed."""
    from victor_ai_bot.omar.learning_identity import DurableLearningIdentity
    from victor_ai_bot.omar.learning_integrity import validate_learning_transition
    from victor_ai_bot.omar.runtime import OmarRuntime

    original_decision = getattr(OmarRuntime, "observe_decision", None)
    original_outcome = getattr(OmarRuntime, "observe_outcome", None)
    if original_decision is None or original_outcome is None:
        return
    if getattr(original_decision, "_durable_identity_patched", False):
        return

    def store_for(runtime: Any) -> DurableLearningIdentity:
        store = getattr(runtime, "_durable_learning_identity", None)
        if store is not None:
            return store
        base = str(getattr(runtime, "data_dir", os.path.join("data", "superstructure")))
        chain = _text(getattr(runtime, "chain_name", "default")) or "default"
        store = DurableLearningIdentity(os.path.join(base, "omar_learning", f"identity_{chain}.json"))
        runtime._durable_learning_identity = store
        return store

    def observe_decision(self: Any, **kwargs: Any) -> None:
        original_decision(self, **kwargs)
        decision_id = _text(kwargs.get("decision_id"))
        if not decision_id:
            return
        store_for(self).remember_decision(
            decision_id,
            {
                "correlation_id": _text(_dict(kwargs.get("metadata")).get("correlation_id")),
                "opportunity_id": _text(kwargs.get("opportunity_id")),
                "route_id": _text(kwargs.get("route_id")),
                "action": _text(kwargs.get("action")),
                "state_key": _text(kwargs.get("state_key")),
                "context": _dict(kwargs.get("context")),
                "metadata": _dict(kwargs.get("metadata")),
            },
        )

    def observe_outcome(self: Any, **kwargs: Any):
        decision_id = _text(kwargs.get("decision_id"))
        store = store_for(self)
        if decision_id and store.is_settled(decision_id):
            return {
                "ok": True,
                "duplicate": True,
                "learned": False,
                "reason": "settled_outcome_already_learned",
                "decision_id": decision_id,
            }

        pending = store.pending(decision_id) if decision_id else {}
        metadata = _dict(kwargs.get("metadata"))
        settlement = _dict(metadata.get("settlement"))
        canonical_lineage = _dict(metadata.get("canonical_lineage"))
        outcome = dict(settlement)
        outcome.update(
            {
                "status": _text(settlement.get("status")) or "settled",
                "decision_id": _text(settlement.get("decision_id") or settlement.get("canonical_decision_id")) or decision_id,
                "correlation_id": _text(settlement.get("correlation_id")) or _text(canonical_lineage.get("correlation_id")),
                "opportunity_id": _text(settlement.get("opportunity_id")) or _text(pending.get("opportunity_id")),
                "action": _text(settlement.get("action")) or _text(pending.get("action")),
                "route_id": _text(settlement.get("route_id")) or _text(kwargs.get("route_id") or pending.get("route_id")),
                "outcome_truth_verified": bool(settlement.get("truth_verified", settlement.get("outcome_truth_verified", kwargs.get("outcome_truth_verified", False)))),
                "source": _text(settlement.get("source")) or _text(metadata.get("source")),
                "canonical_lineage": {
                    "decision_id": _text(canonical_lineage.get("decision_id")) or decision_id,
                    "correlation_id": _text(canonical_lineage.get("correlation_id")),
                },
            }
        )

        gate = validate_learning_transition(pending, outcome, decision_id=decision_id)
        if not gate.allowed:
            self._log({"event": "omar_learning_integrity_rejected", "decision_id": decision_id, "reason": gate.reason, "lineage": gate.to_dict()})
            return {"ok": False, "learned": False, "reason": gate.reason, "decision_id": decision_id}

        result = original_outcome(self, **kwargs)
        if isinstance(result, Mapping) and result.get("ok") and decision_id:
            store.mark_settled(
                decision_id,
                {
                    "correlation_id": outcome["correlation_id"],
                    "action": outcome["action"],
                    "route_id": outcome["route_id"],
                    "tx_hash": _text(kwargs.get("tx_hash") or outcome.get("tx_hash")),
                    "operator_intent_fingerprint": _text(metadata.get("operator_intent_fingerprint")),
                },
            )
        return result

    observe_decision._durable_identity_patched = True
    OmarRuntime.observe_decision = observe_decision
    OmarRuntime.observe_outcome = observe_outcome


def install_production_lineage_bridge() -> None:
    """Install production decision/execution/settlement identity propagation."""
    try:
        _patch_omar_context()
        _patch_decision_identity()
        _patch_execution_identity()
        _patch_settlement_resolution()
    except _SAFE:
        return

    try:
        _patch_learning_identity()
    except (ImportError, ModuleNotFoundError):
        return
    except _SAFE:
        return
