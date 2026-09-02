from __future__ import annotations

import inspect
from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity
from .lineage_identity import execution_id, outcome_id

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
    # A settled row is eligible for learning only when the physical ledger
    # record itself carried the complete production lineage. The canonical
    # read interface may derive compatibility IDs, but that must never hide a
    # persistence gap from the learner.
    return bool(row.get("lineage_persisted", False))


def _pending_lineage(pending: Mapping[str, Any]) -> dict[str, str]:
    row = dict(pending or {})
    canonical = _dict(row.get("canonical_lineage"))
    decision_id = _text(
        row.get("canonical_decision_id")
        or row.get("decision_id")
        or canonical.get("decision_id")
    )
    correlation_id = _text(row.get("correlation_id") or canonical.get("correlation_id"))
    opportunity_id = _text(row.get("opportunity_id") or canonical.get("opportunity_id"))
    tx_hash = _text(row.get("tx_hash") or row.get("transaction_hash"))
    route_id = _text(row.get("route_id") or canonical.get("route_id"))
    execution = _text(row.get("execution_id") or canonical.get("execution_id"))
    outcome = _text(row.get("outcome_id") or canonical.get("outcome_id"))
    sizing = _text(row.get("sizing_id") or canonical.get("sizing_id"))
    action = _text(
        row.get("learning_action")
        or row.get("action")
        or canonical.get("learning_action")
        or canonical.get("action")
        or row.get("aqe_action")
    )
    if decision_id or correlation_id:
        execution = execution or execution_id(
            decision_id=decision_id,
            correlation_id=correlation_id,
            tx_hash=tx_hash,
            route_id=route_id,
        )
        outcome = outcome or outcome_id(
            decision_id=decision_id,
            correlation_id=correlation_id,
            transaction_id=_text(row.get("transaction_id")),
            tx_hash=tx_hash,
        )
    return {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "opportunity_id": opportunity_id,
        "route_id": route_id,
        "execution_id": execution,
        "outcome_id": outcome,
        "sizing_id": sizing,
        "action": action,
    }


def _resolve_learning_action(runtime: Any, pending: Mapping[str, Any]) -> str:
    row = dict(pending or {})
    direct = _text(
        row.get("learning_action")
        or row.get("action")
        or row.get("aqe_action")
    )
    if direct:
        return direct
    decision_id = _text(
        row.get("canonical_decision_id")
        or row.get("decision_id")
        or _dict(row.get("canonical_lineage")).get("decision_id")
    )
    omar = getattr(runtime, "_omar", None) if runtime is not None else None
    pending_decisions = getattr(omar, "_pending_decisions", None)
    if decision_id and isinstance(pending_decisions, Mapping):
        decision = pending_decisions.get(decision_id)
        if isinstance(decision, Mapping):
            return _text(decision.get("action"))
    return ""


def _enrich_pending_lineage(
    pending: Mapping[str, Any], *, runtime: Any | None = None
) -> dict[str, Any]:
    row = dict(pending or {})
    action = _resolve_learning_action(runtime, row)
    if action:
        row["action"] = action
        row["learning_action"] = action
    lineage = _pending_lineage(row)
    if action and not lineage["action"]:
        lineage["action"] = action
    if lineage["decision_id"]:
        row["canonical_decision_id"] = lineage["decision_id"]
        row["decision_id"] = lineage["decision_id"]
    if lineage["correlation_id"]:
        row["correlation_id"] = lineage["correlation_id"]
    if lineage["opportunity_id"]:
        row["opportunity_id"] = lineage["opportunity_id"]
    if lineage["route_id"]:
        row["route_id"] = lineage["route_id"]
    if lineage["execution_id"]:
        row["execution_id"] = lineage["execution_id"]
    if lineage["outcome_id"]:
        row["outcome_id"] = lineage["outcome_id"]
    if lineage["sizing_id"]:
        row["sizing_id"] = lineage["sizing_id"]
    canonical = _dict(row.get("canonical_lineage"))
    canonical.update({key: value for key, value in lineage.items() if value})
    if canonical:
        row["canonical_lineage"] = canonical
    return row


