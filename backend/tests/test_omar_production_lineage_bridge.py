from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.omar import production_lineage_bridge
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge


def test_decision_identity_is_preserved_when_omar_is_not_present():
    runtime = SimpleNamespace()
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = None
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    runtime._apply_omar_to_candidate = RuntimeDecisionFacade._apply_omar_to_candidate.__get__(runtime)
    install_production_lineage_bridge()

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


def test_settlement_guard_requires_physical_lineage_and_rejects_cross_trade_lineage():
    assert production_lineage_bridge._lineage_matches(
        {
            "status": "settled",
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "opportunity_id": "opp-1",
            "lineage_persisted": True,
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
            "lineage_persisted": True,
        },
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
    assert not production_lineage_bridge._lineage_matches(
        {
            "status": "settled",
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "opportunity_id": "opp-1",
            "lineage_persisted": False,
        },
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
