from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ..capital_family_policy import build_family_capital_plan


@dataclass(frozen=True)
class CapitalTruthDerivedStateBundle:
    realized_profit_wei: int
    deployed_capital_wei: int
    reserved_capital_wei: int
    treasury_balance_wei: int
    auto_reinvest: bool
    reinvest_rate_pct: float
    retained_profit_wei: int
    withdrawable_balance_wei: int
    locked_capital_wei: int
    total_capital_wei: int
    prime_state_ready: bool
    prime_state_reason: str
    borrowed_usd: float
    prime_capacity_usd: float
    prime_utilization: float
    prime_family_exposure: Dict[str, float]
    prime_open_loan_count: int
    reserved_collateral_usd: float
    collateralization_ratio: float
    prime_locked_wei_estimate: int
    categories: Dict[str, str]
    family_allocations: Dict[str, float]
    family_capital_plan: List[Dict[str, Any]]


def _int_like(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_like(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _family_allocations(capital_engine: Dict[str, Any]) -> Dict[str, float]:
    targets = dict((capital_engine or {}).get("family_targets") or {})
    return {str(family): round(_float_like(value), 8) for family, value in targets.items()}


def _prime_family_exposure(internal_prime_state: Dict[str, Any]) -> Dict[str, float]:
    return {
        str(k): round(_float_like(v), 8)
        for k, v in dict(internal_prime_state.get("familyExposure") or {}).items()
    }


def _reserved_collateral_usd(internal_prime_state: Dict[str, Any]) -> float:
    explicit = _float_like(internal_prime_state.get("reservedCollateralUsd"))
    if explicit > 0.0:
        return explicit
    total = 0.0
    for loan in list(internal_prime_state.get("openLoans") or []) + list(
        internal_prime_state.get("disputedLoans") or []
    ):
        if not isinstance(loan, dict):
            continue
        total += _float_like(loan.get("collateral_reserved_usd") or loan.get("notional_usd"))
    return total


def build_capital_truth_derived_state(
    *,
    capital_engine: Dict[str, Any],
    efficiency: Dict[str, Any],
    reinvestment: Dict[str, Any],
    treasury_state: Dict[str, Any],
    internal_prime_state: Dict[str, Any],
    bankroll: Any,
    bankroll_state: Any,
) -> CapitalTruthDerivedStateBundle:
    realized_profit_wei = _int_like(getattr(bankroll_state, "realized_profit_wei", 0))
    deployed_capital_wei = _int_like(
        capital_engine.get("deployable_bankroll_wei")
        or efficiency.get("deployedCapitalWei")
        or getattr(bankroll_state, "last_amount_in_wei", 0)
    )
    reserved_capital_wei = _int_like(
        capital_engine.get("drawdown_buffer_wei") or treasury_state.get("drawdown_buffer_wei") or 0
    )
    treasury_balance_wei = _int_like(
        capital_engine.get("estimated_capital_wei") or deployed_capital_wei + reserved_capital_wei
    )
    auto_reinvest = bool(getattr(getattr(bankroll, "cfg", None), "auto_reinvest_enabled", False))
    reinvest_rate_pct = _float_like(
        reinvestment.get("reinvest_pct")
        or reinvestment.get("reinvestRatePct")
        or getattr(getattr(bankroll, "cfg", None), "reinvest_rate_pct", 0.0)
    )
    reinvest_rate_pct = max(0.0, min(100.0, reinvest_rate_pct if auto_reinvest else 0.0))
    retained_profit_wei = int(realized_profit_wei * (reinvest_rate_pct / 100.0))
    withdrawable_balance_wei = max(0, realized_profit_wei - retained_profit_wei)
    locked_capital_wei = max(0, reserved_capital_wei)
    total_capital_wei = max(0, treasury_balance_wei + retained_profit_wei)

    prime_state_ready = bool(internal_prime_state.get("stateReady", True))
    prime_state_reason = str(
        internal_prime_state.get("stateReasonCode")
        or ("internal_prime_state_unavailable" if not prime_state_ready else "")
    )
    borrowed_usd = _float_like(internal_prime_state.get("borrowedUsd"))
    prime_capacity_usd = _float_like(internal_prime_state.get("capacityUsd"))
    prime_utilization = _float_like(internal_prime_state.get("utilization"))
    prime_family_exposure = _prime_family_exposure(internal_prime_state)
    prime_open_loan_count = _int_like(
        internal_prime_state.get("loanCount")
        or len(list(internal_prime_state.get("openLoans") or []))
    )
    reserved_collateral_usd = _reserved_collateral_usd(internal_prime_state)
    collateralization_ratio = _float_like(internal_prime_state.get("collateralizationRatio"))
    prime_locked_wei_estimate = int(max(0.0, reserved_collateral_usd or borrowed_usd) * 1e18)
    if prime_locked_wei_estimate > 0:
        locked_capital_wei = max(locked_capital_wei, prime_locked_wei_estimate)

    categories = {
        "total_capital_wei": str(total_capital_wei),
        "deployable_capital_wei": str(max(0, deployed_capital_wei)),
        "reserved_capital_wei": str(max(0, reserved_capital_wei)),
        "realized_profit_wei": str(max(0, realized_profit_wei)),
        "retained_profit_wei": str(max(0, retained_profit_wei)),
        "withdrawable_balance_wei": str(max(0, withdrawable_balance_wei)),
        "treasury_balance_wei": str(max(0, treasury_balance_wei)),
        "capital_locked_wei": str(max(0, locked_capital_wei)),
    }
    family_allocations = _family_allocations(capital_engine)
    family_capital_plan = build_family_capital_plan(
        capital_engine=capital_engine,
        deployable_usd=(max(0, deployed_capital_wei) / 1e18),
    )
    return CapitalTruthDerivedStateBundle(
        realized_profit_wei=realized_profit_wei,
        deployed_capital_wei=deployed_capital_wei,
        reserved_capital_wei=reserved_capital_wei,
        treasury_balance_wei=treasury_balance_wei,
        auto_reinvest=auto_reinvest,
        reinvest_rate_pct=reinvest_rate_pct,
        retained_profit_wei=retained_profit_wei,
        withdrawable_balance_wei=withdrawable_balance_wei,
        locked_capital_wei=locked_capital_wei,
        total_capital_wei=total_capital_wei,
        prime_state_ready=prime_state_ready,
        prime_state_reason=prime_state_reason,
        borrowed_usd=borrowed_usd,
        prime_capacity_usd=prime_capacity_usd,
        prime_utilization=prime_utilization,
        prime_family_exposure=prime_family_exposure,
        prime_open_loan_count=prime_open_loan_count,
        reserved_collateral_usd=reserved_collateral_usd,
        collateralization_ratio=collateralization_ratio,
        prime_locked_wei_estimate=prime_locked_wei_estimate,
        categories=categories,
        family_allocations=family_allocations,
        family_capital_plan=family_capital_plan,
    )
