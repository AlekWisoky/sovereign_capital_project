from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from enum import Enum
from typing import Any, Mapping


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
        if isinstance(self.amount, bool) or int(self.amount) < 0:
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
        required = {
            "correlation_id": self.correlation_id,
            "strategy_family": self.strategy_family,
            "capital_source": self.capital_source,
            "execution_asset": self.execution_asset,
            "treasury_denomination": self.treasury_denomination,
            "provenance": self.provenance,
            "source_identity": self.source_identity,
        }
        if any(not str(value).strip() for value in required.values()):
            raise CapitalDemandError("CapitalDemand identity and provenance are required")
        if not 0 <= self.execution_decimals <= 255 or not 0 <= self.treasury_decimals <= 255:
            raise CapitalDemandError("CapitalDemand decimals are invalid")
        if self.strategy_budget_consumption.denomination != self.treasury_denomination:
            raise CapitalDemandError("strategy budget must use treasury denomination")
        for value in (self.internal_capital_commitment, self.gas_reserve, self.fee_reserve, self.provider_capacity_requirement, self.worst_case_exposure):
            if value.denomination != self.treasury_denomination:
                raise CapitalDemandError("all treasury exposure fields must share treasury denomination")
        if self.status == DemandStatus.VALID and self.conversion is not None and not self.conversion.fresh():
            raise CapitalDemandError("stale conversion evidence")

    @property
    def is_flash_loan(self) -> bool:
        return self.capital_source == "flashloan" or self.strategy_family in {"flash_arb", "flashloan_atomic"}

    def validate(self, *, now: datetime | None = None) -> DemandStatus:
        if self.status != DemandStatus.VALID:
            return self.status
        if self.is_flash_loan and self.execution_notional.amount > 0 and self.internal_capital_commitment.amount == 0:
            # Zero principal commitment is valid, but zero total exposure is not.
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
    if value.denomination != demand.treasury_denomination:
        raise CapitalDemandError("projection denomination mismatch")
    return value


def selector_scalar(demand: CapitalDemand, *, now: datetime | None = None) -> int:
    """Compatibility scalar: strategy-budget consumption in treasury units only."""
    return project_strategy_budget(demand, now=now).amount


def require_same_treasury_denomination(budget: Money, demand: CapitalDemand) -> None:
    if budget.denomination != demand.treasury_denomination or budget.decimals != demand.treasury_decimals:
        raise CapitalDemandError("treasury budget and demand are not comparable")


def ceil_ratio(amount: int, numerator: int, denominator: int) -> int:
    if min(amount, numerator, denominator) < 0 or denominator == 0:
        raise CapitalDemandError("invalid rounding inputs")
    return int((Decimal(amount) * Decimal(numerator) / Decimal(denominator)).to_integral_value(rounding=ROUND_CEILING))
