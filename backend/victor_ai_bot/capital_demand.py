from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from enum import Enum


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
    amount: int
    asset: str
    decimals: int
    denomination: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount < 0:
            raise CapitalDemandError("money amount must be a non-negative integer")
        if not str(self.asset).strip() or not str(self.denomination).strip():
            raise CapitalDemandError("money asset and denomination are required")
        if not isinstance(self.decimals, int) or isinstance(self.decimals, bool) or not 0 <= self.decimals <= 255:
            raise CapitalDemandError("money decimals are invalid")


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
        if self.numerator <= 0 or self.denominator <= 0 or self.max_age_seconds < 0:
            raise CapitalDemandError("conversion evidence is invalid")

    def fresh(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        observed = self.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return (current - observed).total_seconds() <= self.max_age_seconds


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
    provider_capacity_requirement: Money
    worst_case_exposure: Money
    strategy_budget_consumption: Money
    conversion: ConversionEvidence | None
    provenance: str
    source_identity: str
    status: DemandStatus = DemandStatus.VALID

    def __post_init__(self) -> None:
        try:
            status = self.status if isinstance(self.status, DemandStatus) else DemandStatus(str(self.status))
        except ValueError as exc:
            raise CapitalDemandError("unknown demand status") from exc
        object.__setattr__(self, "status", status)
        required = (self.correlation_id, self.strategy_family, self.capital_source, self.execution_asset, self.treasury_denomination, self.provenance, self.source_identity)
        if any(not str(value).strip() for value in required):
            raise CapitalDemandError("CapitalDemand identity and provenance are required")
        if not isinstance(self.execution_decimals, int) or not 0 <= self.execution_decimals <= 255 or not isinstance(self.treasury_decimals, int) or not 0 <= self.treasury_decimals <= 255:
            raise CapitalDemandError("CapitalDemand decimals are invalid")
        if self.strategy_budget_consumption.denomination != self.treasury_denomination or self.strategy_budget_consumption.decimals != self.treasury_decimals:
            raise CapitalDemandError("strategy budget must use treasury denomination and decimals")
        for value in (self.internal_capital_commitment, self.gas_reserve, self.fee_reserve, self.provider_capacity_requirement, self.worst_case_exposure):
            if value.denomination != self.treasury_denomination or value.decimals != self.treasury_decimals:
                raise CapitalDemandError("treasury exposure fields must share treasury denomination and decimals")
        if self.execution_notional.denomination != self.treasury_denomination:
            if self.conversion is None:
                raise CapitalDemandError("conversion evidence required for cross-denomination demand")
            if self.conversion.from_denomination != self.execution_notional.denomination or self.conversion.to_denomination != self.treasury_denomination:
                raise CapitalDemandError("conversion evidence does not match demand denominations")
        if status == DemandStatus.VALID and self.conversion is not None and not self.conversion.fresh():
            raise CapitalDemandError("stale conversion evidence")

    @property
    def is_flash_loan(self) -> bool:
        return self.capital_source == "flashloan" or self.strategy_family in {"flash_arb", "flashloan_atomic"}

    def validate(self, *, now: datetime | None = None) -> DemandStatus:
        if self.status != DemandStatus.VALID:
            return self.status
        if self.is_flash_loan and self.execution_notional.amount > 0 and self.internal_capital_commitment.amount == 0:
            if self.worst_case_exposure.amount == 0 or self.strategy_budget_consumption.amount == 0:
                return DemandStatus.INVALID
        if self.conversion is not None and not self.conversion.fresh(now=now):
            return DemandStatus.STALE
        return DemandStatus.VALID


def project_strategy_budget(demand: CapitalDemand, *, now: datetime | None = None) -> Money:
    status = demand.validate(now=now)
    if status != DemandStatus.VALID:
        raise CapitalDemandError(f"cannot project demand with status={status.value}")
    value = demand.strategy_budget_consumption
    if value.denomination != demand.treasury_denomination or value.decimals != demand.treasury_decimals:
        raise CapitalDemandError("projection denomination mismatch")
    if value.amount <= 0:
        raise CapitalDemandError("strategy budget consumption is unknown or zero")
    return value


def selector_scalar(demand: CapitalDemand, *, now: datetime | None = None) -> int:
    """Compatibility scalar: strategy-budget consumption in treasury units only."""
    return project_strategy_budget(demand, now=now).amount


def require_same_treasury_denomination(budget: Money, demand: CapitalDemand) -> None:
    if budget.denomination != demand.treasury_denomination or budget.decimals != demand.treasury_decimals:
        raise CapitalDemandError("treasury budget and demand are not comparable")


def ceil_ratio(amount: int, numerator: int, denominator: int) -> int:
    if not all(isinstance(value, int) and value >= 0 for value in (amount, numerator, denominator)) or denominator == 0:
        raise CapitalDemandError("invalid rounding inputs")
    return int((Decimal(amount) * Decimal(numerator) / Decimal(denominator)).to_integral_value(rounding=ROUND_CEILING))
