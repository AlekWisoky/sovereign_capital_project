from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping

from victor_ai_bot.learning.net_economics import resolve_net_economics


_LATENCY_FAST_MS = 450.0
_LATENCY_MODERATE_MS = 900.0


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


def _latency_ms(row: Mapping[str, Any], metadata: Mapping[str, Any]) -> float:
    stages_map = _mapping(metadata.get("latency_stages_ms"))
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
    """First-class identity and economic truth for one settled trade.

    This is an attribution record, not an authorization object. It resolves the
    same decision/execution/outcome identity that existed before settlement and
    carries expected-vs-realized economics so OMAR learns from settled truth.
    """

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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_REQUIRED = (
    "decision_id",
    "correlation_id",
    "execution_id",
    "outcome_id",
    "sizing_id",
    "settlement_id",
)


def _nested(context: Mapping[str, Any], *names: str) -> Dict[str, Any]:
    for name in names:
        value = context.get(name)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _usd(context: Mapping[str, Any], *keys: str) -> float:
    value = _first(*(context.get(key) for key in keys))
    return _float(value, 0.0)


def _economic_fields(source: Mapping[str, Any], metadata: Mapping[str, Any]) -> Dict[str, float]:
    expected = _nested(metadata, "expected_economics", "expectedEconomics", "expected")
    realized = _nested(metadata, "realized_economics", "realizedEconomics", "settled_economics", "settledEconomics")
    costs = _nested(metadata, "costs", "settled_costs", "settledCosts")

    expected_gross = _float(_first(
        expected.get("gross_usd"), expected.get("gross_profit_usd"),
        metadata.get("expected_gross_usd"), source.get("expected_gross_usd"),
    ), 0.0)
    expected_costs = _float(_first(
        expected.get("costs_usd"), expected.get("total_costs_usd"),
        metadata.get("expected_costs_usd"), source.get("expected_costs_usd"),
    ), 0.0)
    expected_net = _float(_first(
        expected.get("net_usd"), expected.get("expected_net_usd"),
        metadata.get("expected_net_usd"), source.get("expected_net_usd"),
    ), expected_gross - expected_costs)

    realized_gross = _float(_first(
        realized.get("gross_usd"), realized.get("gross_profit_usd"),
        metadata.get("realized_gross_usd"), source.get("realized_gross_usd"),
        _float(source.get("realized_profit_usd_micro"), 0.0) / 1_000_000.0,
    ), 0.0)
    realized_net = _float(_first(
        realized.get("signed_pnl_usd"), realized.get("net_realized_usd"),
        realized.get("realized_net_after_costs_usd"), metadata.get("settled_net_pnl_usd"),
        metadata.get("realized_net_usd"), source.get("realized_net_usd"),
    ), 0.0)
    if realized_net == 0.0 and realized_gross != 0.0:
        realized_net = realized_gross - _float(_first(
            costs.get("total_costs_usd"), metadata.get("realized_costs_usd"),
        ), 0.0)

    realized_costs = _float(_first(
        realized.get("costs_usd"), realized.get("total_costs_usd"),
        metadata.get("realized_costs_usd"), costs.get("total_costs_usd"),
    ), max(0.0, realized_gross - realized_net))

    return {
        "expected_gross_usd": expected_gross,
        "expected_costs_usd": expected_costs,
        "expected_net_usd": expected_net,
        "expected_latency_ms": _float(_first(
            expected.get("latency_ms"), metadata.get("expected_latency_ms"),
        ), 0.0),
        "latency_budget_ms": _float(_first(
            expected.get("latency_budget_ms"), metadata.get("latency_budget_ms"),
            metadata.get("latencyBudgetMs"),
        ), 0.0),
        "realized_gross_usd": realized_gross,
        "realized_costs_usd": realized_costs,
        "realized_net_usd": realized_net,
    }


