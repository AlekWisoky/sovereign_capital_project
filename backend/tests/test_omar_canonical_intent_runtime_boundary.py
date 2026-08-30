from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.runtime_services.runtime_decision_facade as decision_facade
from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.operator_intent import intent_fingerprint


class _Recommendation:
    action = "EXECUTE"
    state_key = "state-1"
    confidence = 0.8
    trained = True
    observations = 4
    reason = "learned"
    veto = False
    size_mult = 0.8
    gas_mode = "standard"

    def to_dict(self):
        return {
            "action": self.action,
            "state_key": self.state_key,
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
        self.observed = []

    def recommend(self, context):
        self.context = context
        return _Recommendation()

    def observe_decision(self, **kwargs):
        self.observed.append(kwargs)


def test_omar_runtime_reuses_canonical_identity_and_frozen_operator_intent(monkeypatch):
    """OMAR must not mint a second identity after the canonical decision exists."""
    monkeypatch.setattr(
        decision_facade,
        "build_features",
        lambda _opp: SimpleNamespace(margin_ratio=0.5, gas_ratio=0.2, legs=2),
    )

    intent = {
        "aggression_mode": "aggressive",
        "risk_multiplier": 0.75,
        "goal": {
            "target_amount": "100000",
            "timeframe_days": 90,
            "goal_revision": 3,
        },
        "ai_recommendation": {
            "action": "WAIT",
            "posture": "protect_capital",
            "confidence": 0.91,
        },
        "authority": "operator_intent_only",
    }
    omar = _Omar()
    runtime = object.__new__(decision_facade.RuntimeDecisionFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = omar
    runtime._market_regime = {"volatility": 0.1}
    runtime._wealth_goal_service = None

    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        meta={"brain": {"p_success": 0.9, "ev_wei": 500}},
    )
    decision = SimpleNamespace(
        action="trade",
        opp_id="opp-1",
        route_id="route-1",
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        p_success=0.9,
        ev_wei=500,
        metadata={},
    )

    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=intent,
        intent_fingerprint=intent_fingerprint(intent),
    )

    returned_opp, returned_decision = runtime._apply_omar_to_candidate(
        opp, decision, current_block=123
    )

    assert returned_opp is opp
    assert returned_decision is decision
    assert len(omar.observed) == 1
    observed = omar.observed[0]

    # OMAR attribution must attach to the existing canonical identity.
    assert observed["decision_id"] == identity.decision_id
    assert observed["metadata"]["canonical_lineage"]["decision_id"] == identity.decision_id
    assert observed["metadata"]["canonical_lineage"]["correlation_id"] == identity.correlation_id
    assert "omar-" not in observed["decision_id"]

    # The intent passed to learning is the decision-time snapshot, not live
    # controls resolved later in execution.
    assert observed["context"]["operator_intent"] == intent
    assert observed["context"]["operator_intent"] is not intent

    assert opp.meta["canonical_lineage"]["decision_id"] == identity.decision_id
    assert opp.meta["canonical_lineage"]["correlation_id"] == identity.correlation_id
    assert opp.meta["canonical_lineage"]["operator_intent"] == intent
    assert decision.metadata["canonical_decision_id"] == identity.decision_id
    assert decision.metadata["correlation_id"] == identity.correlation_id
