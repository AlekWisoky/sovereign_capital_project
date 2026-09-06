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


def _patch_decision_identity() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        operator_intent, fingerprint = snapshot_operator_intent(self, opp, decision)
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
        try:
            registry = getattr(self, "_operator_intent_by_route_id", None)
            if not isinstance(registry, dict):
                registry = {}
                setattr(self, "_operator_intent_by_route_id", registry)
            route_id = _text(getattr(opp, "route_id", ""))
            if route_id:
                registry[route_id] = {
                    "operator_intent": dict(operator_intent),
                    "intent_fingerprint": str(fingerprint),
                    "canonical_lineage": dict(
                        _dict(getattr(opp, "meta", {}).get("canonical_lineage"))
                    ),
                    "opportunity_id": _text(getattr(opp, "id", "")),
                }
        except _SAFE:
            pass
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
                )
                lineage = lineage_from_opportunity(opp)
                if result is not None:
                    plan = _dict(getattr(result, "plan", None))
                    plan["canonical_lineage"] = dict(lineage)
                    plan["canonical_decision_id"] = lineage["decision_id"]
                    plan["correlation_id"] = lineage["correlation_id"]
                    intent = _dict(_dict(getattr(opp, "meta", None)).get("canonical_lineage")).get(
                        "operator_intent"
                    )
                    if isinstance(intent, Mapping):
                        plan["operator_intent"] = dict(intent)
                    fingerprint = _text(
                        _dict(_dict(getattr(opp, "meta", None)).get("canonical_lineage")).get(
                            "intent_fingerprint"
                        )
                    )
                    if fingerprint:
                        plan["intent_fingerprint"] = fingerprint
                    result.plan = plan
            except _SAFE:
                pass
        return await original(*args, **kwargs)

    wrapped._production_identity_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _patch_capital_write() -> None:
    from victor_ai_bot.runtime_services.capital_write_service import CapitalWriteService

    original = getattr(CapitalWriteService, "commit_receipt_settlement", None)
    if original is None or getattr(original, "_production_intent_patched", False):
        return

    def wrapped(self: Any, runtime: Any, *, tx_payload: Mapping[str, Any], **kwargs: Any):
        payload = dict(tx_payload or {})
        metadata = _dict(payload.get("metadata"))
        route_id = _text(kwargs.get("route_id") or metadata.get("route_id"))
        registry = getattr(runtime, "_operator_intent_by_route_id", {})
        entry = _dict(registry.get(route_id)) if isinstance(registry, dict) else {}
        lineage = _dict(entry.get("canonical_lineage"))
        intent = _dict(entry.get("operator_intent"))
        fingerprint = _text(entry.get("intent_fingerprint"))
        if lineage:
            metadata["canonical_lineage"] = dict(lineage)
        if intent:
            metadata["operator_intent"] = dict(intent)
        if fingerprint:
            metadata["intent_fingerprint"] = fingerprint
        if entry.get("opportunity_id"):
            metadata["opportunity_id"] = str(entry["opportunity_id"])
        payload["metadata"] = metadata
        return original(self, runtime, tx_payload=payload, **kwargs)

    wrapped._production_intent_patched = True
    CapitalWriteService.commit_receipt_settlement = wrapped


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
        _patch_capital_write()
        _patch_settlement_resolution()
    except _SAFE:
        return