def _patch_decision_identity() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_production_identity_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(
                getattr(getattr(self, "cfg", None), "chain", None).name
                if getattr(getattr(self, "cfg", None), "chain", None) is not None
                else "chain"
            ),
            current_block=int(current_block),
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
                )
                lineage = lineage_from_opportunity(opp)
                if result is not None:
                    plan = _dict(getattr(result, "plan", None))
                    exec_id = execution_id(
                        decision_id=lineage["decision_id"],
                        correlation_id=lineage["correlation_id"],
                        tx_hash=_text(getattr(result, "tx_hash", "")),
                        route_id=_text(getattr(opp, "route_id", "")),
                        existing=_text(plan.get("execution_id") or plan.get("executionId")),
                    )
                    sizing_id = _text(
                        plan.get("sizing_id")
                        or _dict(plan.get("canonical_lineage")).get("sizing_id")
                        or _dict(getattr(opp, "meta", None)).get("sizing_id")
                        or _dict(_dict(getattr(opp, "meta", None)).get("brain")).get("sizing_id")
                    )
                    action = _resolve_learning_action(runtime, {
                        "canonical_decision_id": lineage["decision_id"],
                        "aqe_action": _dict(getattr(opp, "meta", None)).get("aqe_action"),
                    })
                    plan["canonical_lineage"] = {
                        **dict(lineage),
                        "route_id": _text(getattr(opp, "route_id", "")),
                        "execution_id": exec_id,
                        "sizing_id": sizing_id,
                        "action": action,
                    }
                    plan["canonical_decision_id"] = lineage["decision_id"]
                    plan["correlation_id"] = lineage["correlation_id"]
                    plan["execution_id"] = exec_id
                    if sizing_id:
                        plan["sizing_id"] = sizing_id
                    if action:
                        plan["action"] = action
                    result.plan = plan
            except _SAFE:
                pass
        return await original(*args, **kwargs)

    wrapped._production_identity_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _patch_receipt_finalize_lineage() -> None:
    """Resolve execution/outcome identity before the settlement side effects run."""
    from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", None)
    if original is None or getattr(original, "_production_lineage_patched", False):
        return

    def wrapped(self: Any, *args: Any, **kwargs: Any):
        try:
            signature = inspect.signature(original)
            bound = signature.bind_partial(self, *args, **kwargs)
            pending = bound.arguments.get("pending")
            if isinstance(pending, Mapping):
                bound.arguments["pending"] = _enrich_pending_lineage(
                    pending, runtime=self
                )
                return original(*bound.args, **bound.kwargs)
        except _SAFE:
            pass
        return original(self, *args, **kwargs)

    wrapped._production_lineage_patched = True
    RuntimeReceiptFacade._safe_finalize_receipt_side_effects = wrapped


def _patch_persisted_outcome_lineage() -> None:
    """Carry the complete canonical identity into the physical settlement write."""
    from victor_ai_bot.runtime_services.receipt_service import ReceiptService

    # ReceiptService owns persist_execution_outcome in the canonical runtime
    # chain. Patching ExecutionService here was a dead compatibility path and
    # left the actual receipt -> ledger boundary unprotected.
    original = getattr(ReceiptService, "persist_execution_outcome", None)
    if original is None or getattr(original, "_production_lineage_patched", False):
        return

    def wrapped(*args: Any, **kwargs: Any):
        runtime = kwargs.get("runtime")
        pending = kwargs.get("pending")
        if isinstance(pending, Mapping):
            kwargs["pending"] = _enrich_pending_lineage(pending, runtime=runtime)
        elif args:
            try:
                signature = inspect.signature(original)
                bound = signature.bind_partial(*args, **kwargs)
                if isinstance(bound.arguments.get("pending"), Mapping):
                    bound.arguments["pending"] = _enrich_pending_lineage(
                        bound.arguments["pending"],
                        runtime=bound.arguments.get("runtime"),
                    )
                    return original(*bound.args, **bound.kwargs)
            except _SAFE:
                pass
        return original(*args, **kwargs)

    wrapped._production_lineage_patched = True
    ReceiptService.persist_execution_outcome = wrapped


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
        _patch_receipt_finalize_lineage()
        _patch_persisted_outcome_lineage()
        _patch_settlement_resolution()
    except _SAFE:
        return
