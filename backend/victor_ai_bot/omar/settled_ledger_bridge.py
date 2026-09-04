from __future__ import annotations

from typing import Any, Mapping

from victor_ai_bot.runtime_services.settled_outcome_lineage import (
    CanonicalSettledOutcomeLineage,
    resolve_settled_lineage,
)

from .operator_intent import OperatorIntentSnapshot
from .real_learning import CapitalAuthoritySnapshot, OmarRealLearningLoop


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _int(*values: Any) -> int:
    value = _first(*values)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(*values: Any) -> float:
    value = _first(*values)
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _operator_intent(lineage: CanonicalSettledOutcomeLineage) -> OperatorIntentSnapshot:
    """Rehydrate the immutable decision-time operator context from the ledger."""
    raw = _mapping(lineage.operator_intent)
    return OperatorIntentSnapshot(
        control_mode=str(raw.get("control_mode") or raw.get("controlMode") or ""),
        aggression_mode=str(
            raw.get("aggression_mode") or raw.get("aggressionMode") or "balanced"
        ),
        brain_mode=str(raw.get("brain_mode") or raw.get("brainMode") or "off"),
        risk_multiplier=_float(raw.get("risk_multiplier"), raw.get("riskMultiplier"), 1.0),
        force_send_mode=str(
            raw.get("force_send_mode") or raw.get("forceSendMode") or ""
        ),
        force_gas_mode=str(
            raw.get("force_gas_mode") or raw.get("forceGasMode") or ""
        ),
        desired_wealth_goal=_mapping(
            raw.get("desired_wealth_goal")
            or raw.get("desiredWealthGoal")
            or lineage.wealth_goal
        ),
        ai_recommendation=_mapping(
            raw.get("ai_recommendation")
            or raw.get("aiRecommendation")
            or lineage.ai_recommendation
        ),
        source=str(raw.get("source") or "settled_ledger"),
    )


def _capital_authority(lineage: CanonicalSettledOutcomeLineage) -> CapitalAuthoritySnapshot:
    """Rehydrate the authoritative capital snapshot carried by the settled ledger."""
    raw = _mapping(lineage.capital_engine_state)
    family = _mapping(
        raw.get("family_allocatable_wei") or raw.get("familyAllocatableWei")
    )
    return CapitalAuthoritySnapshot(
        authority_id=str(raw.get("authority_id") or raw.get("authorityId") or "ledger"),
        available_wei=max(0, _int(raw.get("available_wei"), raw.get("availableWei"))),
        allocatable_wei=max(0, _int(raw.get("allocatable_wei"), raw.get("allocatableWei"))),
        family_allocatable_wei={str(k): max(0, _int(v)) for k, v in family.items()},
        status=str(raw.get("status") or "unknown"),
        freshness_class=str(
            raw.get("freshness_class")
            or raw.get("freshnessClass")
            or "settled_snapshot"
        ),
        reason_codes=[
            str(x)
            for x in (raw.get("reason_codes") or raw.get("reasonCodes") or [])
            if str(x)
        ],
        source=str(raw.get("source") or "capital_engine_state"),
    )