def resolve_settled_lineage(row: Mapping[str, Any]) -> CanonicalSettledOutcomeLineage:
    """Resolve complete decision -> execution -> settled outcome lineage."""

    source = _mapping(row)
    metadata = _mapping(source.get("metadata"))
    nested = _mapping(source.get("lineage"))
    execution = _mapping(metadata.get("execution"))
    decision = _mapping(metadata.get("decision"))
    outcome = _mapping(metadata.get("outcome"))
    sizing = _nested(metadata, "sizing", "sizingDecision", "sizing_decision")
    capital = _nested(metadata, "capital_engine_state", "capitalEngineState", "capital_authority", "capitalAuthority")
    intent = _nested(metadata, "operator_intent", "operatorIntent")
    goal = _nested(metadata, "wealth_goal", "wealthGoal")
    ai = _nested(metadata, "ai_recommendation", "aiRecommendation")

    decision_id = _text(_first(
        nested.get("decision_id"), nested.get("decisionId"), source.get("decision_id"),
        source.get("decisionId"), metadata.get("decision_id"), metadata.get("decisionId"),
        decision.get("decision_id"), decision.get("decisionId"),
    ))
    correlation_id = _text(_first(
        nested.get("correlation_id"), nested.get("correlationId"), source.get("correlation_id"),
        source.get("correlationId"), metadata.get("correlation_id"), metadata.get("correlationId"),
        decision.get("correlation_id"), decision.get("correlationId"),
        execution.get("correlation_id"), execution.get("correlationId"),
    ))
    execution_id = _text(_first(
        nested.get("execution_id"), nested.get("executionId"), source.get("execution_id"),
        source.get("executionId"), metadata.get("execution_id"), metadata.get("executionId"),
        execution.get("execution_id"), execution.get("executionId"),
    ))
    outcome_id = _text(_first(
        nested.get("outcome_id"), nested.get("outcomeId"), source.get("outcome_id"),
        source.get("outcomeId"), metadata.get("outcome_id"), metadata.get("outcomeId"),
        outcome.get("outcome_id"), outcome.get("outcomeId"),
        source.get("settlement_id"), metadata.get("settlement_id"),
    ))
    settlement_id = _text(_first(
        nested.get("settlement_id"), nested.get("settlementId"), source.get("settlement_id"),
        source.get("settlementId"), metadata.get("settlement_id"), metadata.get("settlementId"),
        outcome.get("settlement_id"), outcome.get("settlementId"), outcome_id,
    ))
    sizing_id = _text(_first(
        nested.get("sizing_id"), nested.get("sizingId"), source.get("sizing_id"),
        source.get("sizingId"), metadata.get("sizing_id"), metadata.get("sizingId"),
        sizing.get("sizing_id"), sizing.get("sizingId"),
    ))

    reasons = [f"missing_{name}" for name in _REQUIRED if not _text(locals()[name])]
    latency = _latency_ms(source, metadata)
    economics = _economic_fields(source, metadata)

    # Reuse the authoritative settled economics resolver when the row already
    # has an outcome-shaped object. Its signed net P&L is the learning truth.
    try:
        resolved_economics = resolve_net_economics(type("Outcome", (), {
            "context": metadata,
            "realized_gas_cost_usd_micro": _float(source.get("realized_gas_cost_usd_micro"), 0.0),
            "realized_profit_after_gas_usd_micro": _float(source.get("realized_profit_after_gas_usd_micro"), 0.0),
            "realized_profit_usd_micro": _float(source.get("realized_profit_usd_micro"), 0.0),
            "ok": bool(source.get("ok", source.get("receipt_status") == 1)),
            "latency_ms": latency,
        })())
        if resolved_economics.complete:
            economics["realized_net_usd"] = resolved_economics.net_profit_after_costs_usd
            if economics["realized_gross_usd"] == 0.0:
                economics["realized_gross_usd"] = resolved_economics.gross_profit_usd
            if economics["realized_costs_usd"] == 0.0:
                economics["realized_costs_usd"] = max(0.0, economics["realized_gross_usd"] - economics["realized_net_usd"])
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
        receipt_id=_text(_first(source.get("receipt_id"), source.get("receiptId"), metadata.get("tx_hash"), source.get("tx_hash"))),
        action=_text(_first(nested.get("action"), source.get("action"), metadata.get("action"), execution.get("action"))),
        opportunity_id=_text(_first(
            nested.get("opportunity_id"), nested.get("opportunityId"), source.get("opportunity_id"),
            source.get("opportunityId"), metadata.get("opportunity_id"), metadata.get("opportunityId"),
        )),
        route_id=_text(_first(nested.get("route_id"), nested.get("routeId"), source.get("route_id"), source.get("routeId"), metadata.get("route_id"))),
        policy_version=_text(_first(nested.get("policy_version"), nested.get("policyVersion"), source.get("policy_version"), metadata.get("policy_version"))),
        chain=_text(_first(source.get("chain"), metadata.get("chain"))),
        status=_text(_first(source.get("status"), metadata.get("status"), outcome.get("status"))),
        expected_gross_usd=economics["expected_gross_usd"],
        expected_costs_usd=economics["expected_costs_usd"],
        expected_net_usd=economics["expected_net_usd"],
        expected_latency_ms=economics["expected_latency_ms"],
        latency_budget_ms=economics["latency_budget_ms"],
        realized_gross_usd=economics["realized_gross_usd"],
        realized_costs_usd=economics["realized_costs_usd"],
        realized_net_usd=economics["realized_net_usd"],
        realized_latency_ms=latency,
        net_prediction_error_usd=economics["realized_net_usd"] - economics["expected_net_usd"],
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
    """Return an enriched settled ledger payload with identity and economics."""
    payload = dict(row)
    lineage = resolve_settled_lineage(payload)
    payload["lineage"] = lineage.to_dict()
    for key in (
        "decision_id", "correlation_id", "execution_id", "outcome_id", "sizing_id", "settlement_id",
        "latency_ms", "latency_class", "expected_gross_usd", "expected_costs_usd", "expected_net_usd",
        "expected_latency_ms", "latency_budget_ms", "realized_gross_usd", "realized_costs_usd",
        "realized_net_usd", "realized_latency_ms", "net_prediction_error_usd",
    ):
        payload[key] = getattr(lineage, key)
    return payload


def settled_lineage_rows(rows: Iterable[Mapping[str, Any]]) -> list[CanonicalSettledOutcomeLineage]:
    return [resolve_settled_lineage(row) for row in rows if isinstance(row, Mapping)]
