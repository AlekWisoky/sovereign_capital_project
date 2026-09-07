from __future__ import annotations

import copy
import hashlib
import inspect
import time
from typing import Any, Mapping

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(value) for value in parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def capital_authority_context(runtime: Any) -> dict[str, Any]:
    """Read-only OMAR view of the runtime's actual capital authority."""
    try:
        raw = (
            runtime.capital_engine_state()
            if callable(getattr(runtime, "capital_engine_state", None))
            else {}
        )
        root = _dict(raw)
        cap = _dict(root.get("capital_engine"))
        allocations = _dict(cap.get("family_allocations_wei"))
        available = cap.get("available_bankroll_wei", cap.get("available_wei", 0))
        deployable = cap.get("deployable_bankroll_wei", cap.get("deployable_wei", 0))
        return {
            "capital_authority_source": "capital_engine_state",
            "capital_available_wei": max(0, int(available or 0)),
            "capital_allocatable_wei": max(0, int(deployable or 0)),
            "capital_family_allocations_wei": {
                str(k): max(0, int(v or 0)) for k, v in allocations.items()
            },
            "capital_authority_status": _text(cap.get("status") or root.get("status")) or "unknown",
            "capital_authority_freshness": _text(
                cap.get("freshness_class") or root.get("freshness_class")
            )
            or "unknown",
            "capital_authority_id": _text(cap.get("authority_id") or root.get("authority_id"))
            or "unknown",
            "capital_source": _text(cap.get("source") or root.get("source")) or "runtime_capital",
            "internal_prime_available": bool(
                cap.get("internal_prime_available", cap.get("prime_available", False))
            ),
            "prime_capacity_ratio": float(
                cap.get("prime_capacity_ratio", cap.get("internal_prime_capacity_ratio", 0.0))
                or 0.0
            ),
            "prime_cost_bps": float(
                cap.get("prime_cost_bps", cap.get("internal_prime_cost_bps", 0.0)) or 0.0
            ),
        }
    except _SAFE:
        return {
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "unavailable",
            "capital_authority_freshness": "unavailable",
            "capital_authority_id": "unavailable",
            "capital_available_wei": 0,
            "capital_allocatable_wei": 0,
            "capital_family_allocations_wei": {},
            "capital_source": "runtime_capital",
            "internal_prime_available": False,
            "prime_capacity_ratio": 0.0,
            "prime_cost_bps": 0.0,
        }


def ensure_lineage(opp: Any, decision: Any, current_block: int) -> tuple[str, str]:
    """Persist canonical decision/correlation IDs on both decision and opportunity."""
    meta = getattr(opp, "meta", None)
    brain = _dict(meta.get("brain")) if isinstance(meta, dict) else {}
    decision_id = _text(brain.get("canonical_decision_id") or brain.get("omar_decision_id"))
    if not decision_id:
        decision_id = _stable_id(
            "decision", current_block, getattr(opp, "id", ""), getattr(opp, "route_id", "")
        )
    correlation_id = _text(brain.get("correlation_id") or brain.get("omar_correlation_id"))
    if not correlation_id:
        correlation_id = _stable_id("corr", decision_id)
    brain["canonical_decision_id"] = decision_id
    brain["correlation_id"] = correlation_id
    if isinstance(meta, dict):
        meta["brain"] = brain
        lineage = _dict(meta.get("canonical_lineage"))
        lineage.setdefault("decision_id", decision_id)
        lineage.setdefault("correlation_id", correlation_id)
        lineage.setdefault("created_at_ms", int(time.time() * 1000))
        if brain.get("operator_intent") and not lineage.get("operator_intent"):
            lineage["operator_intent"] = copy.deepcopy(brain["operator_intent"])
        if brain.get("intent_fingerprint") and not lineage.get("intent_fingerprint"):
            lineage["intent_fingerprint"] = str(brain["intent_fingerprint"])
        meta["canonical_lineage"] = lineage
    metadata = _dict(getattr(decision, "metadata", None))
    metadata["canonical_decision_id"] = decision_id
    metadata["correlation_id"] = correlation_id
    metadata["decision_lineage"] = {"decision_id": decision_id, "correlation_id": correlation_id}
    if isinstance(meta, dict):
        lineage = _dict(meta.get("canonical_lineage"))
        intent = lineage.get("operator_intent")
        fingerprint = lineage.get("intent_fingerprint")
        if intent and not metadata.get("operator_intent"):
            metadata["operator_intent"] = copy.deepcopy(intent)
        if fingerprint and not metadata.get("intent_fingerprint"):
            metadata["intent_fingerprint"] = str(fingerprint)
    try:
        decision.metadata = metadata
    except _SAFE:
        pass
    return decision_id, correlation_id