def ingest_settled_ledger_record(
    loop: OmarRealLearningLoop,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Feed one canonical settled-ledger record into OMAR's real learning loop.

    The ledger remains the source of settled truth. This bridge only translates
    the already-settled record into OMAR's decision/execution/outcome interfaces;
    it cannot authorize a trade or alter capital authority.
    """

    lineage: CanonicalSettledOutcomeLineage = resolve_settled_lineage(row)
    if not lineage.complete:
        return {
            "ok": False,
            "eligible_for_learning": False,
            "reason_code": "incomplete_settled_lineage",
            "reason_codes": list(lineage.reason_codes),
            "lineage": lineage.to_dict(),
        }

    source = dict(row)
    metadata = _mapping(source.get("metadata"))
    execution_meta = _mapping(metadata.get("execution"))
    outcome_meta = _mapping(metadata.get("outcome"))
    state = _mapping(metadata.get("state"))
    if not state:
        state = _mapping(metadata.get("decision_state"))
    operator_intent = _operator_intent(lineage)
    capital_authority = _capital_authority(lineage)

    decision = getattr(loop, "_decisions", {}).get(lineage.decision_id)
    if decision is None:
        loop.record_decision(
            decision_id=lineage.decision_id,
            correlation_id=lineage.correlation_id,
            action=lineage.action or "trade",
            opp_id=lineage.opportunity_id,
            route_id=lineage.route_id,
            policy_version=lineage.policy_version,
            state=state,
            capital_authority=capital_authority,
            operator_intent=operator_intent,
            metadata={
                "source": "settled_ledger",
                "transaction_id": lineage.transaction_id,
                "receipt_id": lineage.receipt_id,
                "outcome_id": lineage.outcome_id,
                "sizing_id": lineage.sizing_id,
                "wealth_goal": dict(lineage.wealth_goal),
                "ai_recommendation": dict(lineage.ai_recommendation),
                "canonical_lineage": lineage.to_dict(),
            },
        )

    execution = getattr(loop, "_executions", {}).get(lineage.execution_id)
    if execution is None:
        loop.bind_execution(
            decision_id=lineage.decision_id,
            correlation_id=lineage.correlation_id,
            execution_id=lineage.execution_id,
            status=str(
                _first(execution_meta.get("status"), source.get("execution_status"), "executed")
            ),
            action=lineage.action or "trade",
            tx_hash=lineage.receipt_id,
            fill_quantity=_float(
                execution_meta.get("fill_quantity"), metadata.get("fill_quantity")
            ),
            fill_price=_float(
                execution_meta.get("fill_price"), metadata.get("fill_price")
            ),
            slippage_bps=_float(
                execution_meta.get("slippage_bps"),
                metadata.get("realized_slippage_bps"),
                source.get("realized_slippage_bps"),
            ),
            gas_wei=_int(execution_meta.get("gas_wei"), metadata.get("gas_cost_wei")),
            latency_ms=lineage.latency_ms,
            metadata={
                "source": "settled_ledger",
                "latency_class": lineage.latency_class,
                "transaction_id": lineage.transaction_id,
                "outcome_id": lineage.outcome_id,
                "sizing_id": lineage.sizing_id,
            },
        )

    # The canonical ledger's realized_profit_after_gas_wei is already net of gas.
    # OmarRealLearningLoop historically subtracts realized_gas_wei again, which
    # double-counts gas. Reconstruct the pre-gas realized amount for that API so
    # the learning reward subtracts gas exactly once.
    realized_after_gas_wei = _int(
        outcome_meta.get("realized_after_gas_wei"),
        outcome_meta.get("realized_profit_after_gas_wei"),
        metadata.get("realized_profit_after_gas_wei"),
        metadata.get("realized_after_gas_wei"),
    )
    realized_gas_wei = _int(
        outcome_meta.get("realized_gas_wei"),
        metadata.get("gas_cost_wei"),
    )
    realized_pnl_wei = realized_after_gas_wei + max(0, realized_gas_wei)
    realized_pnl_usd_micro = _int(
        outcome_meta.get("realized_pnl_usd_micro"),
        metadata.get("realized_profit_after_gas_usd_micro"),
    )
    risk_cost_wei = _int(
        outcome_meta.get("risk_cost_wei"),
        metadata.get("risk_cost_wei"),
    )

    canonical_economics = lineage.to_dict()
    attribution = loop.settle_outcome(
        decision_id=lineage.decision_id,
        correlation_id=lineage.correlation_id,
        execution_id=lineage.execution_id,
        settlement_id=lineage.settlement_id,
        status=lineage.status or "settled",
        realized_pnl_wei=realized_pnl_wei,
        realized_pnl_usd_micro=realized_pnl_usd_micro,
        realized_slippage_bps=_float(
            outcome_meta.get("realized_slippage_bps"),
            metadata.get("realized_slippage_bps"),
        ),
        realized_gas_wei=max(0, realized_gas_wei),
        risk_cost_wei=risk_cost_wei,
        metadata={
            "source": "phase2_canonical_outcome_ledger",
            "transaction_id": lineage.transaction_id,
            "receipt_id": lineage.receipt_id,
            "latency_ms": lineage.latency_ms,
            "latency_class": lineage.latency_class,
            "outcome_id": lineage.outcome_id,
            "sizing_id": lineage.sizing_id,
            "wealth_goal": dict(lineage.wealth_goal),
            "ai_recommendation": dict(lineage.ai_recommendation),
            "canonical_lineage": canonical_economics,
            "canonical_economics": canonical_economics,
            "gas_accounting": "realized_after_gas_plus_gas_minus_gas_once",
        },
    )

    return {
        "ok": True,
        "eligible_for_learning": bool(attribution.eligible_for_learning),
        "lineage": canonical_economics,
        "attribution": attribution.to_dict(),
        "policy_update": dict(loop.last_update or {}),
    }
