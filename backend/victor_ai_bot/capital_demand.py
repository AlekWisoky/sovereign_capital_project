from __future__ import annotations

"""Canonical capital-demand composition.

This module answers one question before execution: *what capital demand is
actually fundable for this opportunity right now?*

It deliberately separates demand shaping from authority. Wealth goals,
aggressiveness and AI recommendations may modify a valid request, but they
can never create capital, bypass governance/risk limits, or exceed provider
capacity. The result is therefore a planning/decision input, not an execution
authorization.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


CAPITAL_MODES = {"v1_external_prime", "own_capital", "hybrid"}
AGGRESSION_MULTIPLIERS = {
    "conservative": 0.75,
    "balanced": 1.0,
    "aggressive": 1.15,
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _nonnegative(value: Any) -> float:
    return max(0.0, _float(value))


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _cap(value: float, upper: float) -> float:
    return max(0.0, min(max(0.0, value), max(0.0, upper)))


def _to_base_units(amount: Any, decimals: int) -> int:
    """Convert a human amount to integer token units without float leakage."""
    text = str(amount if amount is not None else 0).strip()
    if not text:
        return 0
    try:
        from decimal import Decimal, InvalidOperation

        value = Decimal(text)
        if not value.is_finite() or value <= 0:
            return 0
        return int(value * (Decimal(10) ** max(0, int(decimals))))
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return 0


@dataclass(frozen=True)
class CapitalDemandInput:
    """Inputs used to compose a fundable capital demand."""

    requested_amount: float
    strategy_family: str
    strategy_version: str = "V1"
    capital_mode: str = "v1_external_prime"
    treasury_available: float = 0.0
    treasury_allocatable: float = 0.0
    treasury_symbol: str = ""
    treasury_decimals: int = 18
    conversion_authorized: bool = False
    conversion_rate: float = 1.0
    provider_capacity: float = 0.0
    provider_fee_bps: float = 0.0
    current_exposure: float = 0.0
    exposure_limit: float = 0.0
    risk_limit: float = 0.0
    governance_limit: float = 0.0
    execution_plan_required: bool = True
    execution_plan_ready: bool = False
    latency_ms: float = 0.0
    freshness_ms: float = 0.0
    max_latency_ms: float = 0.0
    max_freshness_ms: float = 0.0
    prime_available: float = 0.0
    prime_capacity: float = 0.0
    prime_fee_bps: float = 0.0
    prime_collateral_available: float = 0.0
    wealth_goal_multiplier: float = 1.0
    aggressiveness: str = "balanced"
    aggressiveness_cap: float = 1.0
    ai_multiplier: float = 1.0
    ai_recommendation_id: str = ""
    ai_recommendation_reason: str = ""
    governance_approved: bool = True
    risk_approved: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapitalDemand:
    """Resolved demand and the binding authority behind it."""

    requested_amount: float
    shaped_amount: float
    fundable_amount: float
    capital_source: str
    capital_mode: str
    strategy_version: str
    strategy_family: str
    treasury_amount: float
    prime_amount: float
    provider_fee_bps: float
    prime_fee_bps: float
    conversion_authorized: bool
    execution_ready: bool
    eligible: bool
    reason_codes: tuple[str, ...]
    shaping: Mapping[str, float]
    identity: Mapping[str, str]
    metadata: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compose_capital_demand(inp: CapitalDemandInput) -> CapitalDemand:
    """Compose demand without granting execution authority.

    The ordering is intentional:
      1. establish a valid base demand;
      2. apply goal/aggression/AI posture;
      3. cap against every hard capital/risk/governance/execution constraint;
      4. select the configured capital source posture.

    A V1-only deployment therefore remains valid even when treasury capital is
    zero: the demand can be satisfied from internal prime/provider capacity.
    """

    requested = _nonnegative(inp.requested_amount)
    mode = str(inp.capital_mode or "v1_external_prime").strip().lower()
    mode = mode if mode in CAPITAL_MODES else "v1_external_prime"
    aggression = str(inp.aggressiveness or "balanced").strip().lower()
    aggression_mult = AGGRESSION_MULTIPLIERS.get(aggression, 1.0)
    aggression_cap = _cap(inp.aggressiveness_cap, 1.0)
    goal_mult = max(0.0, _float(inp.wealth_goal_multiplier, 1.0))
    ai_mult = max(0.0, _float(inp.ai_multiplier, 1.0))

    shaped = requested * goal_mult * aggression_mult * ai_mult
    shaped = _cap(shaped, requested * max(aggression_cap, 0.0))

    reasons: list[str] = []
    hard_eligible = True
    if not inp.governance_approved:
        reasons.append("governance_not_approved")
        hard_eligible = False
    if not inp.risk_approved:
        reasons.append("risk_not_approved")
        hard_eligible = False
    if inp.execution_plan_required and not inp.execution_plan_ready:
        reasons.append("execution_plan_not_ready")
        hard_eligible = False
    if inp.max_latency_ms > 0 and inp.latency_ms > inp.max_latency_ms:
        reasons.append("latency_stale")
        hard_eligible = False
    if inp.max_freshness_ms > 0 and inp.freshness_ms > inp.max_freshness_ms:
        reasons.append("market_data_stale")
        hard_eligible = False

    exposure_room = max(0.0, _float(inp.exposure_limit) - _nonnegative(inp.current_exposure))
    risk_room = _nonnegative(inp.risk_limit)
    governance_room = _nonnegative(inp.governance_limit)
    treasury_room = min(_nonnegative(inp.treasury_available), _nonnegative(inp.treasury_allocatable))
    prime_room = min(
        _nonnegative(inp.prime_available),
        _nonnegative(inp.prime_capacity),
        _nonnegative(inp.provider_capacity),
    )

    # Conversion is an authority gate, never an implicit convenience.
    if not inp.conversion_authorized and inp.conversion_rate != 1.0:
        reasons.append("conversion_not_authorized")
        conversion_room = 0.0
    else:
        conversion_room = float("inf") if _float(inp.conversion_rate, 1.0) > 0 else 0.0

    common_cap = min(exposure_room, risk_room, governance_room, conversion_room)
    if common_cap == float("inf"):
        common_cap = max(treasury_room + prime_room, shaped)

    # Fees are economic constraints, not permissions. A negative/invalid fee
    # is normalized to zero so it cannot manufacture capacity.
    provider_fee_bps = _nonnegative(inp.provider_fee_bps)
    prime_fee_bps = _nonnegative(inp.prime_fee_bps)
    fee_factor = max(0.0, 1.0 - ((provider_fee_bps + prime_fee_bps) / 10_000.0))
    economic_cap = max(0.0, (treasury_room + prime_room) * fee_factor)
    fundable = min(shaped, common_cap, economic_cap)

    treasury_amount = 0.0
    prime_amount = 0.0
    source = "none"

    if hard_eligible and fundable > 0:
        if mode == "v1_external_prime":
            prime_amount = min(fundable, prime_room)
            source = "internal_prime" if prime_amount > 0 else "none"
        elif mode == "own_capital":
            treasury_amount = min(fundable, treasury_room)
            source = "treasury" if treasury_amount > 0 else "none"
        else:  # hybrid: use treasury first, then prime for the residual.
            treasury_amount = min(fundable, treasury_room)
            prime_amount = min(fundable - treasury_amount, prime_room)
            if treasury_amount > 0 and prime_amount > 0:
                source = "treasury+internal_prime"
            elif treasury_amount > 0:
                source = "treasury"
            elif prime_amount > 0:
                source = "internal_prime"

    if fundable <= 0:
        reasons.append("no_fundable_capacity")
    if mode == "v1_external_prime" and prime_room <= 0:
        reasons.append("v1_prime_capacity_unavailable")
    if mode == "own_capital" and treasury_room <= 0:
        reasons.append("treasury_capacity_unavailable")
    if mode == "hybrid" and treasury_room + prime_room <= 0:
        reasons.append("hybrid_capacity_unavailable")
    if inp.prime_collateral_available > 0 and prime_amount > _nonnegative(inp.prime_collateral_available):
        reasons.append("prime_collateral_limit")
        prime_amount = _nonnegative(inp.prime_collateral_available)
        fundable = treasury_amount + prime_amount
    if fundable < shaped and hard_eligible:
        reasons.append("demand_capped")

    # Integer treasury units are included for downstream exact accounting.
    treasury_units = _to_base_units(treasury_amount, int(inp.treasury_decimals))
    metadata = dict(inp.metadata or {})
    metadata.update(
        {
            "treasurySymbol": str(inp.treasury_symbol or ""),
            "treasuryDecimals": max(0, int(inp.treasury_decimals)),
            "treasuryUnits": treasury_units,
            "conversionRate": _float(inp.conversion_rate, 1.0),
            "providerCapacity": _nonnegative(inp.provider_capacity),
            "providerFeeBps": provider_fee_bps,
            "currentExposure": _nonnegative(inp.current_exposure),
            "riskLimit": risk_room,
            "governanceLimit": governance_room,
            "latencyMs": _nonnegative(inp.latency_ms),
            "freshnessMs": _nonnegative(inp.freshness_ms),
            "aiRecommendationId": str(inp.ai_recommendation_id or ""),
            "aiRecommendationReason": str(inp.ai_recommendation_reason or ""),
        }
    )

    eligible = bool(hard_eligible and fundable > 0 and source != "none")
    return CapitalDemand(
        requested_amount=requested,
        shaped_amount=round(shaped, 12),
        fundable_amount=round(fundable, 12),
        capital_source=source,
        capital_mode=mode,
        strategy_version=str(inp.strategy_version or "V1"),
        strategy_family=str(inp.strategy_family or ""),
        treasury_amount=round(treasury_amount, 12),
        prime_amount=round(prime_amount, 12),
        provider_fee_bps=round(provider_fee_bps, 6),
        prime_fee_bps=round(prime_fee_bps, 6),
        conversion_authorized=bool(inp.conversion_authorized),
        execution_ready=bool(hard_eligible),
        eligible=eligible,
        reason_codes=tuple(dict.fromkeys(reasons)),
        shaping={
            "wealth_goal_multiplier": round(goal_mult, 8),
            "aggressiveness_multiplier": round(aggression_mult, 8),
            "aggressiveness_cap": round(aggression_cap, 8),
            "ai_multiplier": round(ai_mult, 8),
        },
        identity={
            "strategy_version": str(inp.strategy_version or "V1"),
            "strategy_family": str(inp.strategy_family or ""),
            "capital_mode": mode,
            "ai_recommendation_id": str(inp.ai_recommendation_id or ""),
        },
        metadata=metadata,
    )
