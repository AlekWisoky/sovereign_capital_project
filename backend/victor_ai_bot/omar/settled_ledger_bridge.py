from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from victor_ai_bot.runtime_services.settled_outcome_lineage import (
    CanonicalSettledOutcomeLineage,
    resolve_settled_lineage,
)

from .operator_intent import OperatorIntentSnapshot
from .real_learning import OmarRealLearningLoop


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _int(*values: Any) -> int:
    value = _first(*values)
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _float(*values: Any) -> float:
    value = _first(*values)
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _operator_intent(row: Mapping[str, Any], metadata: Mapping[str, Any]) -> OperatorIntentSnapshot:
    raw = _mapping(metadata.get("operator_intent")) or _mapping(row.get("operator_intent"))
    allowed = set(OperatorIntentSnapshot.__dataclass_fields__)
    payload = {key: value for key, value in raw.items() if key in allowed}
    if "desired_wealth_goal" not in payload:
        payload["desired_wealth_goal"] = _mapping(raw.get("goal"))
    if "ai_recommendation" not in payload:
        payload["ai_recommendation"] = _mapping(raw.get("recommendation"))
    return OperatorIntentSnapshot(**payload)


def ingest_settled_ledger_record(
    loop: OmarRealLearningLoop, row: Mapping[str, Any]
) -> dict[str, Any]:
    """Feed one canonical settled-ledger record into OMAR's real-learning loop."""
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
    capital_demand = _mapping(metadata.get("capital_demand"))
    state = _mapping(metadata.get("state")) or _mapping(metadata.get("decision_state"))
    operator_intent = _operator_intent(source, metadata)

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
            operator_intent=operator_intent,
            metadata={
                "source": "settled_ledger",
                "transaction_id": lineage.transaction_id,
                "receipt_id": lineage.receipt_id,
                "capital_demand": capital_demand,
            },
        )
    else:
        if capital_demand:
            decision.metadata.setdefault("capital_demand", dict(capital_demand))
        if (
            decision.operator_intent == OperatorIntentSnapshot()
            and operator_intent != OperatorIntentSnapshot()
        ):
            loop._decisions[lineage.decision_id] = replace(
                decision, operator_intent=operator_intent
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
            fill_price=_float(execution_meta.get("fill_price"), metadata.get("fill_price")),
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
                "capital_demand": capital_demand,
            },
        )

    attribution = loop.settle_outcome(
        decision_id=lineage.decision_id,
        correlation_id=lineage.correlation_id,
        execution_id=lineage.execution_id,
        settlement_id=lineage.settlement_id,
        status=lineage.status or "settled",
        realized_pnl_wei=_int(
            outcome_meta.get("realized_pnl_wei"),
            metadata.get("realized_profit_after_gas_wei"),
            metadata.get("realized_after_gas_wei"),
        ),
        realized_pnl_usd_micro=_int(
            outcome_meta.get("realized_pnl_usd_micro"),
            metadata.get("realized_profit_after_gas_usd_micro"),
        ),
        realized_slippage_bps=_float(
            outcome_meta.get("realized_slippage_bps"), metadata.get("realized_slippage_bps")
        ),
        realized_gas_wei=_int(outcome_meta.get("realized_gas_wei"), metadata.get("gas_cost_wei")),
        risk_cost_wei=_int(outcome_meta.get("risk_cost_wei"), metadata.get("risk_cost_wei")),
        metadata={
            "source": "settled_ledger",
            "transaction_id": lineage.transaction_id,
            "receipt_id": lineage.receipt_id,
            "latency_ms": lineage.latency_ms,
            "latency_class": lineage.latency_class,
            "capital_demand": capital_demand,
            "operator_intent": operator_intent.to_dict(),
            "lineage": lineage.to_dict(),
        },
    )
    return {
        "ok": True,
        "eligible_for_learning": bool(attribution.eligible_for_learning),
        "lineage": lineage.to_dict(),
        "capital_demand": capital_demand,
        "operator_intent": operator_intent.to_dict(),
        "attribution": attribution.to_dict(),
        "policy_update": dict(loop.last_update or {}),
    }
