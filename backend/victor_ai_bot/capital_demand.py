from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from typing import Iterable


class DemandStatus(str, Enum):
    VALID = "valid"
    UNKNOWN = "unknown"
    INVALID = "invalid"
    STALE = "stale"
    CONFLICTING = "conflicting"


class CapitalDemandError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    """Integer quantity with explicit asset, decimals, and denomination.

    `amount` is base units of `asset`; it is never implicitly USD or wei.
    `denomination` identifies the accounting unit used for comparison.
    """

    amount: int
    asset: str
    decimals: int
    denomination: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount < 0:
            raise CapitalDemandError("money amount must be a non-negative integer")
        if not str(self.asset).strip() or not str(self.denomination).strip():
            raise CapitalDemandError("money asset and denomination are required")
        if isinstance(self.decimals, bool) or not isinstance(self.decimals, int) or not 0 <= self.decimals <= 255:
            raise CapitalDemandError("money decimals are invalid")

    def compatible_with(self, other: "Money") -> bool:
        return (self.asset, self.decimals, self.denomination) == (other.asset, other.decimals, other.denomination)


@dataclass(frozen=True)
class Capacity:
    """Provider constraint, intentionally not treasury capital."""

    amount: int
    unit: str
    provider: str
    observed_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount < 0:
            raise CapitalDemandError("capacity amount is invalid")
        if not str(self.unit).strip() or not str(self.provider).strip():
            raise CapitalDemandError("capacity unit and provider are required")
        if not isinstance(self.observed_at, datetime) or not isinstance(self.expires_at, datetime):
            raise CapitalDemandError("capacity timestamps are required")

    def valid(self, *, now: datetime) -> bool:
        return self.observed_at <= now <= self.expires_at

    def covers(self, execution_notional: Money, *, now: datetime) -> bool:
        return self.valid(now=now) and self.unit == execution_notional.denomination and self.amount >= execution_notional.amount


@dataclass(frozen=True)
class ConversionEvidence:
    source: str
    observed_at: datetime
    max_age_seconds: int
    from_denomination: str
    to_denomination: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if not str(self.source).strip() or not str(self.from_denomination).strip() or not str(self.to_denomination).strip():
            raise CapitalDemandError("conversion source and denominations are required")
        if isinstance(self.numerator, bool) or isinstance(self.denominator, bool) or self.numerator < 0 or self.denominator <= 0 or self.max_age_seconds < 0:
            raise CapitalDemandError("conversion ratio is invalid")
        if not isinstance(self.observed_at, datetime):
            raise CapitalDemandError("conversion timestamp is required")

    def fresh(self, *, now: datetime) -> bool:
        return (now - self.observed_at).total_seconds() <= self.max_age_seconds

    def convert(self, amount: Money, *, target_asset: str, target_decimals: int, now: datetime, rounding: str = "ceil") -> Money:
        if amount.denomination != self.from_denomination or not self.fresh(now=now):
            raise CapitalDemandError("conversion direction or freshness is invalid")
        if rounding not in {"ceil", "floor"}:
            raise CapitalDemandError("rounding direction is required")
        mode = ROUND_CEILING if rounding == "ceil" else ROUND_FLOOR
        converted = (Decimal(amount.amount) * Decimal(self.numerator) / Decimal(self.denominator)).to_integral_value(rounding=mode)
        return Money(int(converted), target_asset, target_decimals, self.to_denomination)


@dataclass(frozen=True)
class Provenance:
    source_component: str
    schema_version: str
    source_identity: str
    source_event: str
    generated_at: datetime
    correlation_id: str
    input_identity: str

    def __post_init__(self) -> None:
        if any(not str(value).strip() for value in (self.source_component, self.schema_version, self.source_identity, self.source_event, self.correlation_id, self.input_identity)):
            raise CapitalDemandError("structured provenance is incomplete")
        if not isinstance(self.generated_at, datetime):
            raise CapitalDemandError("provenance timestamp is required")


@dataclass(frozen=True)
class DemandSource:
    source_identity: str
    strategy_budget_consumption: Money


