from types import SimpleNamespace

from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


def make_runtime():
    runtime = RuntimeDecisionFacade()
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._cc = SimpleNamespace(controls=SimpleNamespace(aggression_mode="aggressive", risk_multiplier=0.65))
    runtime._wealth_goal_service = SimpleNamespace(
        state=lambda _: {
            "state": {
                "goal": {
                    "target_amount": "250000",
                    "target_return_percentage": 12.5,
                    "timeframe_days": 90,
                },
                "meta": {"active_goal_id": "goal-test", "goal_revision": 4},
                "currentReturnPct": 4.25,
                "drawdownPct": 1.75,
            }
        }
    )
    runtime._ai_recommendation = {
        "action": "reduce_exposure",
        "posture": "defensive",
        "confidence": 0.91,
        "source": "operator_ai",
    }
    runtime._omar = None
    return runtime


def test_operator_intent_reaches_canonical_decision_context():
    install_production_lineage_bridge()
    runtime = make_runtime()
    opp = SimpleNamespace(id="opp-18", route_id="route-18", meta={})
    decision = SimpleNamespace(metadata={})

    chosen, returned = runtime._apply_omar_to_candidate(opp, decision, current_block=123)

    assert chosen is opp
    assert returned is decision
    assert decision.metadata["canonical_decision_id"]
    assert decision.metadata["correlation_id"]
    intent = decision.metadata["operator_intent"]
    assert intent["aggression_mode"] == "aggressive"
    assert intent["risk_multiplier"] == 0.65
    assert intent["goal"]["target_amount"] == "250000"
    assert intent["goal"]["timeframe_days"] == 90.0
    assert intent["goal"]["goal_revision"] == 4
    assert intent["ai_recommendation"]["action"] == "reduce_exposure"
    assert intent["ai_recommendation"]["confidence"] == 0.91
    assert decision.metadata["operator_intent_fingerprint"]
    assert opp.meta["brain"]["operator_intent"] == intent


def test_existing_operator_intent_is_write_once_for_decision_identity():
    install_production_lineage_bridge()
    runtime = make_runtime()
    opp = SimpleNamespace(
        id="opp-stable",
        route_id="route-stable",
        meta={
            "brain": {
                "canonical_decision_id": "decision-fixed",
                "correlation_id": "corr-fixed",
                "operator_intent": {"aggression_mode": "conservative"},
                "operator_intent_fingerprint": "fingerprint-fixed",
            }
        },
    )
    decision = SimpleNamespace(metadata={})

    runtime._apply_omar_to_candidate(opp, decision, current_block=124)

    assert decision.metadata["canonical_decision_id"] == "decision-fixed"
    assert decision.metadata["correlation_id"] == "corr-fixed"
    assert decision.metadata["operator_intent"] == {"aggression_mode": "conservative"}
    assert decision.metadata["operator_intent_fingerprint"] == "fingerprint-fixed"
