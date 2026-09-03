from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping


_LATENCY_FAST_MS = 450.0
_LATENCY_MODERATE_MS = 900.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _latency_ms(row: Mapping[str, Any], metadata: Mapping[str, Any]) -> float:
    stages = metadata.get("latency_stages_ms")
    stages_map = _mapping(stages)
    candidates = (
        row.get("latency_ms"),
        row.get("submit_to_receipt_ms"),
        row.get("exec_e2e_ms"),
        metadata.get("latency_ms"),
        metadata.get("submit_to_receipt_ms"),
        metadata.get("exec_e2e_ms"),
        stages_map.get("total"),
    )
    for value in candidates:
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    return 0.0


def latency_class(ms: float) -> str:
    value = max(0.0, float(ms or 0.0))
    if value <= _LATENCY_FAST_MS:
        return "fast"
    if value <= _LATENCY_MODERATE_MS:
        return "moderate"
    return "slow"


@dataclass(frozen=True)
class CanonicalSettledOutcomeLineage:
    """Canonical lineage resolved directly from a settled ledger transaction.

    The record is attribution-only. It never authorizes execution or capital.
    Learning eligibility requires the exact decision, correlation, execution,
    settlement, and action identity. Latency remains a realized delivery feature.
    """

    decision_id: str = ""
    correlation_id: str = ""
    execution_id: str = ""
    settlement_id: str = ""
    transaction_id: str = ""
    receipt_id: str = ""
    action: str = ""
    opportunity_id: str = ""
    route_id: str = ""
    policy_version: str = ""
    chain: str = ""
    status: str = ""
    latency_ms: float = 0.0
    latency_class: str = "unknown"
    complete: bool = False
    reason_codes: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Action is part of the learning identity: a result without an exact action
# cannot be attributed to a policy decision and must never update OMAR.
_REQUIRED = ("decision_id", "correlation_id", "execution_id", "settlement_id", "action")


def resolve_settled_lineage(row: Mapping[str, Any]) -> CanonicalSettledOutcomeLineage:
    """Resolve the complete decision -> execution -> settlement -> action chain."""

    source = _mapping(row)
    metadata = _mapping(source.get("metadata"))
    nested = _mapping(source.get("lineage"))
    execution = _mapping(metadata.get("execution"))
    decision = _mapping(metadata.get("decision"))
    outcome = _mapping(metadata.get("outcome"))
    phase7 = _mapping(source.get("phase7_context")) or _mapping(metadata.get("phase7_context"))
    phase7_decision = _mapping(phase7.get("decision"))

    decision_id = _first(
        nested.get("decision_id"), nested.get("decisionId"),
        source.get("decision_id"), source.get("decisionId"),
        metadata.get("decision_id"), metadata.get("decisionId"),
        decision.get("decision_id"), decision.get("decisionId"),
        phase7_decision.get("decision_id"), phase7_decision.get("decisionId"),
    )
    correlation_id = _first(
        nested.get("correlation_id"), nested.get("correlationId"),
        source.get("correlation_id"), source.get("correlationId"),
        metadata.get("correlation_id"), metadata.get("correlationId"),
        decision.get("correlation_id"), decision.get("correlationId"),
        execution.get("correlation_id"), execution.get("correlationId"),
        phase7_decision.get("correlation_id"), phase7_decision.get("correlationId"),
    )
    execution_id = _first(
        nested.get("execution_id"), nested.get("executionId"),
        source.get("execution_id"), source.get("executionId"),
        metadata.get("execution_id"), metadata.get("executionId"),
        execution.get("execution_id"), execution.get("executionId"),
        _mapping(phase7.get("execution")).get("execution_id"),
        _mapping(phase7.get("execution")).get("executionId"),
    )
    settlement_id = _first(
        nested.get("settlement_id"), nested.get("settlementId"),
        source.get("settlement_id"), source.get("settlementId"),
        metadata.get("settlement_id"), metadata.get("settlementId"),
        outcome.get("settlement_id"), outcome.get("settlementId"),
    )
    action = _first(
        nested.get("action"), source.get("action"), metadata.get("action"),
        decision.get("action"), execution.get("action"), phase7_decision.get("action"),
    )

    latency = _latency_ms(source, metadata)
    reasons = []
    for field_name in _REQUIRED:
        if not _text(locals()[field_name]):
            reasons.append(f"missing_{field_name}")

    return CanonicalSettledOutcomeLineage(
        decision_id=decision_id,
        correlation_id=correlation_id,
        execution_id=execution_id,
        settlement_id=settlement_id,
        transaction_id=_first(source.get("transaction_id"), source.get("transactionId")),
        receipt_id=_first(source.get("receipt_id"), source.get("receiptId"), metadata.get("tx_hash")),
        action=action,
        opportunity_id=_first(
            nested.get("opportunity_id"), nested.get("opportunityId"),
            source.get("opportunity_id"), source.get("opportunityId"),
            metadata.get("opportunity_id"), metadata.get("opportunityId"),
            phase7_decision.get("opportunity_id"), phase7_decision.get("opportunityId"),
        ),
        route_id=_first(
            nested.get("route_id"), nested.get("routeId"),
            source.get("route_id"), source.get("routeId"), metadata.get("route_id"),
        ),
        policy_version=_first(
            nested.get("policy_version"), nested.get("policyVersion"),
            source.get("policy_version"), metadata.get("policy_version"),
            phase7_decision.get("policy_version"), phase7_decision.get("policyVersion"),
        ),
        chain=_first(source.get("chain"), metadata.get("chain")),
        status=_first(source.get("status"), metadata.get("status"), outcome.get("status")),
        latency_ms=latency,
        latency_class=latency_class(latency),
        complete=not reasons,
        reason_codes=reasons,
        metadata={
            **metadata,
            "lineageResolved": True,
            "phase7_context": phase7,
        },
    )


def attach_settled_lineage(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an enriched settled ledger payload with canonical lineage attached."""

    payload = dict(row)
    lineage = resolve_settled_lineage(payload)
    payload["lineage"] = lineage.to_dict()
    payload["decision_id"] = lineage.decision_id
    payload["correlation_id"] = lineage.correlation_id
    payload["execution_id"] = lineage.execution_id
    payload["settlement_id"] = lineage.settlement_id
    payload["action"] = lineage.action
    payload["latency_ms"] = lineage.latency_ms
    payload["latency_class"] = lineage.latency_class
    return payload


def settled_lineage_rows(rows: Iterable[Mapping[str, Any]]) -> list[CanonicalSettledOutcomeLineage]:
    return [resolve_settled_lineage(row) for row in rows if isinstance(row, Mapping)]
