from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .operator_intent import OperatorIntentSnapshot


_SAFE = (TypeError, ValueError, AttributeError, KeyError)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _int(*values: Any) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except _SAFE:
            continue
    return 0


def _float(*values: Any) -> float:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except _SAFE:
            continue
    return 0.0


def _canonical_hash(payload: Mapping[str, Any], *, prefix: str) -> str:
    body = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _lineage(pending: Mapping[str, Any], outcome: Mapping[str, Any], committed: Mapping[str, Any]) -> dict[str, str]:
    canonical = _mapping(pending.get("canonical_lineage"))
    brain = _mapping(pending.get("brain"))
    committed_lineage = _mapping(committed.get("lineage"))
    return {
        "decision_id": _text(
            canonical.get("decision_id"),
            canonical.get("decisionId"),
            committed_lineage.get("decision_id"),
            committed_lineage.get("decisionId"),
            pending.get("decision_id"),
            pending.get("decisionId"),
            brain.get("canonical_decision_id"),
            brain.get("decision_id"),
        ),
        "correlation_id": _text(
            canonical.get("correlation_id"),
            canonical.get("correlationId"),
            committed_lineage.get("correlation_id"),
            committed_lineage.get("correlationId"),
            pending.get("correlation_id"),
            pending.get("correlationId"),
            brain.get("correlation_id"),
            outcome.get("correlation_id"),
        ),
        "execution_id": _text(
            canonical.get("execution_id"),
            canonical.get("executionId"),
            committed_lineage.get("execution_id"),
            committed_lineage.get("executionId"),
            pending.get("execution_id"),
            pending.get("executionId"),
            outcome.get("execution_id"),
        ),
        "settlement_id": _text(
            canonical.get("settlement_id"),
            canonical.get("settlementId"),
            committed_lineage.get("settlement_id"),
            committed_lineage.get("settlementId"),
            outcome.get("settlement_id"),
            outcome.get("settlementId"),
            committed.get("settlement_id"),
            committed.get("settlementId"),
        ),
    }


def _capital_identity(pending: Mapping[str, Any], committed: Mapping[str, Any]) -> dict[str, Any]:
    admission = _mapping(pending.get("capital_admission"))
    demand = _mapping(
        pending.get("capital_demand")
        or pending.get("capitalDemand")
        or admission.get("capital_demand")
        or admission.get("capitalDemand")
    )
    capital_state = _mapping(
        pending.get("capital_engine_state")
        or pending.get("capitalEngineState")
        or admission.get("capital_engine_state")
        or admission.get("capitalEngineState")
    )
    prime = _mapping(
        pending.get("internal_prime")
        or pending.get("internalPrime")
        or pending.get("prime_loan")
        or pending.get("primeLoan")
    )
    prime_authority = _mapping(
        pending.get("internal_prime_authority")
        or pending.get("internalPrimeAuthority")
        or prime.get("authority")
        or admission.get("internal_prime_authority")
        or admission.get("internalPrimeAuthority")
    )

    requested = _int(
        demand.get("requested_wei"), demand.get("requestedWei"),
        demand.get("requested_amount_wei"), demand.get("requestedAmountWei"),
        pending.get("capital_demand_wei"), pending.get("capitalDemandWei"),
        pending.get("amount_in"),
    )
    authorized = _int(
        demand.get("authorized_wei"), demand.get("authorizedWei"),
        admission.get("authorized_wei"), admission.get("authorizedWei"),
        capital_state.get("allocatable_wei"), capital_state.get("allocatableWei"),
    )
    deployed = _int(
        demand.get("deployed_wei"), demand.get("deployedWei"),
        pending.get("amount_in"), pending.get("amount_in_wei"),
    )
    loan_id = _text(
        prime.get("loan_id"), prime.get("loanId"),
        pending.get("loan_id"), pending.get("prime_loan_id"), pending.get("internal_prime_loan_id"),
    )
    authority_id = _text(
        prime_authority.get("authority_id"), prime_authority.get("authorityId"),
        capital_state.get("authority_id"), capital_state.get("authorityId"),
    )
    source = _text(
        demand.get("capital_source"), demand.get("capitalSource"),
        pending.get("capital_source"), prime.get("source"),
    )
    family = _text(demand.get("strategy_family"), pending.get("strategy_family"))
    denomination = _text(
        demand.get("treasury_denomination"), demand.get("treasuryDenomination"),
        demand.get("execution_asset"), pending.get("capital_denomination"),
    )

    identity_payload = {
        "requested_wei": max(0, requested),
        "authorized_wei": max(0, authorized),
        "deployed_wei": max(0, deployed),
        "capital_source": source,
        "strategy_family": family,
        "treasury_denomination": denomination,
        "internal_prime_loan_id": loan_id,
        "internal_prime_authority_id": authority_id,
    }
    identity_payload["capital_demand_id"] = _text(
        demand.get("demand_id"), demand.get("demandId"),
    ) or _canonical_hash(identity_payload, prefix="capital_demand")
    identity_payload["internal_prime_identity"] = _canonical_hash(
        {
            "loan_id": loan_id,
            "authority_id": authority_id,
            "source": source,
        },
        prefix="internal_prime",
    )
    identity_payload["committed_capital_transaction_id"] = _text(
        committed.get("transaction_id"), committed.get("transactionId")
    )
    return identity_payload


