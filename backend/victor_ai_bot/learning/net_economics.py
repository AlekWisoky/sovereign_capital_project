from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp
from typing import Any, Mapping


_SAFE = (TypeError, ValueError)


@dataclass(frozen=True)
class NetEconomics:
    """Settled economic truth used as OMAR's learning objective.

    Financial P&L is kept separate from delivery quality. Latency changes the
    learning reward but is never fabricated as a dollar cost and never changes
    the canonical settled P&L.
    """

    gross_profit_usd: float = 0.0
    gas_cost_usd: float = 0.0
    financing_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    execution_cost_usd: float = 0.0
    other_cost_usd: float = 0.0
    net_profit_after_costs_usd: float = 0.0
    expected_net_profit_after_costs_usd: float = 0.0
    latency_ms: float = 0.0
    latency_quality: float = 1.0
    learning_reward: float = 0.0
    source: str = "derived_from_settled_components"
    complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _float(value: Any, default: float = 0.0) -> float:
    if value in (None, "") or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except _SAFE:
        return float(default)


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _usd(mapping: Mapping[str, Any], *keys: str) -> float:
    return max(0.0, _float(_first(*(mapping.get(key) for key in keys)), 0.0))


def _nested(context: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    for name in names:
        value = context.get(name)
        if isinstance(value, Mapping):
            return value
    return {}


def resolve_net_economics(
    outcome: Any,
    *,
    latency_half_life_ms: float = 750.0,
) -> NetEconomics:
    """Resolve the canonical post-cost learning objective from one settlement.

    Priority order for realized net P&L is:
    1. explicitly settled signed net P&L;
    2. settled profit-after-gas minus observed financing/execution/slippage costs.

    Safety reserves and borrowed principal are not costs and are therefore never
    subtracted from realized P&L. Latency is a separate delivery-quality factor.
    """

    context = _mapping(getattr(outcome, "context", {}))
    costs = _nested(context, "costs", "settled_costs", "settledCosts")
    settled = _nested(context, "settled_economics", "settledEconomics", "settlement")
    borrowing = _nested(context, "borrowing", "internal_prime", "internalPrime")
    capture = _nested(context, "capture")

    explicit_net = _first(
        settled.get("signed_pnl_usd"),
        settled.get("net_realized_usd"),
        settled.get("realized_net_after_costs_usd"),
        context.get("settled_net_pnl_usd"),
        context.get("realized_net_after_costs_usd"),
        costs.get("net_realized_usd"),
    )

    gas_cost = max(
        _usd(costs, "gas_cost_usd", "gas_usd"),
        _usd(settled, "gas_cost_usd", "gas_usd"),
        _float(getattr(outcome, "realized_gas_cost_usd_micro", 0), 0.0) / 1_000_000.0,
    )

    financing_cost = _usd(
        costs,
        "financing_cost_usd",
        "borrow_cost_usd",
        "prime_cost_usd",
        "internal_prime_cost_usd",
    )
    if financing_cost <= 0.0:
        financing_cost = max(
            _usd(borrowing, "realized_cost_usd", "borrow_cost_usd"),
            _usd(settled, "borrow_cost_usd", "prime_cost_usd", "financing_cost_usd"),
        )

    slippage_cost = _usd(costs, "slippage_cost_usd", "realized_slippage_cost_usd")
    execution_cost = _usd(
        costs,
        "execution_cost_usd",
        "execution_fee_usd",
        "executor_fee_usd",
    )
    other_cost = _usd(costs, "other_cost_usd", "other_fees_usd")

    after_gas = max(
        0.0,
        _float(getattr(outcome, "realized_profit_after_gas_usd_micro", 0), 0.0)
        / 1_000_000.0,
    )
    gross_profit = max(
        0.0,
        _float(getattr(outcome, "realized_profit_usd_micro", 0), 0.0)
        / 1_000_000.0,
    )
    if gross_profit <= 0.0 and after_gas > 0.0:
        gross_profit = after_gas + gas_cost

    if explicit_net is not None:
        net_profit = _float(explicit_net, 0.0)
        source = "settled_authoritative"
    else:
        net_profit = after_gas - financing_cost - slippage_cost - execution_cost - other_cost
        # On a failed/reverted settlement, no trading profit exists but settled
        # gas is still a real economic loss.
        if not bool(getattr(outcome, "ok", False)):
            net_profit -= gas_cost
        source = "derived_from_settled_components"

    expected_net = _first(
        settled.get("expected_net_profit_after_costs_usd"),
        settled.get("expected_net_usd"),
        context.get("expected_net_profit_after_costs_usd"),
        context.get("expected_net_usd"),
        costs.get("expected_net_profit_after_costs_usd"),
    )
    expected_net_usd = _float(expected_net, 0.0) if expected_net is not None else 0.0

    latency = max(
        0.0,
        _float(
            _first(
                context.get("latency_ms"),
                capture.get("latency_ms"),
                settled.get("latency_ms"),
                getattr(outcome, "latency_ms", 0),
            ),
            0.0,
        ),
    )
    half_life = max(1.0, float(latency_half_life_ms))
    latency_quality = exp(-latency / half_life)

    # Positive/negative financial outcomes remain the dominant signal. Faster
    # delivery gets a bounded 0.50..1.00 multiplier instead of becoming a fake
    # financial fee. This teaches OMAR to prefer the same net edge delivered
    # sooner without allowing speed to turn a loss into a profit.
    learning_reward = net_profit * (0.50 + 0.50 * latency_quality)

    complete = bool(
        explicit_net is not None
        or gross_profit > 0.0
        or after_gas != 0.0
        or (not bool(getattr(outcome, "ok", False)) and gas_cost > 0.0)
    )

    return NetEconomics(
        gross_profit_usd=float(gross_profit),
        gas_cost_usd=float(gas_cost),
        financing_cost_usd=float(financing_cost),
        slippage_cost_usd=float(slippage_cost),
        execution_cost_usd=float(execution_cost),
        other_cost_usd=float(other_cost),
        net_profit_after_costs_usd=float(net_profit),
        expected_net_profit_after_costs_usd=float(expected_net_usd),
        latency_ms=float(latency),
        latency_quality=float(latency_quality),
        learning_reward=float(learning_reward),
        source=source,
        complete=complete,
    )
