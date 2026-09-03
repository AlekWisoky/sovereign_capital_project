from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from victor_ai_bot.authority_contracts import (
    AuthorityContractError,
    AuthorityStatus,
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


def plan_fields(**changes):
    values = dict(
        route_id="route-1",
        amount=100,
        amount_unit=unit(),
        quote_revision=rev("quote"),
        quote_block=100,
        min_outs=(99,),
        provider="provider-unresolved",
        provider_fee_revision=rev("fee"),
        gas_assumptions=(("gas_limit", "200000"),),
        deadline=200,
        simulation_state="simulated-test",
        treasury_revision=rev("treasury"),
        risk_revision=rev("risk"),
        governance_revision=rev("governance"),
        policy_revision=rev("policy"),
    )
    values.update(changes)
    return values


def plan(**changes) -> ExecutionPlanSnapshot:
    values = plan_fields(**changes)
    provisional = ExecutionPlanSnapshot.__new__(ExecutionPlanSnapshot)
    for key, value in values.items():
        object.__setattr__(provisional, key, value)
    execution_plan_id = ExecutionPlanSnapshot.content_id(provisional.material_fields())
    return ExecutionPlanSnapshot(**values, execution_plan_id=execution_plan_id, provenance=provenance("plan"))


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


def test_nested_policy_state_is_deeply_immutable():
    source = {"outer": {"inner": ["value", {"leaf": True}]}}
    policy = PolicySnapshot(rev("risk"), source, evidence())
    with pytest.raises(TypeError):
        policy.state["outer"]["inner"][1]["leaf"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        policy.state["outer"]["inner"] += ("new",)  # type: ignore[index]
    source["outer"]["inner"][1]["leaf"] = "caller-mutated"
    assert policy.state["outer"]["inner"][1]["leaf"] is True


def test_unsupported_mutable_evidence_objects_are_rejected():
    with pytest.raises(AuthorityContractError):
        PolicySnapshot(rev("risk"), {"custom": object()}, evidence())


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


def test_execution_plan_identity_is_deterministic_and_material_fields_bound():
    first = plan()
    second = plan()
    assert first.execution_plan_id == second.execution_plan_id
    assert first.validate() is SnapshotState.VALID
    material_changes = (
        {"route_id": "route-2"},
        {"amount": 101},
        {"quote_revision": rev("quote", "r2")},
        {"quote_block": 101},
        {"min_outs": (98,)},
        {"provider": "provider-2"},
        {"provider_fee_revision": rev("fee", "r2")},
        {"gas_assumptions": (("gas_limit", "300000"),)},
        {"deadline": 201},
        {"simulation_state": "reverted"},
        {"treasury_revision": rev("treasury", "r2")},
        {"risk_revision": rev("risk", "r2")},
        {"governance_revision": rev("governance", "r2")},
        {"policy_revision": rev("policy", "r2")},
        {"amount_unit": unit(asset="ASSET_B")},
    )
    assert all(plan(**change).execution_plan_id != first.execution_plan_id for change in material_changes)
    with pytest.raises(AuthorityContractError):
        ExecutionPlanSnapshot(**plan_fields(), execution_plan_id="not-the-content-id", provenance=provenance("plan"))


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