def build_canonical_settled_outcome(
    *,
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
    committed_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the immutable learning envelope after canonical settlement commit."""
    pending = _mapping(pending)
    outcome = _mapping(outcome)
    committed = _mapping(committed_record)
    lineage = _lineage(pending, outcome, committed)
    missing = [key for key, value in lineage.items() if not value]
    if missing:
        raise ValueError("incomplete_canonical_lineage:" + ",".join(missing))

    capital = _capital_identity(pending, committed)
    receipt_id = _text(outcome.get("tx_hash"), outcome.get("receipt_id"), committed.get("receipt_id"))
    settlement_status = _text(outcome.get("status"), committed.get("status"), "settled")
    action = _text(
        lineage.get("action"),
        outcome.get("action"),
        pending.get("action"),
        pending.get("aqe_action"),
        "trade",
    )
    operator_intent = _mapping(
        _mapping(pending.get("canonical_lineage")).get("operator_intent")
        or pending.get("operator_intent")
    )
    identity_payload = {
        **lineage,
        "receipt_id": receipt_id,
        "capital_demand_id": capital["capital_demand_id"],
        "internal_prime_identity": capital["internal_prime_identity"],
        "requested_wei": capital["requested_wei"],
        "authorized_wei": capital["authorized_wei"],
        "deployed_wei": capital["deployed_wei"],
    }
    outcome_identity = _canonical_hash(identity_payload, prefix="settled_outcome")

    return {
        "schema_version": "omar.settled_outcome.v1",
        "outcome_identity": outcome_identity,
        "lineage": lineage,
        "decision_id": lineage["decision_id"],
        "correlation_id": lineage["correlation_id"],
        "execution_id": lineage["execution_id"],
        "settlement_id": lineage["settlement_id"],
        "receipt_id": receipt_id,
        "tx_hash": receipt_id,
        "action": action,
        "opportunity_id": _text(pending.get("opportunity_id"), outcome.get("opportunity_id")),
        "route_id": _text(pending.get("route_id"), outcome.get("route_id")),
        "status": settlement_status,
        "ok": bool(outcome.get("truth_verified", outcome.get("ok", True))),
        "realized_net_usd": _float(outcome.get("realized_net_usd"), outcome.get("net_realized_usd")),
        "expected_net_usd": _float(outcome.get("expected_net_usd")),
        "amount_in_wei": _int(outcome.get("amount_in_wei"), pending.get("amount_in")),
        "realized_pnl_wei": _int(outcome.get("realized_pnl_wei"), outcome.get("realized_profit_after_gas_wei")),
        "realized_pnl_usd_micro": _int(outcome.get("realized_pnl_usd_micro"), outcome.get("realized_profit_after_gas_usd_micro")),
        "gas_cost_wei": _int(outcome.get("gas_cost_wei"), outcome.get("realized_gas_cost_wei")),
        "slippage_bps": _float(outcome.get("slippage_bps"), outcome.get("realized_slippage_bps")),
        "latency_ms": _float(outcome.get("latency_ms"), outcome.get("submit_to_receipt_ms")),
        "operator_intent": operator_intent,
        "capital_identity": capital,
        "committed_record": committed,
        "metadata": {
            "source": "phase2_canonical_outcome_ledger",
            "canonical_settlement_committed": True,
            "operator_intent": operator_intent,
            "capital_identity": capital,
            "lineage": lineage,
        },
    }


def settlement_hook(
    runtime: Any,
    *,
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
    committed_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Deterministic post-commit hook: canonical outcome -> OMAR observation.

    This hook is deliberately downstream of canonical settlement. It refuses to
    learn from an uncommitted record and refuses to fabricate missing lineage.
    """
    committed = _mapping(committed_record)
    if not bool(committed.get("ok", committed.get("settlementCommitted", False))):
        return {"ok": False, "eligible_for_learning": False, "reason_code": "settlement_not_committed"}

    canonical = build_canonical_settled_outcome(
        pending=pending,
        outcome=outcome,
        committed_record=committed,
    )
    omar = getattr(runtime, "_omar", None)
    if omar is None or not hasattr(omar, "observe_outcome"):
        return {
            "ok": False,
            "eligible_for_learning": False,
            "reason_code": "omar_observer_unavailable",
            "canonical_outcome": canonical,
        }
    result = omar.observe_outcome(
        decision_id=canonical["decision_id"],
        correlation_id=canonical["correlation_id"],
        execution_id=canonical["execution_id"],
        settlement_id=canonical["settlement_id"],
        action=canonical["action"],
        tx_hash=canonical["tx_hash"],
        reward_scaled=canonical["realized_pnl_wei"] - canonical["gas_cost_wei"],
        state_key=_text(_mapping(pending.get("brain")).get("rl_state"), pending.get("rl_state"), "unknown"),
        role=_text(_mapping(pending.get("brain")).get("role"), "ARBITRAGE_AGENT"),
        latency_ms=canonical["latency_ms"],
        outcome_truth_verified=bool(canonical["ok"]),
        metadata=canonical["metadata"],
    )
    return {
        "ok": bool(_mapping(result).get("ok", True)),
        "eligible_for_learning": bool(_mapping(result).get("eligible_for_learning", True)),
        "canonical_outcome": canonical,
        "observation": _mapping(result),
    }


# Stable alias for callers that prefer the explicit lifecycle name.
settlement_hook_observe_outcome = settlement_hook