@dataclass(frozen=True)
class CapitalDemand:
    correlation_id: str
    strategy_family: str
    capital_source: str
    execution_notional: Money
    execution_asset: str
    execution_decimals: int
    treasury_denomination: str
    treasury_decimals: int
    internal_capital_commitment: Money
    gas_reserve: Money
    fee_reserve: Money
    provider_capacity_requirement: Capacity
    worst_case_exposure: Money
    strategy_budget_consumption: Money
    provenance: Provenance
    demand_generated_at: datetime
    demand_expires_at: datetime
    principal_solvency_required: bool = False
    gas_solvency_required: bool = True
    max_worst_case_exposure: Money | None = None
    corroborating_sources: tuple[DemandSource, ...] = ()
    status: DemandStatus = DemandStatus.VALID

    def __post_init__(self) -> None:
        try:
            status = self.status if isinstance(self.status, DemandStatus) else DemandStatus(str(self.status))
        except ValueError as exc:
            raise CapitalDemandError("unknown demand status") from exc
        object.__setattr__(self, "status", status)
        if any(not str(value).strip() for value in (self.correlation_id, self.strategy_family, self.capital_source, self.execution_asset, self.treasury_denomination)):
            raise CapitalDemandError("demand identity is incomplete")
        if self.provenance.correlation_id != self.correlation_id:
            raise CapitalDemandError("provenance correlation mismatch")
        if self.execution_notional.asset != self.execution_asset or self.execution_notional.decimals != self.execution_decimals:
            raise CapitalDemandError("execution identity does not match execution notional")
        if isinstance(self.treasury_decimals, bool) or not isinstance(self.treasury_decimals, int) or not 0 <= self.treasury_decimals <= 255:
            raise CapitalDemandError("treasury decimals are invalid")
        treasury_values = (self.internal_capital_commitment, self.gas_reserve, self.fee_reserve, self.worst_case_exposure, self.strategy_budget_consumption)
        if any(value.denomination != self.treasury_denomination or value.decimals != self.treasury_decimals for value in treasury_values):
            raise CapitalDemandError("treasury quantities must share declared treasury denomination and decimals")
        if self.max_worst_case_exposure is not None and not self.max_worst_case_exposure.compatible_with(self.worst_case_exposure):
            raise CapitalDemandError("worst-case exposure policy is incompatible")
        if self.demand_expires_at < self.demand_generated_at:
            raise CapitalDemandError("demand expiry precedes generation")

    @property
    def is_flash_loan(self) -> bool:
        return self.capital_source == "flashloan" or self.strategy_family in {"flash_arb", "flashloan_atomic"}

    def validate(self, *, now: datetime) -> DemandStatus:
        if self.status != DemandStatus.VALID:
            return self.status
        if not isinstance(now, datetime) or now < self.demand_generated_at or now > self.demand_expires_at:
            return DemandStatus.STALE
        if self.is_flash_loan and self.execution_notional.amount > 0 and self.internal_capital_commitment.amount == 0:
            if self.gas_solvency_required and self.gas_reserve.amount == 0:
                return DemandStatus.INVALID
            if self.worst_case_exposure.amount == 0 or self.strategy_budget_consumption.amount == 0:
                return DemandStatus.INVALID
        if not self.provider_capacity_requirement.covers(self.execution_notional, now=now):
            return DemandStatus.STALE if not self.provider_capacity_requirement.valid(now=now) else DemandStatus.INVALID
        if self.max_worst_case_exposure is not None and self.worst_case_exposure.amount > self.max_worst_case_exposure.amount:
            return DemandStatus.INVALID
        values = [self.strategy_budget_consumption] + [source.strategy_budget_consumption for source in self.corroborating_sources]
        if any(value.denomination != self.treasury_denomination or value.decimals != self.treasury_decimals for value in values):
            return DemandStatus.CONFLICTING
        if any(value.amount != self.strategy_budget_consumption.amount for value in values[1:]):
            return DemandStatus.CONFLICTING
        return DemandStatus.VALID


def project_strategy_budget(demand: CapitalDemand, *, now: datetime) -> Money:
    status = demand.validate(now=now)
    if status != DemandStatus.VALID or demand.strategy_budget_consumption.amount <= 0:
        raise CapitalDemandError(f"cannot project demand with status={status.value}")
    return demand.strategy_budget_consumption


def selector_scalar(demand: CapitalDemand, *, now: datetime) -> int:
    """Only strategy-budget consumption, expressed in declared treasury base units."""
    return project_strategy_budget(demand, now=now).amount


def require_same_treasury_denomination(budget: Money, demand: CapitalDemand) -> None:
    if budget.denomination != demand.treasury_denomination or budget.decimals != demand.treasury_decimals:
        raise CapitalDemandError("treasury budget and demand are not comparable")


def apply_goal_cap(*, demand: CapitalDemand, cap: int, accepted: bool, now: datetime) -> CapitalDemand:
    if not accepted or cap < 0 or demand.validate(now=now) != DemandStatus.VALID:
        raise CapitalDemandError("goal cannot authorize or rescue invalid demand")
    reduced = min(demand.strategy_budget_consumption.amount, cap)
    return _replace_budget(demand, reduced)


def apply_aggressiveness_cap(*, demand: CapitalDemand, multiplier: int, safety_approved: bool, now: datetime) -> CapitalDemand:
    if not safety_approved or multiplier < 0 or demand.validate(now=now) != DemandStatus.VALID:
        raise CapitalDemandError("aggressiveness cannot bypass safety")
    return _replace_budget(demand, demand.strategy_budget_consumption.amount * multiplier)


def live_eligible_family(*, family: str, mode: str = "phase_a", selected: Iterable[str] = (), ready: bool = False, governed: bool = False) -> bool:
    selected_set = {str(item) for item in selected}
    if mode == "ai_managed":
        return family in selected_set and ready and governed and family == "flash_arb"
    if mode == "single":
        return family in selected_set and ready and governed and family == "flash_arb"
    if mode == "multi":
        return family in selected_set and ready and governed and family == "flash_arb"
    return family == "flash_arb" and ready and governed


def _replace_budget(demand: CapitalDemand, amount: int) -> CapitalDemand:
    return CapitalDemand(**{**demand.__dict__, "strategy_budget_consumption": Money(amount, demand.treasury_denomination, demand.treasury_decimals, demand.treasury_denomination)})


def validate_settlement_authority(*, authoritative_after: int, supplied_after: int) -> None:
    if authoritative_after != supplied_after:
        raise CapitalDemandError("settlement realized-after conflicts with authoritative PnL")


def ceil_ratio(amount: int, numerator: int, denominator: int) -> int:
    if not all(isinstance(value, int) and value >= 0 for value in (amount, numerator, denominator)) or denominator == 0:
        raise CapitalDemandError("invalid rounding inputs")
    return int((Decimal(amount) * Decimal(numerator) / Decimal(denominator)).to_integral_value(rounding=ROUND_CEILING))
