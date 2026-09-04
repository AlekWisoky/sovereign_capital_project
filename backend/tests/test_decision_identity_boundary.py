from victor_ai_bot.decision_engine import TradeDecision
from victor_ai_bot.identity import identity_from
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import (
    RuntimeDecisionFinalizeFacade,
)


def test_decision_boundary_assigns_one_canonical_identity():
    decision = TradeDecision(action="trade", opp_id="opp-1", route_id="route-1")
    finalized = RuntimeDecisionFinalizeFacade()._ensure_decision_identity(
        decision, opps=[]
    )

    identity = identity_from(finalized)
    assert identity is not None
    assert identity.decision_id.startswith("decision_")
    assert identity.correlation_id.startswith("corr_")
    assert finalized.decision_id == identity.decision_id
    assert finalized.correlation_id == identity.correlation_id


def test_decision_identity_survives_second_attachment():
    facade = RuntimeDecisionFinalizeFacade()
    decision = facade._ensure_decision_identity(
        TradeDecision(action="trade", opp_id="opp-1"), opps=[]
    )
    first = identity_from(decision)

    decision = facade._ensure_decision_identity(decision, opps=[])
    second = identity_from(decision)

    assert first == second
