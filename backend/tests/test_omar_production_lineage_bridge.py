from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.omar import production_lineage_bridge
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


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


def test_runtime_decision_boundary_creates_identity_even_when_omar_is_disabled():
    runtime = object.__new__(RuntimeDecisionFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = None
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    chosen, returned_decision = runtime._apply_omar_to_candidate(
        opp,
        decision,
        current_block=123,
    )

    assert chosen is opp
    assert returned_decision is decision
    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"]
    assert lineage["correlation_id"]
    assert decision.metadata["canonical_decision_id"] == lineage["decision_id"]
    assert decision.metadata["correlation_id"] == lineage["correlation_id"]


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
