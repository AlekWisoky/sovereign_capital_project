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


def _lineage_matches(outcome: Any, *, decision_id: str, correlation_id: str, opportunity_id: str) -> bool:
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
        "execution_id": execution,
        "outcome_id": outcome,
    }


def _enrich_pending_lineage(pending: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(pending or {})
    lineage = _pending_lineage(row)
    if lineage["decision_id"]:
        row["canonical_decision_id"] = lineage["decision_id"]
        row["decision_id"] = lineage["decision_id"]
    if lineage["correlation_id"]:
        row["correlation_id"] = lineage["correlation_id"]
    if lineage["opportunity_id"]:
        row["opportunity_id"] = lineage["opportunity_id"]
    if lineage["execution_id"]:
        row["execution_id"] = lineage["execution_id"]
    if lineage["outcome_id"]:
        row["outcome_id"] = lineage["outcome_id"]
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
                    plan["canonical_lineage"] = {**dict(lineage), "execution_id": exec_id}
                    plan["canonical_decision_id"] = lineage["decision_id"]
                    plan["correlation_id"] = lineage["correlation_id"]
                    plan["execution_id"] = exec_id
                    result.plan = plan
            except _SAFE:
                pass
        return await original(*args, **kwargs)

    wrapped._production_identity_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _patch_persisted_outcome_lineage() -> None:
    """Carry identity from the production pending record into settlement persistence."""
    from victor_ai_bot.runtime_services.execution_service import ExecutionService

    original = getattr(ExecutionService, "persist_execution_outcome", None)
    if original is None or getattr(original, "_production_lineage_patched", False):
        return

    def wrapped(*args: Any, **kwargs: Any):
        pending = kwargs.get("pending")
        if isinstance(pending, Mapping):
            kwargs["pending"] = _enrich_pending_lineage(pending)
        elif args:
            try:
                signature = inspect.signature(original)
                bound = signature.bind_partial(*args, **kwargs)
                if isinstance(bound.arguments.get("pending"), Mapping):
                    bound.arguments["pending"] = _enrich_pending_lineage(
                        bound.arguments["pending"]
                    )
                    return original(*bound.args, **bound.kwargs)
            except _SAFE:
                pass
        return original(*args, **kwargs)

    wrapped._production_lineage_patched = True
    ExecutionService.persist_execution_outcome = wrapped


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
        row = dict(outcome)
        exec_id = _text(
            row.get("execution_id")
            or _dict(row.get("canonical_lineage")).get("execution_id")
        )
        if not exec_id:
            exec_id = execution_id(
                decision_id=lineage["decision_id"],
                correlation_id=lineage["correlation_id"],
                tx_hash=_text(row.get("tx_hash") or getattr(result, "tx_hash", "")),
                route_id=_text(row.get("route_id") or getattr(opp, "route_id", "")),
            )
        out_id = _text(
            row.get("outcome_id")
            or _dict(row.get("canonical_lineage")).get("outcome_id")
        )
        if not out_id:
            out_id = outcome_id(
                decision_id=lineage["decision_id"],
                correlation_id=lineage["correlation_id"],
                transaction_id=_text(row.get("transaction_id")),
                tx_hash=_text(row.get("tx_hash") or getattr(result, "tx_hash", "")),
            )
        row["execution_id"] = exec_id
        row["outcome_id"] = out_id
        row["canonical_lineage"] = {
            **lineage,
            "execution_id": exec_id,
            "outcome_id": out_id,
        }
        return row

    wrapped._production_identity_patched = True
    lifecycle_bridge._canonical_settled_outcome = wrapped


def install_production_lineage_bridge() -> None:
    try:
        _patch_decision_identity()
        _patch_execution_identity()
        _patch_persisted_outcome_lineage()
        _patch_settlement_resolution()
    except _SAFE:
        return