def _patch_decision_context() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade
    from ..operator_intent import resolve_operator_intent

    original = getattr(RuntimeDecisionFacade, "_omar_context", None)
    if original is None or getattr(original, "_omar_capital_patched", False):
        return

    def wrapped(self: Any, opp: Any, *, p_success: float, ev_wei: int) -> dict[str, Any]:
        context = _dict(original(self, opp, p_success=p_success, ev_wei=ev_wei))
        context.update(capital_authority_context(self))
        try:
            context["operator_intent"] = copy.deepcopy(resolve_operator_intent(self))
        except _SAFE:
            context["operator_intent"] = {}
        return context

    wrapped._omar_capital_patched = True
    RuntimeDecisionFacade._omar_context = wrapped


def _patch_decision_lineage() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_omar_lineage_patched", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any | None, *, current_block: int):
        chosen, selected = original(self, opp, decision, current_block=current_block)
        if chosen is not None and selected is not None:
            ensure_lineage(chosen, selected, int(current_block))
        return chosen, selected

    wrapped._omar_lineage_patched = True
    RuntimeDecisionFacade._apply_omar_to_candidate = wrapped


def _canonical_settled_outcome(runtime: Any, result: Any, opp: Any) -> dict[str, Any] | None:
    """Return only an outcome already marked settled by the canonical ledger."""
    interface = getattr(runtime, "canonical_settled_outcome", None)
    if callable(interface):
        try:
            meta = _dict(getattr(opp, "meta", None))
            brain = _dict(meta.get("brain"))
            lineage = _dict(meta.get("canonical_lineage"))
            row = interface(
                tx_hash=_text(getattr(result, "tx_hash", "")),
                decision_id=_text(brain.get("canonical_decision_id") or lineage.get("decision_id")),
                correlation_id=_text(brain.get("correlation_id") or lineage.get("correlation_id")),
                opportunity_id=_text(getattr(opp, "id", "")),
            )
            row = _dict(row)
            if _text(row.get("status")).lower() == "settled":
                return row
        except _SAFE:
            pass

    ledgers = [
        getattr(runtime, "canonical_outcome_ledger", None),
        getattr(runtime, "_canonical_outcome_ledger", None),
        getattr(runtime, "outcome_ledger", None),
        getattr(runtime, "_outcome_ledger", None),
    ]
    keys = [_text(getattr(result, "tx_hash", "")), _text(getattr(opp, "id", ""))]
    for ledger in ledgers:
        if ledger is None:
            continue
        for method_name in (
            "get_settled",
            "lookup_settled",
            "find_settled",
            "settled_outcome",
            "get_outcome",
        ):
            method = getattr(ledger, method_name, None)
            if not callable(method):
                continue
            for key in keys:
                if not key:
                    continue
                try:
                    row = method(key)
                    if inspect.isawaitable(row):
                        continue
                    row = _dict(row)
                    if _text(row.get("status")).lower() in {
                        "settled",
                        "closed",
                        "complete",
                        "completed",
                    }:
                        return row
                except _SAFE:
                    continue
    for attribute in ("last_canonical_settled_outcome", "last_settled_outcome"):
        row = _dict(getattr(runtime, attribute, None))
        if _text(row.get("status")).lower() in {"settled", "closed", "complete", "completed"}:
            return row
    return None


