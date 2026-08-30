from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ProfitAfterCosts:
    gross_profit_usd: float
    flashloan_fee_usd: float
    gas_cost_usd: float
    slippage_cost_usd: float
    execution_fee_usd: float
    prime_cost_usd: float
    safety_reserve_usd: float
    net_profit_usd: float
    net_roi_bps: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class RiskBudgetDecision:
    canonical_decision_id: str
    correlation_id: str
    sizing_id: str
    allowed: bool
    selected_size_mult: float
    max_size_mult: float
    risk_budget_usd: float
    estimated_loss_usd: float
    expected_net_profit_usd: float
    minimum_net_profit_usd: float
    minimum_net_roi_bps: float
    reason: str
    hard_constraints: tuple[str, ...]
    preference_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sizing_id(decision_id: str, correlation_id: str, route_id: str, provider: str, size_mult: float) -> str:
    body = "|".join(
        (_text(decision_id), _text(correlation_id), _text(route_id), _text(provider), f"{float(size_mult):.8f}")
    )
    return "sizing_" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def compute_profit_after_costs(
    *,
    gross_profit_usd: float,
    flashloan_fee_usd: float = 0.0,
    gas_cost_usd: float = 0.0,
    slippage_cost_usd: float = 0.0,
    execution_fee_usd: float = 0.0,
    prime_cost_usd: float = 0.0,
    safety_reserve_usd: float = 0.0,
    capital_base_usd: float = 0.0,
) -> ProfitAfterCosts:
    """Compute the economic quantity OMAR is allowed to learn from."""
    gross = _num(gross_profit_usd)
    costs = {
        "flashloan_fee_usd": max(0.0, _num(flashloan_fee_usd)),
        "gas_cost_usd": max(0.0, _num(gas_cost_usd)),
        "slippage_cost_usd": max(0.0, _num(slippage_cost_usd)),
        "execution_fee_usd": max(0.0, _num(execution_fee_usd)),
        "prime_cost_usd": max(0.0, _num(prime_cost_usd)),
        "safety_reserve_usd": max(0.0, _num(safety_reserve_usd)),
    }
    net = gross - sum(costs.values())
    base = max(0.0, _num(capital_base_usd))
    roi_bps = (net / base * 10_000.0) if base > 0.0 else 0.0
    return ProfitAfterCosts(
        gross_profit_usd=gross,
        **costs,
        net_profit_usd=net,
        net_roi_bps=roi_bps,
    )


def build_risk_budget(
    *,
    capital_available_usd: float,
    deployable_capital_usd: float,
    family_allocation_usd: float,
    max_borrow_usd: float,
    max_loss_usd: float,
    current_drawdown_pct: float,
    hard_stop: bool,
    governance_allowed: bool,
    capital_authority_fresh: bool,
    confidence: float,
    aggressiveness: float,
    goal_gap_pct: float,
) -> float:
    """Build a bounded loss budget from authoritative capital/risk inputs."""
    if not governance_allowed or hard_stop or not capital_authority_fresh:
        return 0.0

    capital_ceiling = min(
        max(0.0, _num(capital_available_usd)),
        max(0.0, _num(deployable_capital_usd)),
        max(0.0, _num(family_allocation_usd)),
        max(0.0, _num(max_borrow_usd)),
    )
    configured_loss = max(0.0, _num(max_loss_usd))
    if capital_ceiling <= 0.0 or configured_loss <= 0.0:
        return 0.0

    # Human/AI preferences can influence the budget only inside the hard cap.
    confidence_factor = _clip(confidence, 0.25, 1.0)
    aggression_factor = _clip(0.75 + 0.25 * _clip(aggressiveness, 0.0, 1.0), 0.75, 1.0)
    goal_factor = _clip(1.0 + max(0.0, _num(goal_gap_pct)) / 100.0 * 0.10, 1.0, 1.10)
    dd = max(0.0, _num(current_drawdown_pct))
    drawdown_factor = 0.50 if dd >= 8.0 else 0.75 if dd >= 5.0 else 0.90 if dd >= 2.0 else 1.0

    preferred = configured_loss * confidence_factor * aggression_factor * goal_factor * drawdown_factor
    return _clip(preferred, 0.0, min(configured_loss, capital_ceiling))


