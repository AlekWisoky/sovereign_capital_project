"""Immutable, side-effect-free authority evidence contracts.

This module intentionally does not select any unresolved treasury, conversion,
provider, exposure, reservation, identity, or freshness policy. It contains
read-side evidence shapes only. Runtime consumers are not wired to these types.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
import json
from typing import Any, Mapping


class AuthorityStatus(str, Enum):
    PROVEN = "PROVEN"
    PARTIALLY_PROVEN = "PARTIALLY_PROVEN"
    HEURISTIC = "HEURISTIC"
    CONFLICTING = "CONFLICTING"
    UNPROVEN = "UNPROVEN"
    UNRESOLVED = "UNRESOLVED"


class SnapshotState(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    MISSING = "MISSING"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    PROVENANCE_CONFLICT = "PROVENANCE_CONFLICT"
    POLICY_UNRESOLVED = "POLICY_UNRESOLVED"


class AuthorityContractError(ValueError):
    pass


def _freeze(value: Any) -> Any:
    """Recursively freeze supported evidence containers.

    Unsupported objects are rejected instead of being presented as immutable
    evidence. This intentionally makes the contract conservative for arbitrary
    user-defined mutable objects.
    """
    if value is None or isinstance(value, (str, bytes, int, float, bool, datetime, timedelta, Enum)):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    if dataclass_is_instance(value):
        return value
    raise AuthorityContractError(f"unsupported mutable evidence value: {type(value).__name__}")


def dataclass_is_instance(value: Any) -> bool:
    try:
        from dataclasses import is_dataclass

        return bool(is_dataclass(value) and not isinstance(value, type))
    except TypeError:
        return False


class _FrozenStateMixin:
    def _freeze_state(self) -> None:
        object.__setattr__(self, "state", _freeze(self.state))


@dataclass(frozen=True)
class Revision:
    """Source-specific revision; no universal ordering is assumed."""

    source: str
    value: str
    schema: str = ""

    def __post_init__(self) -> None:
        if not self.source or not self.value:
            raise AuthorityContractError("revision source and value are required")

    def compatible_with(self, other: "Revision") -> bool:
        return self.source == other.source and self.value == other.value and self.schema == other.schema


@dataclass(frozen=True)
class Provenance:
    source: str
    source_id: str = ""
    evidence_type: str = ""
    observed_at: datetime | None = None
    chain: str = ""
    block_number: int | None = None
    block_hash: str = ""
    revision: Revision | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise AuthorityContractError("provenance source is required")
        if self.block_number is not None and self.block_number < 0:
            raise AuthorityContractError("block number cannot be negative")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise AuthorityContractError("observed_at must be timezone-aware")


@dataclass(frozen=True)
class FreshnessSnapshot:
    source: str
    observed_at: datetime | None
    observed_block: int | None = None
    observed_block_hash: str = ""
    horizon: timedelta | None = None
    policy_revision: Revision | None = None
    state: SnapshotState = SnapshotState.POLICY_UNRESOLVED
    revalidation_required: bool = True

    def __post_init__(self) -> None:
        if not self.source:
            raise AuthorityContractError("freshness source is required")
        if self.observed_at is not None and self.observed_at.tzinfo is None:
            raise AuthorityContractError("freshness observed_at must be timezone-aware")
        if self.observed_block is not None and self.observed_block < 0:
            raise AuthorityContractError("observed block cannot be negative")
        if self.horizon is not None and self.horizon.total_seconds() < 0:
            raise AuthorityContractError("freshness horizon cannot be negative")

    def evaluate(self, *, now: datetime, revision: Revision | None = None) -> SnapshotState:
        if now.tzinfo is None:
            raise AuthorityContractError("now must be timezone-aware")
        if self.policy_revision is not None and revision is not None and not self.policy_revision.compatible_with(revision):
            return SnapshotState.REVISION_CONFLICT
        if self.observed_at is None or self.horizon is None:
            return SnapshotState.POLICY_UNRESOLVED
        if now < self.observed_at or now - self.observed_at > self.horizon:
            return SnapshotState.STALE
        return SnapshotState.VALID


@dataclass(frozen=True)
class Unit:
    asset: str
    denomination: str
    decimals: int | None
    decimal_revision: Revision | None = None

    def __post_init__(self) -> None:
        if not self.asset or not self.denomination:
            raise AuthorityContractError("asset and denomination are required")
        if self.decimals is not None and not 0 <= self.decimals <= 255:
            raise AuthorityContractError("decimals out of range")

    def compatible_with(self, other: "Unit") -> bool:
        return self.asset == other.asset and self.denomination == other.denomination and self.decimals == other.decimals


@dataclass(frozen=True)
class Evidence:
    status: AuthorityStatus
    provenance: Provenance
    freshness: FreshnessSnapshot
    revision: Revision | None = None
    conflicts: tuple[str, ...] = ()
    state: SnapshotState = SnapshotState.VALID

    def validate(self, *, now: datetime) -> SnapshotState:
        if self.status in {AuthorityStatus.CONFLICTING, AuthorityStatus.UNRESOLVED}:
            return SnapshotState.PROVENANCE_CONFLICT if self.status is AuthorityStatus.CONFLICTING else SnapshotState.POLICY_UNRESOLVED
        if self.conflicts:
            return SnapshotState.PROVENANCE_CONFLICT
        freshness_state = self.freshness.evaluate(now=now, revision=self.revision)
        if freshness_state is not SnapshotState.VALID:
            return freshness_state
        if self.state is not SnapshotState.VALID:
            return self.state
        return SnapshotState.VALID


@dataclass(frozen=True)
class TreasurySnapshot:
    scope: str
    chain: str
    account: str
    unit: Unit
    settled_amount: int | None
    available_amount: int | None
    reserved_amount: int | None
    encumbered_amount: int | None
    evidence: Evidence
    treasury_revision: Revision | None = None
    reservation_authority: str = "UNRESOLVED / NON-AUTHORITATIVE"

    def validate(self, *, now: datetime) -> SnapshotState:
        if not self.scope or not self.chain or not self.account:
            return SnapshotState.MISSING
        if self.unit.decimals is None or any(v is not None and v < 0 for v in (self.settled_amount, self.available_amount, self.reserved_amount, self.encumbered_amount)):
            return SnapshotState.MISSING if self.unit.decimals is None else SnapshotState.INVALID
        return self.evidence.validate(now=now)


@dataclass(frozen=True)
class ConversionSnapshot:
    source: Unit
    target: Unit
    numerator: int | None
    denominator: int | None
    evidence: Evidence
    block_number: int | None = None
    block_hash: str = ""
    rounding_policy: str = "UNRESOLVED"

    def validate(self, *, now: datetime) -> SnapshotState:
        if self.source.decimals is None or self.target.decimals is None:
            return SnapshotState.MISSING
        if self.numerator is None or self.denominator is None or self.denominator <= 0 or self.numerator < 0:
            return SnapshotState.MISSING
        return self.evidence.validate(now=now)


@dataclass(frozen=True)
class ProviderCapacitySnapshot:
    provider: str
    unit: Unit
    capacity_amount: int | None
    capacity_units: str
    evidence: Evidence
    block_number: int | None = None
    block_hash: str = ""

    def validate(self, *, now: datetime) -> SnapshotState:
        if not self.provider or not self.capacity_units or self.capacity_amount is None:
            return SnapshotState.MISSING
        if self.capacity_amount < 0 or self.unit.decimals is None:
            return SnapshotState.INVALID if self.capacity_amount < 0 else SnapshotState.MISSING
        return self.evidence.validate(now=now)


@dataclass(frozen=True)
class ProviderFeeSnapshot:
    provider: str
    unit: Unit
    fee_amount: int | None
    fee_rate_numerator: int | None
    fee_rate_denominator: int | None
    evidence: Evidence

    def validate(self, *, now: datetime) -> SnapshotState:
        if not self.provider or self.unit.decimals is None:
            return SnapshotState.MISSING
        if self.fee_amount is None and (self.fee_rate_numerator is None or not self.fee_rate_denominator):
            return SnapshotState.MISSING
        return self.evidence.validate(now=now)


@dataclass(frozen=True)
class ExposureSnapshot:
    components: tuple[tuple[str, Unit, int], ...]
    evidence: Evidence
    policy_revision: Revision | None = None

    def validate(self, *, now: datetime) -> SnapshotState:
        if any(amount < 0 or unit.decimals is None for _, unit, amount in self.components):
            return SnapshotState.INVALID
        return self.evidence.validate(now=now)


@dataclass(frozen=True)
class PolicySnapshot(_FrozenStateMixin):
    policy_revision: Revision | None
    state: Mapping[str, Any]
    evidence: Evidence

    def __post_init__(self) -> None:
        self._freeze_state()

    def validate(self, *, now: datetime) -> SnapshotState:
        if not self.state:
            return SnapshotState.MISSING
        return self.evidence.validate(now=now)


RiskSnapshot = PolicySnapshot
GovernanceSnapshot = PolicySnapshot
GoalSnapshot = PolicySnapshot


@dataclass(frozen=True)
class ExecutionPlanSnapshot:
    route_id: str
    amount: int
    amount_unit: Unit
    quote_revision: Revision | None
    quote_block: int | None
    min_outs: tuple[int, ...]
    provider: str
    provider_fee_revision: Revision | None
    gas_assumptions: tuple[tuple[str, str], ...]
    deadline: int
    simulation_state: str
    treasury_revision: Revision | None
    risk_revision: Revision | None
    governance_revision: Revision | None
    policy_revision: Revision | None
    execution_plan_id: str
    provenance: Provenance

    def material_fields(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "amount": self.amount,
            "amount_unit": asdict(self.amount_unit),
            "quote_revision": asdict(self.quote_revision) if self.quote_revision else None,
            "quote_block": self.quote_block,
            "min_outs": self.min_outs,
            "provider": self.provider,
            "provider_fee_revision": asdict(self.provider_fee_revision) if self.provider_fee_revision else None,
            "gas_assumptions": self.gas_assumptions,
            "deadline": self.deadline,
            "simulation_state": self.simulation_state,
            "treasury_revision": asdict(self.treasury_revision) if self.treasury_revision else None,
            "risk_revision": asdict(self.risk_revision) if self.risk_revision else None,
            "governance_revision": asdict(self.governance_revision) if self.governance_revision else None,
            "policy_revision": asdict(self.policy_revision) if self.policy_revision else None,
        }

    @staticmethod
    def content_id(fields: Mapping[str, Any]) -> str:
        encoded = json.dumps(dict(fields), sort_keys=True, separators=(",", ":"), default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()

    def __post_init__(self) -> None:
        expected = self.content_id(self.material_fields())
        if self.execution_plan_id != expected:
            raise AuthorityContractError("execution_plan_id does not match material plan content")

    def validate(self) -> SnapshotState:
        if not self.route_id or self.amount <= 0 or self.amount_unit.decimals is None or not self.provider or not self.execution_plan_id:
            return SnapshotState.MISSING
        if any(value < 0 for value in self.min_outs):
            return SnapshotState.INVALID
        return SnapshotState.VALID


@dataclass(frozen=True)
class DecisionSnapshot:
    opportunity_id: str
    economic_intent_id: str
    trade_correlation_id: str
    execution_plan: ExecutionPlanSnapshot
    treasury: TreasurySnapshot | None
    conversion: ConversionSnapshot | None
    provider_capacity: ProviderCapacitySnapshot | None
    provider_fee: ProviderFeeSnapshot | None
    exposure: ExposureSnapshot | None
    risk: RiskSnapshot | None
    governance: GovernanceSnapshot | None
    goal: GoalSnapshot | None
    freshness: FreshnessSnapshot
    provenance: Provenance
    policy_revision: Revision | None
    status: AuthorityStatus = AuthorityStatus.UNRESOLVED

    def validate(self, *, now: datetime) -> SnapshotState:
        if not self.opportunity_id or not self.economic_intent_id or not self.trade_correlation_id:
            return SnapshotState.MISSING
        if self.status in {AuthorityStatus.CONFLICTING, AuthorityStatus.UNRESOLVED}:
            return SnapshotState.PROVENANCE_CONFLICT if self.status is AuthorityStatus.CONFLICTING else SnapshotState.POLICY_UNRESOLVED
        plan_state = self.execution_plan.validate()
        if plan_state is not SnapshotState.VALID:
            return plan_state
        freshness_state = self.freshness.evaluate(now=now, revision=self.policy_revision)
        if freshness_state is not SnapshotState.VALID:
            return freshness_state
        for snapshot in (self.treasury, self.conversion, self.provider_capacity, self.provider_fee, self.exposure, self.risk, self.governance, self.goal):
            if snapshot is None:
                continue
            state = snapshot.validate(now=now)
            if state is not SnapshotState.VALID:
                return state
        return SnapshotState.VALID


class ReadOnlyAuthorityAdapter:
    """Marker protocol-like base for future read-only adapters."""

    def read(self, *, now: datetime) -> Any:
        raise NotImplementedError
