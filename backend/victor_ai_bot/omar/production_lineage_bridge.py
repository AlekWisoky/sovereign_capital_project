from __future__ import annotations

import inspect
from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity
from ..operator_intent import intent_fingerprint, resolve_operator_intent

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _lineage_matches(
    outcome: Any,
    *,
    decision_id: str,
    correlation_id: str,
    opportunity_id: str,
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


def _attach_operator_intent(opp: Any, decision: Any | None, runtime: Any) -> dict[str, Any]:
    """Persist operator intent as attribution/context, never as authority."""
    intent = resolve_operator_intent(runtime)
    fingerprint = intent_fingerprint(intent)

    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        meta = {}
        try:
            opp.meta = meta
        except (AttributeError, TypeError):
            return {"intent": intent, "fingerprint": fingerprint}

    attribution = {
        "fingerprint": fingerprint,
        "intent": intent,
        "authority": "operator_intent_only",
    }
    meta["operator_intent"] = attribution

    if decision is not None:
        decision_meta = _dict(getattr(decision, "metadata", None))
        decision_meta["operator_intent"] = attribution
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass

    return attribution


def _patch_decision_identity() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        attribution = _attach_operator_intent(opp, decision, self)
        chosen, selected = original(self, opp, decision, current_block=current_block)
        if chosen is not None:
            meta = getattr(chosen, "meta", None)
            if isinstance(meta, dict):
                meta["operator_intent"] = attribution
            if selected is not None:
                decision_meta = _dict(getattr(selected, "metadata", None))
                decision_meta["operator_intent"] = attribution
                try:
                    selected.metadata = decision_meta
                except (AttributeError, TypeError):
                    pass
        ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(
                getattr(
                    getattr(getattr(self, "cfg", None), "chain", None),
                    "name",
                    "chain",
                )
            ),
            current_block=int(current_block),
        )
        return chosen, selected

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
                        getattr(
                            getattr(getattr(runtime, "cfg", None), "chain", None),
                            "name",
                            "chain",
                        )
                    ),
                    current_block=int(bound.arguments.get("bn") or 0),
                )
                lineage = lineage_from_opportunity(opp)
                intent = _dict(_dict(getattr(opp, "meta", None)).get("operator_intent"))
                if result is not None:
                    plan = _dict(getattr(result, "plan", None))
                    plan["canonical_lineage"] = dict(lineage)
                    plan["canonical_decision_id"] = lineage["decision_id"]
                    plan["correlation_id"] = lineage["correlation_id"]
                    if intent:
                        plan["operator_intent"] = intent
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
        return outcome

    wrapped._production_identity_patched = True
    lifecycle_bridge._canonical_settled_outcome = wrapped


def install_production_lineage_bridge() -> None:
    try:
        _patch_decision_identity()
        _patch_execution_identity()
        _patch_settlement_resolution()
    except _SAFE:
        return
