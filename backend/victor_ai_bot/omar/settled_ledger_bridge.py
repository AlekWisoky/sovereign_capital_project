from __future__ import annotations

from typing import Any, Mapping

from victor_ai_bot.runtime_services.phase7_context_store import Phase7ContextStore
from victor_ai_bot.runtime_services.settled_outcome_lineage import (
    CanonicalSettledOutcomeLineage,
    resolve_settled_lineage,
)

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


def _phase7_context(loop: OmarRealLearningLoop, source: Mapping[str, Any], tx_hash: str) -> dict[str, Any]:
    direct = _mapping(source.get("phase7_context"))
    if direct:
        return direct
    metadata = _mapping(source.get("metadata"))
    direct = _mapping(metadata.get("phase7_context"))
    if direct:
        return direct
    try:
        store = Phase7ContextStore(data_dir=loop.data_dir, chain=loop.chain_name)
        return store.get(tx_hash)
    except (AttributeError, OSError, TypeError, ValueError):
        return {}


def ingest_settled_ledger_record(
    loop: OmarRealLearningLoop,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Feed one canonical settled-ledger record into OMAR's real learning loop.

    The settled ledger remains financial truth. Phase 7 context is attached for
    attribution only. OMAR cannot authorize a trade, capital movement, or bypass
    governance, and incomplete decision/correlation/execution/settlement/action
    identity is rejected before any policy update.
    """

    source = dict(row)
    tx_hash = str(_first(source.get("tx_hash"), source.get("txHash")) or "")
    phase7 = _phase7_context(loop, source, tx_hash)
    lineage_source = dict(source)
    if phase7 and "phase7_context" not in lineage_source:
        lineage_source["phase7_context"] = phase7

    lineage: CanonicalSettledOutcomeLineage = resolve_settled_lineage(lineage_source)
    if not lineage.complete:
        return {
            "ok": False,
            "eligible_for_learning": False,
            "reason_code": "incomplete_settled_lineage",
            "reason_codes": list(lineage.reason_codes),
            "lineage": lineage.to_dict(),
        }

    metadata = _mapping(source.get("metadata"))
    execution_meta = _mapping(metadata.get("execution"))
    outcome_meta = _mapping(metadata.get("outcome"))
    state = _mapping(metadata.get("state"))
    if not state:
        state = _mapping(metadata.get("decision_state"))

    decision = getattr(loop, "_decisions", {}).get(lineage.decision_id)
    if decision is None:
        loop.record_decision(
            decision_id=lineage.decision_id,
            correlation_id=lineage.correlation_id,
            action=lineage.action,
            opp_id=lineage.opportunity_id,
            route_id=lineage.route_id,
            policy_version=lineage.policy_version,
            state=state,
            metadata={
                "source": "settled_ledger",
                "transaction_id": lineage.transaction_id,
                "receipt_id": lineage.receipt_id,
                "phase7_context": phase7,
            },
        )

    execution = getattr(loop, "_executions", {}).get(lineage.execution_id)
    if execution is None:
        loop.bind_execution(
            decision_id=lineage.decision_id,
            correlation_id=lineage.correlation_id,
            execution_id=lineage.execution_id,
            status=str(_first(execution_meta.get("status"), source.get("execution_status"), "executed")),
            action=lineage.action,
            tx_hash=lineage.receipt_id,
            fill_quantity=_float(execution_meta.get("fill_quantity"), metadata.get("fill_quantity")),
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
                "phase7_context": phase7,
            },
        )

    realized_pnl_wei = _int(
        outcome_meta.get("realized_pnl_wei"),
        metadata.get("realized_profit_after_gas_wei"),
        metadata.get("realized_after_gas_wei"),
    )
    realized_pnl_usd_micro = _int(
        outcome_meta.get("realized_pnl_usd_micro"),
        metadata.get("realized_profit_after_gas_usd_micro"),
    )
    realized_gas_wei = _int(
        outcome_meta.get("realized_gas_wei"),
        metadata.get("gas_cost_wei"),
    )
    risk_cost_wei = _int(
        outcome_meta.get("risk_cost_wei"),
        metadata.get("risk_cost_wei"),
    )

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
        realized_gas_wei=realized_gas_wei,
        risk_cost_wei=risk_cost_wei,
        metadata={
            "source": "settled_ledger",
            "transaction_id": lineage.transaction_id,
            "receipt_id": lineage.receipt_id,
            "latency_ms": lineage.latency_ms,
            "latency_class": lineage.latency_class,
            "phase7_context": phase7,
            "lineage": lineage.to_dict(),
        },
    )
    return {
        "ok": True,
        "eligible_for_learning": bool(attribution.eligible_for_learning),
        "lineage": lineage.to_dict(),
        "phase7_context": phase7,
        "attribution": attribution.to_dict(),
        "policy_update": dict(loop.last_update or {}),
    }