def _observe_settled_outcome(
    runtime: Any, *, pending: Mapping[str, Any], outcome: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply exactly one canonical settled outcome to the real OMAR learner."""
    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason": "omar_disabled"}

    pending_row = _dict(pending)
    brain = _dict(pending_row.get("brain"))
    lineage = _dict(pending_row.get("canonical_lineage"))
    decision_id = _text(
        pending_row.get("canonical_decision_id")
        or brain.get("canonical_decision_id")
        or lineage.get("decision_id")
        or brain.get("omar_decision_id")
    )
    correlation_id = _text(
        pending_row.get("correlation_id")
        or brain.get("correlation_id")
        or lineage.get("correlation_id")
    )
    if not decision_id or not correlation_id:
        return {"ok": False, "reason": "missing_canonical_lineage"}

    outcome_row = _dict(outcome)
    if _text(outcome_row.get("status")).lower() != "settled":
        return {"ok": False, "reason": "outcome_not_settled"}

    metadata = {
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        },
        "source": "phase2_canonical_outcome_ledger",
        "settlement": copy.deepcopy(outcome_row),
        "operator_intent": copy.deepcopy(
            _dict(
                _dict(pending_row.get("context")).get("operator_intent")
                or lineage.get("operator_intent")
                or brain.get("operator_intent")
            )
        ),
        "intent_fingerprint": _text(
            lineage.get("intent_fingerprint") or brain.get("intent_fingerprint")
        ),
    }
    result = omar.observe_outcome(
        decision_id=decision_id,
        ok=bool(outcome_row.get("ok", True)),
        realized_net_usd=float(
            outcome_row.get("realized_net_usd", outcome_row.get("realizedNetUsd", 0.0)) or 0.0
        ),
        expected_net_usd=float(
            outcome_row.get("expected_net_usd", outcome_row.get("expectedNetUsd", 0.0)) or 0.0
        ),
        amount_in_wei=int(outcome_row.get("amount_in_wei", outcome_row.get("amountInWei", 0)) or 0),
        gas_cost_usd=float(
            outcome_row.get("gas_cost_usd", outcome_row.get("gasCostUsd", 0.0)) or 0.0
        ),
        slippage_bps=float(
            outcome_row.get("slippage_bps", outcome_row.get("slippageBps", 0.0)) or 0.0
        ),
        latency_ms=int(outcome_row.get("latency_ms", outcome_row.get("latencyMs", 0)) or 0),
        route_id=_text(outcome_row.get("route_id") or pending_row.get("route_id")),
        tx_hash=_text(outcome_row.get("tx_hash") or outcome_row.get("txHash")),
        outcome_truth_verified=bool(
            outcome_row.get("truth_verified", outcome_row.get("outcome_truth_verified", True))
        ),
        metadata=metadata,
    )

    telemetry = getattr(runtime, "_telemetry_service", None)
    if telemetry is not None and hasattr(telemetry, "record"):
        try:
            telemetry.record(
                "omar_learning_update",
                {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                    "opportunity_id": _text(pending_row.get("opportunity_id")),
                    "route_id": _text(outcome_row.get("route_id") or pending_row.get("route_id")),
                    "tx_hash": _text(outcome_row.get("tx_hash") or outcome_row.get("txHash")),
                    "state_key": _text(result.get("state_key")),
                    "action": _text(result.get("action")),
                    "reward": float(result.get("reward") or 0.0),
                    "observations": int(result.get("observations") or 0),
                    "outcome_truth_verified": bool(
                        outcome_row.get(
                            "truth_verified", outcome_row.get("outcome_truth_verified", True)
                        )
                    ),
                    "intent_fingerprint": metadata["intent_fingerprint"],
                },
                chain=_chain_name(runtime),
            )
        except _SAFE:
            pass
    return dict(result or {})


def _patch_settlement_learning() -> None:
    from victor_ai_bot.runtime_services.execution_service import ExecutionService

    original = getattr(ExecutionService, "handle_post_execute_bookkeeping", None)
    if original is None or getattr(original, "_omar_settlement_patched", False):
        return

    async def wrapped(*args: Any, **kwargs: Any):
        signature = inspect.signature(original)
        bound = signature.bind_partial(*args, **kwargs)
        result = await original(*args, **kwargs)
        try:
            runtime = bound.arguments.get("runtime")
            opp = bound.arguments.get("opp") or bound.arguments.get("opportunity")
            exec_result = bound.arguments.get("result") or result
            if runtime is None or opp is None:
                return result
            omar = getattr(runtime, "_omar", None)
            if omar is None or not bool(getattr(omar, "enabled", False)):
                return result
            meta = _dict(getattr(opp, "meta", None))
            brain = _dict(meta.get("brain"))
            lineage = _dict(meta.get("canonical_lineage"))
            decision_id = _text(
                brain.get("canonical_decision_id")
                or lineage.get("decision_id")
                or brain.get("omar_decision_id")
            )
            correlation_id = _text(brain.get("correlation_id") or lineage.get("correlation_id"))
            if not decision_id or not correlation_id:
                return result
            outcome = _canonical_settled_outcome(runtime, exec_result, opp)
            if outcome is None:
                return result
            _observe_settled_outcome(runtime, pending=meta, outcome=outcome)
        except _SAFE:
            pass
        return result

    wrapped._omar_settlement_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _patch_receipt_settlement_learning() -> None:
    """Attach OMAR learning after the real receipt path commits canonical settlement."""
    from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", None)
    if original is None or getattr(original, "_omar_receipt_learning_patched", False):
        return

    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        signature = inspect.signature(original)
        bound = signature.bind_partial(self, *args, **kwargs)
        result = original(self, *args, **kwargs)
        try:
            runtime = bound.arguments.get("self")
            pending = _dict(bound.arguments.get("pending"))
            if runtime is None or not pending:
                return result
            omar = getattr(runtime, "_omar", None)
            if omar is None or not bool(getattr(omar, "enabled", False)):
                return result
            sync = _dict(getattr(runtime, "_last_settlement_sync", None))
            if not bool(sync.get("ok", False)):
                return result
            tx_hash = _text(bound.arguments.get("tx_hash"))
            brain = _dict(pending.get("brain"))
            lineage = _dict(pending.get("canonical_lineage"))
            decision_id = _text(
                pending.get("canonical_decision_id")
                or brain.get("canonical_decision_id")
                or lineage.get("decision_id")
            )
            correlation_id = _text(
                pending.get("correlation_id")
                or brain.get("correlation_id")
                or lineage.get("correlation_id")
            )
            if not decision_id or not correlation_id:
                return result
            outcome = getattr(runtime, "canonical_settled_outcome", None)
            outcome = (
                outcome(
                    tx_hash=tx_hash,
                    decision_id=decision_id,
                    correlation_id=correlation_id,
                    opportunity_id=_text(pending.get("opportunity_id")),
                )
                if callable(outcome)
                else None
            )
            if outcome is not None:
                _observe_settled_outcome(runtime, pending=pending, outcome=outcome)
        except _SAFE:
            pass
        return result

    wrapped._omar_receipt_learning_patched = True
    RuntimeReceiptFacade._safe_finalize_receipt_side_effects = wrapped


def install_omar_lifecycle_hooks() -> None:
    try:
        _patch_decision_context()
        _patch_decision_lineage()
        _patch_settlement_learning()
        _patch_receipt_settlement_learning()
    except _SAFE:
        return
