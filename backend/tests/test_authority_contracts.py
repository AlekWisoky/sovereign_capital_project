from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from victor_ai_bot.authority_contracts import (
    AuthorityContractError,
    AuthorityStatus,
    ConversionSnapshot,
    DecisionSnapshot,
    Evidence,
    ExecutionPlanSnapshot,
    FreshnessSnapshot,
    PolicySnapshot,
    Provenance,
    ProviderCapacitySnapshot,
    ProviderFeeSnapshot,
    Revision,
    SnapshotState,
    TreasurySnapshot,
    Unit,
)


NOW = datetime(2026, 8, 14, 23, 55, tzinfo=timezone.utc)


def rev(source: str, value: str = "r1") -> Revision:
    return Revision(source, value, "authority-v1")


def provenance(source: str = "fixture") -> Provenance:
    return Provenance(source=source, source_id="fixture-1", evidence_type="test", observed_at=NOW, chain="test", block_number=100, block_hash="block-100", revision=rev(source))


def freshness(revision: Revision | None = None, horizon: timedelta | None = timedelta(seconds=30)) -> FreshnessSnapshot:
    return FreshnessSnapshot(source="fixture", observed_at=NOW, observed_block=100, observed_block_hash="block-100", horizon=horizon, policy_revision=revision, state=SnapshotState.VALID)


def evidence(status: AuthorityStatus = AuthorityStatus.PROVEN, revision: Revision | None = None, conflicts: tuple[str, ...] = ()) -> Evidence:
    return Evidence(status=status, provenance=provenance(), freshness=freshness(revision or rev("fixture")), revision=revision or rev("fixture"), conflicts=conflicts)


def unit(asset: str = "ASSET_A", denomination: str = "asset-native") -> Unit:
    return Unit(asset=asset, denomination=denomination, decimals=18, decimal_revision=rev("decimals"))


def treasury(status: AuthorityStatus = AuthorityStatus.PROVEN) -> TreasurySnapshot:
    return TreasurySnapshot("scope", "test-chain", "account-1", unit(), 1000, 800, 100, 100, evidence(status), rev("treasury"))


def plan() -> ExecutionPlanSnapshot:
    return ExecutionPlanSnapshot("route-1", 100, unit(), rev("quote"), 100, (99,), "provider-unresolved", rev("fee"), (("gas_limit", "200000"),), 200, "simulated-test", rev("treasury"), rev("risk"), rev("governance"), rev("policy"), "plan-1", provenance("plan"))


def decision(**changes) -> DecisionSnapshot:
    values = dict(
        opportunity_id="opp-1",
        economic_intent_id="intent-1",
        trade_correlation_id="corr-1",
        execution_plan=plan(),
        treasury=treasury(),
        conversion=None,
        provider_capacity=None,
        provider_fee=None,
        exposure=None,
        risk=None,
        governance=None,
        goal=None,
        freshness=freshness(rev("policy")),
        provenance=provenance("decision"),
        policy_revision=rev("policy"),
        status=AuthorityStatus.PROVEN,
    )
    values.update(changes)
    return DecisionSnapshot(**values)


def test_contracts_are_immutable_and_require_explicit_provenance():
    with pytest.raises(FrozenInstanceError):
        treasury().scope = "other"  # type: ignore[misc]
    with pytest.raises(AuthorityContractError):
        Provenance(source="", observed_at=NOW)


def test_revision_compatibility_is_deterministic_and_source_specific():
    assert rev("x").compatible_with(rev("x"))
    assert not rev("x").compatible_with(rev("y"))
    assert not rev("x", "r1").compatible_with(rev("x", "r2"))


def test_freshness_requires_explicit_now_and_does_not_invent_ttl():
    assert freshness().evaluate(now=NOW, revision=rev("fixture")) is SnapshotState.VALID
    assert freshness().evaluate(now=NOW + timedelta(seconds=31), revision=rev("fixture")) is SnapshotState.STALE
    assert freshness(horizon=None).evaluate(now=NOW, revision=rev("fixture")) is SnapshotState.POLICY_UNRESOLVED
    with pytest.raises(AuthorityContractError):
        freshness().evaluate(now=datetime(2026, 8, 14, 23, 55), revision=rev("fixture"))


def test_unresolved_and_conflicting_evidence_fail_closed():
    assert treasury(AuthorityStatus.UNRESOLVED).validate(now=NOW) is SnapshotState.POLICY_UNRESOLVED
    assert treasury(AuthorityStatus.CONFLICTING).validate(now=NOW) is SnapshotState.PROVENANCE_CONFLICT
    assert evidence(conflicts=("source-a/source-b",)).validate(now=NOW) is SnapshotState.PROVENANCE_CONFLICT


def test_units_and_missing_decimals_are_not_silently_compatible():
    assert not unit().compatible_with(unit(asset="ASSET_B"))
    assert TreasurySnapshot("scope", "chain", "acct", Unit("ASSET", "native", None), 1, 1, 0, 0, evidence(), rev("treasury")).validate(now=NOW) is SnapshotState.MISSING


def test_execution_plan_has_independent_identity():
    p = plan()
    assert p.validate() is SnapshotState.VALID
    assert p.execution_plan_id != p.route_id
    assert ExecutionPlanSnapshot.content_id({"route": p.route_id, "amount": p.amount}) != ExecutionPlanSnapshot.content_id({"route": p.route_id, "amount": p.amount + 1})


def test_provider_capacity_and_fee_contracts_require_explicit_units_and_fee_evidence():
    capacity = ProviderCapacitySnapshot("provider-unresolved", unit(), 1000, "asset-native", evidence(), 100, "block-100")
    fee = ProviderFeeSnapshot("provider-unresolved", unit(), 1, None, None, evidence())
    assert capacity.validate(now=NOW) is SnapshotState.VALID
    assert fee.validate(now=NOW) is SnapshotState.VALID
    assert ProviderCapacitySnapshot("provider", unit(), 1, "", evidence(), 1, "hash").validate(now=NOW) is SnapshotState.MISSING


def test_decision_validation_is_pure_explicit_now_and_rejects_unresolved_root():
    assert decision().validate(now=NOW) is SnapshotState.VALID
    assert decision(status=AuthorityStatus.UNRESOLVED).validate(now=NOW) is SnapshotState.POLICY_UNRESOLVED
    assert decision(trade_correlation_id="").validate(now=NOW) is SnapshotState.MISSING
    assert decision(freshness=freshness(rev("policy"), timedelta(seconds=1))).validate(now=NOW + timedelta(seconds=2)) is SnapshotState.STALE


def test_policy_snapshot_is_read_only_evidence_not_runtime_authority():
    policy = PolicySnapshot(rev("risk"), {"ready": True}, evidence())
    assert policy.validate(now=NOW) is SnapshotState.VALID
    assert "rpc" not in type(policy).validate.__code__.co_names
    assert "sqlite" not in type(policy).validate.__code__.co_names
