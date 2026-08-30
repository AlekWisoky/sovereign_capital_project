from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _Recommendation:
    action = "EXECUTE"
    state_key = "state-1"
    confidence = 0.91
    trained = True
    observations = 25
    reason = "learned_execution_action"
    veto = False
    size_mult = 0.8
    gas_mode = "standard"

    def to_dict(self):
        return {
            "state_key": self.state_key,
            "action": self.action,
            "confidence": self.confidence,
            "trained": self.trained,
            "observations": self.observations,
            "reason": self.reason,
            "veto": self.veto,
            "size_mult": self.size_mult,
            "gas_mode": self.gas_mode,
        }


class _Omar:
    enabled = True

    def __init__(self):
        self.calls = []

    def recommend(self, context):
        self.context = context
        return _Recommendation()

    def observe_decision(self, **kwargs):
        self.calls.append(kwargs)


def _runtime(omar=None):
    return SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=omar,
        _cc=SimpleNamespace(
            controls=SimpleNamespace(aggression_mode="aggressive", risk_multiplier=0.75)
        ),
        _wealth_goal_service=None,
        _ai_recommendation={"action": "execute", "confidence": 0.92},
        _market_regime={"volatility": 0.12},
    )


def test_production_decision_boundary_uses_canonical_identity_when_omar_disabled():
    runtime = _runtime(None)
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    chosen, returned = runtime._apply_omar_to_candidate(opp, decision, current_block=123)

    assert chosen is opp
    assert returned is decision
    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"]
    assert lineage["correlation_id"]
    assert not lineage["decision_id"].startswith("omar-")
    assert decision.metadata["canonical_decision_id"] == lineage["decision_id"]
    assert decision.metadata["correlation_id"] == lineage["correlation_id"]


def test_production_omar_observes_with_canonical_identity_and_single_intent_snapshot():
    omar = _Omar()
    runtime = _runtime(omar)
    opp = SimpleNamespace(id="opp-2", route_id="route-2", meta={"brain": {"p_success": 0.91, "ev_wei": 100}})
    decision = SimpleNamespace(metadata={})

    chosen, returned = runtime._apply_omar_to_candidate(opp, decision, current_block=456)

    assert chosen is opp
    assert returned is decision
    assert len(omar.calls) == 1
    call = omar.calls[0]
    lineage = lineage_from_opportunity(opp)

    assert call["decision_id"] == lineage["decision_id"]
    assert not call["decision_id"].startswith("omar-")
    assert call["metadata"]["canonical_decision_id"] == lineage["decision_id"]
    assert call["metadata"]["correlation_id"] == lineage["correlation_id"]
    assert call["metadata"]["operator_intent"]["aggression_mode"] == "aggressive"
    assert call["context"]["canonical_decision_id"] == lineage["decision_id"]
    assert call["context"]["operator_intent"]["risk_multiplier"] == 0.75
    assert opp.meta["brain"]["canonical_decision_id"] == lineage["decision_id"]
    assert "omar_decision_id" not in opp.meta["brain"]
