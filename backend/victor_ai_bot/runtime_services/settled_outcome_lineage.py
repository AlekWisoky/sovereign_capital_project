from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping

from victor_ai_bot.learning.net_economics import resolve_net_economics

_LATENCY_FAST_MS = 450.0
_LATENCY_MODERATE_MS = 900.0
_REQUIRED = (
    "decision_id",
    "correlation_id",
    "execution_id",
    "outcome_id",
    "sizing_id",
    "settlement_id",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _nested(context: Mapping[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        value = context.get(name)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _latency_ms(row: Mapping[str, Any], metadata: Mapping[str, Any]) -> float:
    stages = _mapping(metadata.get("latency_stages_ms"))
    for value in (
        row.get("latency_ms"),
        row.get("submit_to_receipt_ms"),
        row.get("exec_e2e_ms"),
        metadata.get("latency_ms"),
        metadata.get("submit_to_receipt_ms"),
        metadata.get("exec_e2e_ms"),
        stages.get("total"),
    ):
        if value in (None, ""):
            continue
        parsed = _float(value, -1.0)
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
    decision_id: str = ""
    correlation_id: str = ""
    execution_id: str = ""
    outcome_id: str = ""
    sizing_id: str = ""
    settlement_id: str = ""
    transaction_id: str = ""
    receipt_id: str = ""
    action: str = ""
    opportunity_id: str = ""
    route_id: str = ""
    policy_version: str = ""
    chain: str = ""
    status: str = ""
    expected_gross_usd: float = 0.0
    expected_costs_usd: float = 0.0
    expected_net_usd: float = 0.0
    expected_latency_ms: float = 0.0
    latency_budget_ms: float = 0.0
    realized_gross_usd: float = 0.0
    realized_costs_usd: float = 0.0
    realized_net_usd: float = 0.0
    realized_latency_ms: float = 0.0
    net_prediction_error_usd: float = 0.0
    capital_engine_state: Dict[str, Any] = field(default_factory=dict)
    operator_intent: Dict[str, Any] = field(default_factory=dict)
    wealth_goal: Dict[str, Any] = field(default_factory=dict)
    ai_recommendation: Dict[str, Any] = field(default_factory=dict)
    latency_class: str = "unknown"
    complete: bool = False
    reason_codes: list[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        """Stable compatibility alias for the realized end-to-end latency."""
        return self.realized_latency_ms

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _economics(source: Mapping[str, Any], metadata: Mapping[str, Any]) -> Dict[str, float]:
    expected = _nested(metadata, "expected_economics", "expectedEconomics", "expected")
    realized = _nested(
        metadata, "realized_economics", "realizedEconomics", "settled_economics", "settledEconomics"
    )
    costs = _nested(metadata, "costs", "settled_costs", "settledCosts")
    gross_expected = _float(
        _first(
            expected.get("gross_usd"),
            expected.get("gross_profit_usd"),
            metadata.get("expected_gross_usd"),
            source.get("expected_gross_usd"),
        )
    )
    costs_expected = _float(
        _first(
            expected.get("costs_usd"),
            expected.get("total_costs_usd"),
            metadata.get("expected_costs_usd"),
            source.get("expected_costs_usd"),
        )
    )
    net_expected = _float(
        _first(
            expected.get("net_usd"),
            expected.get("expected_net_usd"),
            metadata.get("expected_net_usd"),
            source.get("expected_net_usd"),
        ),
        gross_expected - costs_expected,
    )
    gross_realized = _float(
        _first(
            realized.get("gross_usd"),
            realized.get("gross_profit_usd"),
            metadata.get("realized_gross_usd"),
            source.get("realized_gross_usd"),
            _float(source.get("realized_profit_usd_micro")) / 1_000_000.0,
        )
    )
    net_realized = _float(
        _first(
            realized.get("signed_pnl_usd"),
            realized.get("net_realized_usd"),
            realized.get("realized_net_after_costs_usd"),
            metadata.get("settled_net_pnl_usd"),
            metadata.get("realized_net_usd"),
            source.get("realized_net_usd"),
        )
    )
    if net_realized == 0.0 and gross_realized != 0.0:
        net_realized = gross_realized - _float(
            _first(costs.get("total_costs_usd"), metadata.get("realized_costs_usd"))
        )
    costs_realized = _float(
        _first(
            realized.get("costs_usd"),
            realized.get("total_costs_usd"),
            metadata.get("realized_costs_usd"),
            costs.get("total_costs_usd"),
        ),
        max(0.0, gross_realized - net_realized),
    )
    return {
        "expected_gross_usd": gross_expected,
        "expected_costs_usd": costs_expected,
        "expected_net_usd": net_expected,
        "expected_latency_ms": _float(
            _first(expected.get("latency_ms"), metadata.get("expected_latency_ms"))
        ),
        "latency_budget_ms": _float(
            _first(
                expected.get("latency_budget_ms"),
                metadata.get("latency_budget_ms"),
                metadata.get("latencyBudgetMs"),
            )
        ),
        "realized_gross_usd": gross_realized,
        "realized_costs_usd": costs_realized,
        "realized_net_usd": net_realized,
    }


def resolve_settled_lineage(row: Mapping[str, Any]) -> CanonicalSettledOutcomeLineage:
    source = _mapping(row)
    metadata = _mapping(source.get("metadata"))
    nested = _mapping(source.get("lineage"))
    execution = _mapping(metadata.get("execution"))
    decision = _mapping(metadata.get("decision"))
    outcome = _mapping(metadata.get("outcome"))
    sizing = _nested(metadata, "sizing", "sizingDecision", "sizing_decision")
    capital = _nested(
        metadata,
        "capital_engine_state",
        "capitalEngineState",
        "capital_authority",
        "capitalAuthority",
    )
    intent = _nested(metadata, "operator_intent", "operatorIntent")
    goal = _nested(metadata, "wealth_goal", "wealthGoal")
    ai = _nested(metadata, "ai_recommendation", "aiRecommendation")
    decision_id = _text(
        _first(
            nested.get("decision_id"),
            nested.get("decisionId"),
            source.get("decision_id"),
            source.get("decisionId"),
            metadata.get("decision_id"),
            metadata.get("decisionId"),
            decision.get("decision_id"),
            decision.get("decisionId"),
        )
    )
    correlation_id = _text(
        _first(
            nested.get("correlation_id"),
            nested.get("correlationId"),
            source.get("correlation_id"),
            source.get("correlationId"),
            metadata.get("correlation_id"),
            metadata.get("correlationId"),
            decision.get("correlation_id"),
            decision.get("correlationId"),
            execution.get("correlation_id"),
            execution.get("correlationId"),
        )
    )
    execution_id = _text(
        _first(
            nested.get("execution_id"),
            nested.get("executionId"),
            source.get("execution_id"),
            source.get("executionId"),
            metadata.get("execution_id"),
            metadata.get("executionId"),
            execution.get("execution_id"),
            execution.get("executionId"),
        )
    )
    outcome_id = _text(
        _first(
            nested.get("outcome_id"),
            nested.get("outcomeId"),
            source.get("outcome_id"),
            source.get("outcomeId"),
            metadata.get("outcome_id"),
            metadata.get("outcomeId"),
            outcome.get("outcome_id"),
            outcome.get("outcomeId"),
            source.get("settlement_id"),
            metadata.get("settlement_id"),
        )
    )
    settlement_id = _text(
        _first(
            nested.get("settlement_id"),
            nested.get("settlementId"),
            source.get("settlement_id"),
            source.get("settlementId"),
            metadata.get("settlement_id"),
            metadata.get("settlementId"),
            outcome.get("settlement_id"),
            outcome.get("settlementId"),
            outcome_id,
        )
    )
    sizing_id = _text(
        _first(
            nested.get("sizing_id"),
            nested.get("sizingId"),
            source.get("sizing_id"),
            source.get("sizingId"),
            metadata.get("sizing_id"),
            metadata.get("sizingId"),
            sizing.get("sizing_id"),
            sizing.get("sizingId"),
        )
    )
    identities = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "outcome_id": outcome_id,
        "sizing_id": sizing_id,
        "settlement_id": settlement_id,
    }
    reasons = [f"missing_{name}" for name, value in identities.items() if not _text(value)]
    latency = _latency_ms(source, metadata)
    econ = _economics(source, metadata)
    try:
        resolved = resolve_net_economics(
            type(
                "Outcome",
                (),
                {
                    "context": metadata,
                    "realized_gas_cost_usd_micro": _float(
                        source.get("realized_gas_cost_usd_micro")
                    ),
                    "realized_profit_after_gas_usd_micro": _float(
                        source.get("realized_profit_after_gas_usd_micro")
                    ),
                    "realized_profit_usd_micro": _float(source.get("realized_profit_usd_micro")),
                    "ok": bool(source.get("ok", source.get("receipt_status") == 1)),
                    "latency_ms": latency,
                },
            )()
        )
        if resolved.complete:
            econ["realized_net_usd"] = resolved.net_profit_after_costs_usd
    except (AttributeError, TypeError, ValueError):
        pass
    return CanonicalSettledOutcomeLineage(
        decision_id=decision_id,
        correlation_id=correlation_id,
        execution_id=execution_id,
        outcome_id=outcome_id,
        sizing_id=sizing_id,
        settlement_id=settlement_id,
        transaction_id=_text(_first(source.get("transaction_id"), source.get("transactionId"))),
        receipt_id=_text(
            _first(
                source.get("receipt_id"),
                source.get("receiptId"),
                source.get("tx_hash"),
                metadata.get("tx_hash"),
            )
        ),
        action=_text(
            _first(
                nested.get("action"),
                source.get("action"),
                metadata.get("action"),
                execution.get("action"),
            )
        ),
        opportunity_id=_text(
            _first(
                nested.get("opportunity_id"),
                nested.get("opportunityId"),
                source.get("opportunity_id"),
                source.get("opportunityId"),
                metadata.get("opportunity_id"),
                metadata.get("opportunityId"),
            )
        ),
        route_id=_text(
            _first(
                nested.get("route_id"),
                nested.get("routeId"),
                source.get("route_id"),
                source.get("routeId"),
                metadata.get("route_id"),
            )
        ),
        policy_version=_text(
            _first(
                nested.get("policy_version"),
                nested.get("policyVersion"),
                source.get("policy_version"),
                metadata.get("policy_version"),
            )
        ),
        chain=_text(_first(source.get("chain"), metadata.get("chain"))),
        status=_text(_first(source.get("status"), metadata.get("status"), outcome.get("status"))),
        **econ,
        realized_latency_ms=latency,
        net_prediction_error_usd=econ["realized_net_usd"] - econ["expected_net_usd"],
        capital_engine_state=capital,
        operator_intent=intent,
        wealth_goal=goal,
        ai_recommendation=ai,
        latency_class=latency_class(latency),
        complete=not reasons,
        reason_codes=reasons,
        metadata={**metadata, "lineageResolved": True},
    )


def attach_settled_lineage(row: Mapping[str, Any]) -> Dict[str, Any]:
    payload = dict(row)
    lineage = resolve_settled_lineage(payload)
    payload["lineage"] = lineage.to_dict()
    for key in (
        "decision_id",
        "correlation_id",
        "execution_id",
        "outcome_id",
        "sizing_id",
        "settlement_id",
        "latency_ms",
        "latency_class",
        "expected_gross_usd",
        "expected_costs_usd",
        "expected_net_usd",
        "expected_latency_ms",
        "latency_budget_ms",
        "realized_gross_usd",
        "realized_costs_usd",
        "realized_net_usd",
        "realized_latency_ms",
        "net_prediction_error_usd",
    ):
        payload[key] = getattr(lineage, key)
    return payload


def settled_lineage_rows(rows: Iterable[Mapping[str, Any]]) -> list[CanonicalSettledOutcomeLineage]:
    return [resolve_settled_lineage(row) for row in rows if isinstance(row, Mapping)]
