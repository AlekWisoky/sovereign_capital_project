from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.omar import production_lineage_bridge


def test_identity_is_created_before_omar_and_preserved_on_decision_and_opportunity():
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
    )

    assert identity.decision_id
    assert identity.correlation_id
    assert opp.meta["brain"]["canonical_decision_id"] == identity.decision_id
    assert opp.meta["brain"]["correlation_id"] == identity.correlation_id
    assert decision.metadata["canonical_decision_id"] == identity.decision_id
    assert decision.metadata["correlation_id"] == identity.correlation_id
    assert lineage_from_opportunity(opp) == {
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
    }


def test_identity_is_stable_when_the_same_decision_is_reentered():
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    first = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
    )
    second = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
    )

    assert second == first


def test_settlement_guard_rejects_cross_trade_lineage():
    assert production_lineage_bridge._lineage_matches(
        {
            "status": "settled",
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "opportunity_id": "opp-1",
        },
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
    assert not production_lineage_bridge._lineage_matches(
        {
            "status": "settled",
            "decision_id": "decision-2",
            "correlation_id": "corr-2",
            "opportunity_id": "opp-2",
        },
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
