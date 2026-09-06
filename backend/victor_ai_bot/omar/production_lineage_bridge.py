from __future__ import annotations

import inspect
from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity
from .operator_intent import snapshot_operator_intent

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


def _intent_for_decision(runtime: Any, opp: Any, decision: Any | None) -> tuple[dict[str, Any], str]:
    """Return the write-once decision-time intent, creating it only if absent."""
    meta = _dict(getattr(opp, "meta", None))
    lineage = _dict(meta.get("canonical_lineage"))
    existing = lineage.get("operator_intent")
    fingerprint = _text(lineage.get("intent_fingerprint"))
    if isinstance(existing, Mapping) and existing:
        return dict(existing), fingerprint
    decision_meta = _dict(getattr(decision, "metadata", None)) if decision is not None else {}
    existing = decision_meta.get("operator_intent")
    fingerprint = fingerprint or _text(decision_meta.get("intent_fingerprint"))
    if isinstance(existing, Mapping) and existing:
        return dict(existing), fingerprint
    return snapshot_operator_intent(runtime, opp, decision)


def _patch_decision_identity() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        operator_intent, fingerprint = _intent_for_decision(self, opp, decision)
        ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(
                getattr(getattr(self, "cfg", None), "chain", None).name
                if getattr(getattr(self, "cfg", None), "chain", None) is not None
                else "chain"
            ),
            current_block=int(current_block),
            operator_intent=operator_intent,
            intent_fingerprint=fingerprint,
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
                operator_intent, fingerprint = _intent_for_decision(runtime, opp, decision)
                ensure_decision_identity(
                    opp,
                    decision,
                    chain_name=_text(
                        getattr(getattr(runtime, "cfg", None), "chain", None).name
                        if getattr(getattr(runtime, "cfg", None), "chain", None) is not None
                        else "chain"
                    ),
                    current_block=int(bound.arguments.get("bn") or 0),
                    operator_intent=operator_intent,
                    intent_fingerprint=fingerprint,
                )
                lineage = _dict(getattr(opp, "meta", {}).get("canonical_lineage"))
                if result is not None:
                    plan = _dict(getattr(result, "plan", None))
                    plan["canonical_lineage"] = dict(lineage)
                    plan["canonical_decision_id"] = lineage.get("decision_id", "")
                    plan["correlation_id"] = lineage.get("correlation_id", "")
                    plan["intent_fingerprint"] = fingerprint
                    plan["operator_intent"] = operator_intent
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
