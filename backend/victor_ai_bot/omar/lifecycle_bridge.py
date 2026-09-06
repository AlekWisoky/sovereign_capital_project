from __future__ import annotations

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
    """Legacy helper retained for compatibility; the production facade owns identity."""
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
        meta["canonical_lineage"] = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "created_at_ms": int(time.time() * 1000),
        }
    metadata = _dict(getattr(decision, "metadata", None))
    metadata["canonical_decision_id"] = decision_id
    metadata["correlation_id"] = correlation_id
    metadata["decision_lineage"] = {"decision_id": decision_id, "correlation_id": correlation_id}
    try:
        decision.metadata = metadata
    except _SAFE:
        pass
    return decision_id, correlation_id


def _patch_decision_context() -> None:
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_omar_context", None)
    if original is None or getattr(original, "_omar_capital_patched", False):
        return

    def wrapped(self: Any, opp: Any, *, p_success: float, ev_wei: int) -> dict[str, Any]:
        context = _dict(original(self, opp, p_success=p_success, ev_wei=ev_wei))
        context.update(capital_authority_context(self))
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
            decision_id = _text(brain.get("canonical_decision_id") or brain.get("omar_decision_id"))
            correlation_id = _text(brain.get("correlation_id"))
            if not decision_id or not correlation_id:
                return result
            outcome = _canonical_settled_outcome(runtime, exec_result, opp)
            if outcome is None:
                return result
            omar.observe_outcome(
                decision_id=decision_id,
                ok=bool(outcome.get("ok", True)),
                realized_net_usd=float(
                    outcome.get("realized_net_usd", outcome.get("realizedNetUsd", 0.0)) or 0.0
                ),
                expected_net_usd=float(
                    outcome.get("expected_net_usd", outcome.get("expectedNetUsd", 0.0)) or 0.0
                ),
                amount_in_wei=int(outcome.get("amount_in_wei", outcome.get("amountInWei", 0)) or 0),
                gas_cost_usd=float(
                    outcome.get("gas_cost_usd", outcome.get("gasCostUsd", 0.0)) or 0.0
                ),
                slippage_bps=float(
                    outcome.get("slippage_bps", outcome.get("slippageBps", 0.0)) or 0.0
                ),
                latency_ms=int(outcome.get("latency_ms", outcome.get("latencyMs", 0)) or 0),
                route_id=_text(outcome.get("route_id") or getattr(opp, "route_id", "")),
                tx_hash=_text(outcome.get("tx_hash") or outcome.get("txHash")),
                outcome_truth_verified=bool(
                    outcome.get("truth_verified", outcome.get("outcome_truth_verified", True))
                ),
                metadata={
                    "canonical_lineage": {
                        "decision_id": decision_id,
                        "correlation_id": correlation_id,
                    },
                    "source": "canonical_outcome_ledger",
                    "settlement": dict(outcome),
                },
            )
        except _SAFE:
            pass
        return result

    wrapped._omar_settlement_patched = True
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _canonical_lineage(pending: Mapping[str, Any]) -> dict[str, str]:
    meta = _dict(pending.get("canonical_lineage"))
    brain = _dict(pending.get("brain"))
    decision_id = _text(
        meta.get("decision_id")
        or brain.get("canonical_decision_id")
        or brain.get("decision_id")
    )
    correlation_id = _text(meta.get("correlation_id") or brain.get("correlation_id"))
    return {"decision_id": decision_id, "correlation_id": correlation_id}


def _observe_settled_outcome(
    runtime: Any,
    *,
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Compatibility entry point for the canonical settled-outcome learning bridge."""
    pending_map = _dict(pending)
    outcome_map = _dict(outcome)
    status = _text(outcome_map.get("status")).lower()
    if status not in {"settled", "closed", "complete", "completed"}:
        return {"ok": False, "reason_code": "outcome_not_settled"}

    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason_code": "omar_disabled"}

    lineage = _canonical_lineage(pending_map)
    if not lineage["decision_id"] or not lineage["correlation_id"]:
        return {"ok": False, "reason_code": "canonical_lineage_missing"}

    canonical_meta = _dict(pending_map.get("canonical_lineage"))
    operator_intent = _dict(canonical_meta.get("operator_intent"))
    intent_fingerprint = _text(canonical_meta.get("intent_fingerprint"))
    route_id = _text(outcome_map.get("route_id") or pending_map.get("route_id"))
    tx_hash = _text(outcome_map.get("tx_hash") or outcome_map.get("txHash"))

    kwargs = {
        "decision_id": lineage["decision_id"],
        "ok": bool(outcome_map.get("ok", True)),
        "realized_net_usd": float(
            outcome_map.get("realized_net_usd", outcome_map.get("realizedNetUsd", 0.0)) or 0.0
        ),
        "expected_net_usd": float(
            outcome_map.get("expected_net_usd", outcome_map.get("expectedNetUsd", 0.0)) or 0.0
        ),
        "amount_in_wei": int(
            outcome_map.get("amount_in_wei", outcome_map.get("amountInWei", 0)) or 0
        ),
        "gas_cost_usd": float(
            outcome_map.get("gas_cost_usd", outcome_map.get("gasCostUsd", 0.0)) or 0.0
        ),
        "slippage_bps": float(
            outcome_map.get("slippage_bps", outcome_map.get("slippageBps", 0.0)) or 0.0
        ),
        "latency_ms": int(outcome_map.get("latency_ms", outcome_map.get("latencyMs", 0)) or 0),
        "route_id": route_id,
        "tx_hash": tx_hash,
        "outcome_truth_verified": bool(
            outcome_map.get("truth_verified", outcome_map.get("outcome_truth_verified", True))
        ),
        "metadata": {
            "canonical_lineage": lineage,
            "source": "phase2_canonical_outcome_ledger",
            "settlement": dict(outcome_map),
        },
    }
    if operator_intent:
        kwargs["metadata"]["operator_intent"] = operator_intent
    if intent_fingerprint:
        kwargs["metadata"]["intent_fingerprint"] = intent_fingerprint

    try:
        learned = omar.observe_outcome(**kwargs)
    except _SAFE as exc:
        return {"ok": False, "reason_code": "omar_observe_failed", "error": str(exc)}

    return dict(learned) if isinstance(learned, Mapping) else {"ok": True, "result": learned}


def install_omar_lifecycle_hooks() -> None:
    try:
        _patch_decision_context()
        _patch_decision_lineage()
        _patch_settlement_learning()
    except _SAFE:
        return