def choose_adaptive_size(
    *,
    canonical_decision_id: str,
    correlation_id: str,
    route_id: str,
    provider: str,
    requested_size_mult: float,
    candidates: Sequence[Mapping[str, Any]],
    risk_budget_usd: float,
    minimum_net_profit_usd: float,
    minimum_net_roi_bps: float,
    expected_loss_ratio: float,
    max_size_mult: float,
) -> RiskBudgetDecision:
    """Choose the largest *net-profitable* eligible candidate within hard limits."""
    decision_id = _text(canonical_decision_id)
    correlation = _text(correlation_id)
    budget = max(0.0, _num(risk_budget_usd))
    min_profit = max(0.0, _num(minimum_net_profit_usd))
    min_roi = _num(minimum_net_roi_bps)
    hard_max = max(0.0, _num(max_size_mult))
    requested = max(0.0, _num(requested_size_mult))
    loss_ratio = max(0.0, _num(expected_loss_ratio))

    if not decision_id or not correlation:
        return RiskBudgetDecision(
            decision_id,
            correlation,
            "",
            False,
            0.0,
            hard_max,
            budget,
            0.0,
            0.0,
            min_profit,
            min_roi,
            "missing_canonical_identity",
            ("canonical_decision_id_required", "correlation_id_required"),
            (),
        )

    eligible: list[dict[str, float]] = []
    for raw in candidates:
        row = dict(raw or {})
        size = _num(row.get("size_mult"))
        net_profit = _num(row.get("net_profit_usd", row.get("net_edge")))
        roi = _num(row.get("net_roi_bps"))
        estimated_loss = max(0.0, _num(row.get("estimated_loss_usd", size * loss_ratio)))
        if size <= 0.0 or size > hard_max + 1e-9:
            continue
        if net_profit < min_profit or roi < min_roi or estimated_loss > budget + 1e-9:
            continue
        eligible.append({"size": size, "net_profit": net_profit, "roi": roi, "loss": estimated_loss})

    if not eligible:
        return RiskBudgetDecision(
            decision_id,
            correlation,
            "",
            False,
            0.0,
            hard_max,
            budget,
            0.0,
            0.0,
            min_profit,
            min_roi,
            "no_size_passed_net_profit_and_risk_budget",
            ("max_size_mult", "risk_budget", "minimum_net_profit", "minimum_net_roi_bps"),
            ("requested_size_mult",),
        )

    # Primary objective is realized/expected net profit after costs; size is the
    # secondary preference, so larger size wins only when economics support it.
    winner = max(eligible, key=lambda x: (x["net_profit"], x["size"], -x["loss"]))
    size = min(winner["size"], hard_max)
    sizing_id = _sizing_id(decision_id, correlation, route_id, provider, size)
    preference = ("maximize_net_profit_after_costs", "requested_size_supported" if size >= requested else "requested_size_reduced")
    return RiskBudgetDecision(
        decision_id,
        correlation,
        sizing_id,
        True,
        round(size, 8),
        hard_max,
        budget,
        round(winner["loss"], 8),
        round(winner["net_profit"], 8),
        min_profit,
        min_roi,
        "largest_eligible_net_profit_candidate",
        ("max_size_mult", "risk_budget", "minimum_net_profit", "minimum_net_roi_bps"),
        preference,
    )


def learning_reward_from_settled_outcome(outcome: Mapping[str, Any]) -> float:
    """Use only truth-verified settled net economics for OMAR reward."""
    net = _num(outcome.get("realized_net_usd", outcome.get("realizedNetUsd")))
    expected = _num(outcome.get("expected_net_usd", outcome.get("expectedNetUsd")))
    verified = bool(outcome.get("truth_verified", outcome.get("outcome_truth_verified", False)))
    if not verified:
        return 0.0
    return _clip(net + 0.25 * (net - expected), -50.0, 50.0)
