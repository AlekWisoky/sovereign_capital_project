"""TEST_ONLY_SYNTHETIC authority-snapshot contracts for Architecture C.

This file is intentionally isolated from runtime production code.  The types below
make missing authority mechanically visible without selecting any production policy,
source, denomination, provider, reservation lifecycle, or freshness horizon.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any

import pytest


TEST_MARKER = "TEST_ONLY_SYNTHETIC"


class SnapshotError(ValueError):
    pass


class SnapshotStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    MISSING_AUTHORITY = "MISSING_AUTHORITY"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    PROVENANCE_CONFLICT = "PROVENANCE_CONFLICT"


@dataclass(frozen=True)
class Provenance:
    marker: str
    source_identity: str
    source_revision: str
    observed_at: datetime
    observed_block: int | None = None
    observed_block_hash: str = ""

    def __post_init__(self) -> None:
        if self.marker != TEST_MARKER:
            raise SnapshotError("synthetic contract fixtures must be explicitly marked")
        if not self.source_identity or not self.source_revision:
            raise SnapshotError("source identity and revision are required")
        if self.observed_at.tzinfo is None:
            raise SnapshotError("observation time must be timezone-aware")


@dataclass(frozen=True)
class Freshness:
    observed_at: datetime
    observed_block: int | None
    observed_block_hash: str
    horizon: timedelta | None
    source_revision: str
    mandatory_revalidation: bool = True

    def status(self, *, now: datetime, revision: str) -> SnapshotStatus:
        if revision != self.source_revision:
            return SnapshotStatus.REVISION_CONFLICT
        if self.horizon is None:
            return SnapshotStatus.MISSING_AUTHORITY
        if now < self.observed_at or now - self.observed_at > self.horizon:
            return SnapshotStatus.STALE
        return SnapshotStatus.VALID


@dataclass(frozen=True)
class TreasurySnapshot:
    chain: str
    treasury_scope: str
    asset_identity: str
    asset_decimals: int | None
    decimal_authority_revision: str
    ledger_identity: str
    treasury_revision: str
    reservation_authority: str
    available_amount: int
    reserved_amount: int
    encumbered_amount: int
    provenance: Provenance
    freshness: Freshness
    status: SnapshotStatus = SnapshotStatus.VALID

    def validate(self, *, now: datetime) -> SnapshotStatus:
        if self.status != SnapshotStatus.VALID:
            return self.status
        required = (
            self.chain,
            self.treasury_scope,
            self.asset_identity,
            self.decimal_authority_revision,
            self.ledger_identity,
            self.treasury_revision,
            self.reservation_authority,
        )
        if any(not value for value in required) or self.asset_decimals is None:
            return SnapshotStatus.MISSING_AUTHORITY
        if min(self.available_amount, self.reserved_amount, self.encumbered_amount) < 0:
            return SnapshotStatus.INVALID
        return self.freshness.status(now=now, revision=self.treasury_revision)


@dataclass(frozen=True)
class ConversionSnapshot:
    source_asset: str
    source_decimals: int | None
    source_decimal_authority: str
    target_asset: str
    target_decimals: int | None
    target_decimal_authority: str
    numerator: int
    denominator: int
    source_identity: str
    source_revision: str
    block_number: int | None
    block_hash: str
    observed_at: datetime
    freshness: Freshness
    rounding_policy: str
    provenance: Provenance
    conflict_state: str = "none"
    direction: str = "forward"

    def validate(self, *, now: datetime, revision: str | None = None) -> SnapshotStatus:
        if self.conflict_state != "none":
            return SnapshotStatus.PROVENANCE_CONFLICT
        if (
            not self.source_asset
            or self.source_decimals is None
            or not self.source_decimal_authority
            or not self.target_asset
            or self.target_decimals is None
            or not self.target_decimal_authority
            or not self.source_identity
            or not self.source_revision
            or not self.rounding_policy
            or self.direction != "forward"
            or self.numerator < 0
            or self.denominator <= 0
        ):
            return SnapshotStatus.MISSING_AUTHORITY
        return self.freshness.status(now=now, revision=revision or self.source_revision)


@dataclass(frozen=True)
class ProviderSnapshot:
    provider_identity: str
    asset_identity: str
    asset_decimals: int | None
    capacity_amount: int
    capacity_units: str
    observed_block: int | None
    observed_block_hash: str
    provider_revision: str
    fee_schedule_revision: str
    fee_amount: int | None
    fee_rate_numerator: int | None
    fee_rate_denominator: int | None
    freshness: Freshness
    provenance: Provenance

    def validate(self, *, now: datetime) -> SnapshotStatus:
        if not self.provider_identity or not self.asset_identity or self.asset_decimals is None:
            return SnapshotStatus.MISSING_AUTHORITY
        if not self.capacity_units:
            return SnapshotStatus.MISSING_AUTHORITY
        if self.capacity_amount < 0:
            return SnapshotStatus.INVALID
        if not self.provider_revision or not self.fee_schedule_revision:
            return SnapshotStatus.MISSING_AUTHORITY
        if self.fee_amount is None and (
            self.fee_rate_numerator is None or self.fee_rate_denominator in (None, 0)
        ):
            return SnapshotStatus.MISSING_AUTHORITY
        return self.freshness.status(now=now, revision=self.provider_revision)


@dataclass(frozen=True)
class RiskGovernanceSnapshot:
    risk_policy_revision: str
    drawdown_state_revision: str
    governance_revision: str
    readiness_revision: str
    strategy_eligibility_revision: str
    pause_kill_revision: str
    policy_revision: str
    state: dict[str, Any]
    freshness: Freshness
    provenance: Provenance

    def validate(self, *, now: datetime, required_policy_revision: str) -> SnapshotStatus:
        revisions = (
            self.risk_policy_revision,
            self.drawdown_state_revision,
            self.governance_revision,
            self.readiness_revision,
            self.strategy_eligibility_revision,
            self.pause_kill_revision,
            self.policy_revision,
        )
        if not all(revisions) or not self.state:
            return SnapshotStatus.MISSING_AUTHORITY
        if len(set(revisions)) != 1 or self.policy_revision != required_policy_revision:
            return SnapshotStatus.REVISION_CONFLICT
        if self.state.get("contradictory"):
            return SnapshotStatus.PROVENANCE_CONFLICT
        return self.freshness.status(now=now, revision=self.policy_revision)


@dataclass(frozen=True)
class ExecutionPlanSnapshot:
    route_identity: str
    amount: int
    quote_revision: str
    quote_block: int | None
    min_out: int
    slippage_bps: int
    provider_identity: str
    fee_revision: str
    fee_amount: int
    gas_assumptions: tuple[tuple[str, str], ...]
    calldata: str
    deadline: int
    simulation_state: str
    treasury_revision: str
    risk_governance_revision: str
    goal_revision: str
    strategy_family: str
    execution_plan_id: str

    @staticmethod
    def contract_id(fields: dict[str, Any]) -> str:
        """TEST_ONLY_SYNTHETIC content identity, not a production algorithm."""
        encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def material_fields(self) -> dict[str, Any]:
        return {
            "route_identity": self.route_identity,
            "amount": self.amount,
            "quote_revision": self.quote_revision,
            "quote_block": self.quote_block,
            "min_out": self.min_out,
            "slippage_bps": self.slippage_bps,
            "provider_identity": self.provider_identity,
            "fee_revision": self.fee_revision,
            "fee_amount": self.fee_amount,
            "gas_assumptions": self.gas_assumptions,
            "calldata": self.calldata,
            "deadline": self.deadline,
            "simulation_state": self.simulation_state,
            "treasury_revision": self.treasury_revision,
            "risk_governance_revision": self.risk_governance_revision,
            "goal_revision": self.goal_revision,
            "strategy_family": self.strategy_family,
        }

    def validate(self) -> SnapshotStatus:
        if not all(
            (
                self.route_identity,
                self.quote_revision,
                self.provider_identity,
                self.fee_revision,
                self.calldata,
                self.simulation_state,
                self.treasury_revision,
                self.risk_governance_revision,
                self.goal_revision,
                self.strategy_family,
                self.execution_plan_id,
            )
        ):
            return SnapshotStatus.MISSING_AUTHORITY
        if self.amount <= 0 or self.min_out < 0 or self.slippage_bps < 0 or self.fee_amount < 0:
            return SnapshotStatus.INVALID
        return SnapshotStatus.VALID


@dataclass(frozen=True)
class DecisionSnapshot:
    opportunity_identity: str
    execution_plan: ExecutionPlanSnapshot
    treasury: TreasurySnapshot
    conversion: ConversionSnapshot
    provider: ProviderSnapshot
    risk_governance: RiskGovernanceSnapshot
    strategy_mode: str
    selected_strategy: str
    wealth_goal_posture: tuple[tuple[str, str], ...]
    freshness_envelope: Freshness
    provenance: Provenance
    policy_revision: str
    trade_correlation_id: str

    def validate(self, *, now: datetime) -> SnapshotStatus:
        if (
            not self.opportunity_identity
            or not self.policy_revision
            or not self.trade_correlation_id
        ):
            return SnapshotStatus.MISSING_AUTHORITY
        if self.selected_strategy != "flash_arb":
            return SnapshotStatus.INVALID
        if self.execution_plan.validate() != SnapshotStatus.VALID:
            return self.execution_plan.validate()
        if self.treasury.validate(now=now) != SnapshotStatus.VALID:
            return self.treasury.validate(now=now)
        if self.conversion.validate(now=now) != SnapshotStatus.VALID:
            return self.conversion.validate(now=now)
        if self.provider.validate(now=now) != SnapshotStatus.VALID:
            return self.provider.validate(now=now)
        if (
            self.risk_governance.validate(now=now, required_policy_revision=self.policy_revision)
            != SnapshotStatus.VALID
        ):
            return self.risk_governance.validate(
                now=now, required_policy_revision=self.policy_revision
            )
        if (
            self.freshness_envelope.status(now=now, revision=self.policy_revision)
            != SnapshotStatus.VALID
        ):
            return self.freshness_envelope.status(now=now, revision=self.policy_revision)
        return SnapshotStatus.VALID


NOW = datetime(2026, 8, 14, 7, 0, tzinfo=timezone.utc)


def _provenance(name: str, revision: str) -> Provenance:
    return Provenance(
        TEST_MARKER, name, revision, NOW, observed_block=100, observed_block_hash="block-100"
    )


def _fresh(revision: str) -> Freshness:
    return Freshness(NOW, 100, "block-100", timedelta(seconds=30), revision)


def _treasury() -> TreasurySnapshot:
    return TreasurySnapshot(
        "chain-x",
        "scope-x",
        "ASSET_UNSPECIFIED",
        0,
        "decimals-r1",
        "ledger-r1",
        "treasury-r1",
        "reservation-unresolved",
        100,
        10,
        5,
        _provenance("treasury-test", "treasury-r1"),
        _fresh("treasury-r1"),
    )


def _conversion() -> ConversionSnapshot:
    return ConversionSnapshot(
        "ASSET_A",
        8,
        "decimals-a-r1",
        "ASSET_B",
        6,
        "decimals-b-r1",
        3,
        2,
        "conversion-source-x",
        "conversion-r1",
        100,
        "block-100",
        NOW,
        _fresh("conversion-r1"),
        "ceil",
        _provenance("conversion-test", "conversion-r1"),
    )


def _provider() -> ProviderSnapshot:
    return ProviderSnapshot(
        "provider-unresolved",
        "ASSET_UNSPECIFIED",
        0,
        1000,
        "asset-native-units",
        100,
        "block-100",
        "provider-r1",
        "fee-r1",
        1,
        None,
        None,
        _fresh("provider-r1"),
        _provenance("provider-test", "provider-r1"),
    )


def _risk() -> RiskGovernanceSnapshot:
    return RiskGovernanceSnapshot(
        "policy-r1",
        "policy-r1",
        "policy-r1",
        "policy-r1",
        "policy-r1",
        "policy-r1",
        "policy-r1",
        {"ready": True, "gates": "mandatory"},
        _fresh("policy-r1"),
        _provenance("risk-test", "policy-r1"),
    )


def _plan() -> ExecutionPlanSnapshot:
    fields = {
        "route_identity": "route-test",
        "amount": 100,
        "quote_revision": "quote-r1",
        "quote_block": 100,
        "min_out": 99,
        "slippage_bps": 50,
        "provider_identity": "provider-unresolved",
        "fee_revision": "fee-r1",
        "fee_amount": 1,
        "gas_assumptions": (("gas_limit", "200000"),),
        "calldata": "0xtest",
        "deadline": 200,
        "simulation_state": "passed-test-only",
        "treasury_revision": "treasury-r1",
        "risk_governance_revision": "policy-r1",
        "goal_revision": "goal-r1",
        "strategy_family": "flash_arb",
    }
    return ExecutionPlanSnapshot(
        **fields, execution_plan_id=ExecutionPlanSnapshot.contract_id(fields)
    )


def _decision() -> DecisionSnapshot:
    plan = _plan()
    return DecisionSnapshot(
        "opportunity-test",
        plan,
        _treasury(),
        _conversion(),
        _provider(),
        _risk(),
        "single",
        "flash_arb",
        (("pacing", "constrained"),),
        _fresh("policy-r1"),
        _provenance("decision-test", "policy-r1"),
        "policy-r1",
        "trade-correlation-test",
    )


def test_snapshots_are_explicitly_synthetic_and_do_not_choose_authorities():
    assert TEST_MARKER == "TEST_ONLY_SYNTHETIC"
    assert _treasury().asset_identity == "ASSET_UNSPECIFIED"
    assert _provider().provider_identity == "provider-unresolved"
    assert _conversion().source_identity == "conversion-source-x"


def test_treasury_rejects_ambiguous_or_legacy_proxy_truth():
    assert _treasury().validate(now=NOW) is SnapshotStatus.VALID
    assert (
        replace(_treasury(), asset_identity="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_treasury(), decimal_authority_revision="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert "estimated_capital_wei" not in _treasury().__dataclass_fields__
    assert "bankroll_proxy" not in _treasury().__dataclass_fields__


def test_conversion_fails_closed_for_missing_stale_conflicting_or_ambiguous_evidence():
    assert _conversion().validate(now=NOW) is SnapshotStatus.VALID
    assert (
        replace(_conversion(), source_decimals=None).validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_conversion(), source_identity="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_conversion(), conflict_state="contradictory").validate(now=NOW)
        is SnapshotStatus.PROVENANCE_CONFLICT
    )
    assert (
        replace(_conversion(), direction="ambiguous").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_conversion(), freshness=_fresh("other-revision")).validate(now=NOW)
        is SnapshotStatus.REVISION_CONFLICT
    )
    assert (
        replace(
            _conversion(),
            freshness=Freshness(
                NOW - timedelta(minutes=1), 99, "block-99", timedelta(seconds=1), "conversion-r1"
            ),
        ).validate(now=NOW)
        is SnapshotStatus.STALE
    )


def test_provider_capacity_is_not_a_dimensionless_multiplier():
    assert _provider().validate(now=NOW) is SnapshotStatus.VALID
    assert (
        replace(_provider(), capacity_units="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_provider(), fee_schedule_revision="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert "dimensionless_multiplier" not in _provider().__dataclass_fields__


def test_risk_governance_requires_compatible_revisioned_state():
    assert _risk().validate(now=NOW, required_policy_revision="policy-r1") is SnapshotStatus.VALID
    assert (
        replace(_risk(), policy_revision="policy-r2").validate(
            now=NOW, required_policy_revision="policy-r1"
        )
        is SnapshotStatus.REVISION_CONFLICT
    )
    assert (
        replace(_risk(), state={}).validate(now=NOW, required_policy_revision="policy-r1")
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(_risk(), state={"contradictory": True}).validate(
            now=NOW, required_policy_revision="policy-r1"
        )
        is SnapshotStatus.PROVENANCE_CONFLICT
    )
    assert (
        replace(
            _risk(),
            freshness=Freshness(
                NOW - timedelta(minutes=1), 99, "block-99", timedelta(seconds=1), "policy-r1"
            ),
        ).validate(now=NOW, required_policy_revision="policy-r1")
        is SnapshotStatus.STALE
    )


def test_material_plan_changes_invalidate_test_only_plan_identity():
    plan = _plan()
    assert plan.validate() is SnapshotStatus.VALID
    changed = replace(
        plan,
        amount=101,
        execution_plan_id=ExecutionPlanSnapshot.contract_id(
            {**plan.material_fields(), "amount": 101}
        ),
    )
    assert changed.execution_plan_id != plan.execution_plan_id
    assert replace(
        plan, execution_plan_id=plan.route_identity
    ).execution_plan_id != ExecutionPlanSnapshot.contract_id(plan.material_fields())


def test_decision_snapshot_is_immutable_revision_aware_and_fail_closed():
    decision = _decision()
    assert decision.validate(now=NOW) is SnapshotStatus.VALID
    with pytest.raises((AttributeError, TypeError)):
        decision.policy_revision = "policy-r2"  # type: ignore[misc]
    assert (
        replace(decision, selected_strategy="stat_arb").validate(now=NOW) is SnapshotStatus.INVALID
    )
    assert (
        replace(decision, trade_correlation_id="").validate(now=NOW)
        is SnapshotStatus.MISSING_AUTHORITY
    )
    assert (
        replace(
            decision,
            freshness_envelope=Freshness(
                NOW - timedelta(minutes=1), 99, "block-99", timedelta(seconds=1), "policy-r1"
            ),
        ).validate(now=NOW)
        is SnapshotStatus.STALE
    )
    assert (
        replace(decision, risk_governance=replace(_risk(), policy_revision="policy-r2")).validate(
            now=NOW
        )
        is SnapshotStatus.REVISION_CONFLICT
    )


def test_validation_is_deterministic_explicit_now_and_has_no_runtime_io_boundary():
    decision = _decision()
    assert decision.validate(now=NOW) == decision.validate(now=NOW)
    assert decision.validate(now=NOW + timedelta(minutes=1)) is SnapshotStatus.STALE
    source = open(__file__, encoding="utf-8").read()
    forbidden_name = "CapitalDemand" + "Composer"
    assert forbidden_name not in source
    decision_engine_name = "Decision" + "Engine"
    assert decision_engine_name not in source
    json_rpc_name = "JsonRpc" + "Client"
    assert json_rpc_name not in source
    forbidden_storage_name = "sql" + "ite"
    assert forbidden_storage_name not in source.lower()


def test_correlation_identity_remains_distinct_through_replacement_and_reorg():
    correlation = _decision().trade_correlation_id
    assert correlation not in {"tx_hash", "capitalCommitId", "execution_plan_id", "replay_id"}
    replacement = {"trade_correlation_id": correlation, "tx_hash": "tx-replacement"}
    reorg_recovery = {"trade_correlation_id": correlation, "tx_hash": "tx-reorg-recovery"}
    assert replacement["trade_correlation_id"] == reorg_recovery["trade_correlation_id"]
    assert replacement["tx_hash"] != reorg_recovery["tx_hash"]


def test_phase_a_policy_remains_flash_arb_only_and_goals_ai_do_not_authorize():
    decision = _decision()
    assert decision.selected_strategy == "flash_arb"
    assert "authorize_trade" not in dict(decision.wealth_goal_posture)
    assert "ai_authorized" not in dict(decision.wealth_goal_posture)
    assert dict(decision.risk_governance.state)["gates"] == "mandatory"
