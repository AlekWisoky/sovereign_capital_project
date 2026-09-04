from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class DecisionEconomicContext:
    """Economic + delivery state carried unchanged across the trade lifecycle."""

    expected_profit_after_costs_wei: int = 0
    expected_profit_after_costs_usd_micro: int = 0
    expected_gas_cost_wei: int = 0
    expected_slippage_bps: float = 0.0
    expected_latency_ms: float = 0.0
    delivery_budget_ms: float = 0.0
    delivery_headroom_ms: float = 0.0
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_decision_economic_context(
    opp: Any, *, decision: Any | None = None, cfg: Any | None = None
) -> DecisionEconomicContext:
    meta = _mapping(getattr(opp, "meta", None))
    decision_meta = _mapping(getattr(decision, "metadata", None))
    profitability = _mapping(meta.get("profitability"))
    capture = _mapping(meta.get("capture"))
    capture_metadata = _mapping(capture.get("metadata"))
    telemetry = _mapping(capture_metadata.get("telemetry"))
    endpoint = _mapping(capture_metadata.get("endpoint_selection"))
    route_plan = _mapping(capture_metadata.get("execution_route_plan"))
    if not route_plan:
        route_plan = _mapping(decision_meta.get("execution_route_plan"))

    expected_wei = _int(
        _first(
            decision_meta.get("expected_profit_after_costs_wei"),
            profitability.get("profit_after_costs_wei"),
            meta.get("expected_profit_after_costs_wei"),
            getattr(opp, "expected_profit_after_costs_wei", None),
            meta.get("safety", {}).get("profit_after_costs_wei")
            if isinstance(meta.get("safety"), Mapping)
            else None,
            getattr(opp, "expected_profit_raw", None),
        ),
        0,
    )
    expected_usd = _int(
        _first(
            decision_meta.get("expected_profit_after_costs_usd_micro"),
            profitability.get("expected_profit_after_gas_usd_micro"),
            profitability.get("profit_after_costs_usd_micro"),
            meta.get("expected_profit_after_costs_usd_micro"),
        ),
        0,
    )
    gas_wei = _int(
        _first(
            decision_meta.get("expected_gas_cost_wei"),
            profitability.get("gas_cost_wei"),
            meta.get("gas_cost_wei"),
            meta.get("safety", {}).get("gas_cost_wei")
            if isinstance(meta.get("safety"), Mapping)
            else None,
        ),
        0,
    )
    slip_bps = _float(
        _first(
            decision_meta.get("expected_slippage_bps"),
            route_plan.get("expected_slippage_bps"),
            capture_metadata.get("expected_slippage_bps"),
            meta.get("expected_slippage_bps"),
        ),
        0.0,
    )
    expected_latency = _float(
        _first(
            decision_meta.get("expected_latency_ms"),
            route_plan.get("expected_latency_ms"),
            route_plan.get("latency_ms"),
            endpoint.get("measured_latency_ms"),
            endpoint.get("best_latency_ms"),
            telemetry.get("lane_avg_latency_ms"),
            telemetry.get("best_latency_ms"),
            capture_metadata.get("lane_avg_latency_ms"),
            meta.get("expected_latency_ms"),
        ),
        0.0,
    )

    configured_budget = _first(
        decision_meta.get("delivery_budget_ms"),
        route_plan.get("delivery_budget_ms"),
        capture_metadata.get("delivery_budget_ms"),
        meta.get("delivery_budget_ms"),
        getattr(getattr(cfg, "execution", None), "delivery_budget_ms", None),
    )
    if configured_budget in (None, ""):
        deadline_seconds = _float(
            getattr(getattr(cfg, "execution", None), "deadline_seconds", 0), 0.0
        )
        configured_budget = deadline_seconds * 1000.0 if deadline_seconds > 0 else 0.0
        source = "deadline_seconds_fallback" if configured_budget else "unavailable"
    else:
        source = "explicit"
    budget = max(0.0, _float(configured_budget, 0.0))
    latency = max(0.0, expected_latency)
    return DecisionEconomicContext(
        expected_profit_after_costs_wei=max(0, expected_wei),
        expected_profit_after_costs_usd_micro=max(0, expected_usd),
        expected_gas_cost_wei=max(0, gas_wei),
        expected_slippage_bps=max(0.0, slip_bps),
        expected_latency_ms=latency,
        delivery_budget_ms=budget,
        delivery_headroom_ms=max(0.0, budget - latency) if budget else 0.0,
        source=source,
    )


def expectation_error(
    *,
    expected_profit_after_costs_wei: int,
    realized_net_wei: int,
    expected_latency_ms: float,
    realized_latency_ms: float,
) -> dict[str, Any]:
    expected = int(expected_profit_after_costs_wei or 0)
    realized = int(realized_net_wei or 0)
    error = realized - expected
    return {
        "expected_net_wei": str(expected),
        "realized_net_wei": str(realized),
        "net_error_wei": str(error),
        "net_error_pct": (error / abs(expected) * 100.0) if expected else 0.0,
        "expected_latency_ms": float(max(0.0, expected_latency_ms or 0.0)),
        "realized_latency_ms": float(max(0.0, realized_latency_ms or 0.0)),
        "latency_error_ms": float((realized_latency_ms or 0.0) - (expected_latency_ms or 0.0)),
    }
