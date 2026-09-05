from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.caq_kds import bus as bus_module
from victor_ai_bot.omar.operator_intent import operator_intent_fingerprint
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import (
    RuntimeDecisionFinalizeFacade,
)


class _Controls:
    control_mode = "operator"
    aggression_mode = "aggressive"
    brain_mode = "auto"
    force_send_mode = ""
    force_gas_mode = ""


class _GoalService:
    def __init__(self) -> None:
        self.target_amount = "100000"
        self.timeframe_days = 180
        self.revision = 1

    def state(self, _runtime):
        return {
            "goal": {
                "target_amount": self.target_amount,
                "timeframe_days": self.timeframe_days,
            },
            "meta": {
                "active_goal_id": "goal-1",
                "goal_revision": self.revision,
            },
        }


class _Omar:
    def __init__(self) -> None:
        self.calls = []

    def bind_runtime(self, runtime):
        self.runtime = runtime

    def observe_decision(self, **kwargs):
        self.calls.append(kwargs)


def test_phase7_canonical_intent_is_attached_before_omar_observation(monkeypatch):
    monkeypatch.setattr(
        bus_module,
        "BUS",
        SimpleNamespace(snapshot=lambda: {"command": {"data": {"risk_multiplier": 0.75}}}),
    )
    monkeypatch.setenv("VICTOR_ENABLE_OMAR", "1")

    runtime = RuntimeDecisionFinalizeFacade()
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._cc = SimpleNamespace(controls=_Controls())
    runtime._wealth_goal_service = _GoalService()
    runtime._omar = _Omar()

    opportunity = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(
        action="trade",
        opp_id="opp-1",
        route_id="route-1",
        size_mult=0.75,
        borrow_mult=1.0,
        gas_mode="fast",
        p_success=0.91,
        ev_wei=5000,
        reason="selected",
        rl_state="state-1",
        rl_action_index=2,
        metadata={},
    )

    runtime._record_omar_decision([opportunity], decision, current_block=123)

    lineage = opportunity.meta["canonical_lineage"]
    snapshot = lineage["operator_intent"]
    fingerprint = lineage["intent_fingerprint"]

    assert lineage["decision_id"] == decision.metadata["identity"]["decision_id"]
    assert lineage["correlation_id"] == decision.metadata["identity"]["correlation_id"]
    assert snapshot["aggression_mode"] == "aggressive"
    assert snapshot["risk_multiplier"] == 0.75
    assert snapshot["desired_wealth_goal"]["goal"]["target_amount"] == "100000"
    assert snapshot["ai_recommendation"]["action"] == "trade"
    assert fingerprint == operator_intent_fingerprint(snapshot)

    call = runtime._omar.calls[0]
    assert call["decision_id"] == lineage["decision_id"]
    assert call["correlation_id"] == lineage["correlation_id"]
    assert call["metadata"]["intent_fingerprint"] == fingerprint
    assert call["operator_intent"].to_dict() == snapshot


def test_phase7_intent_fingerprint_changes_only_with_decision_time_context():
    first = {
        "aggression_mode": "balanced",
        "risk_multiplier": 0.50,
        "desired_wealth_goal": {"target_amount": "100000", "timeframe_days": 365},
        "ai_recommendation": {"action": "wait"},
    }
    second = dict(first)
    second["risk_multiplier"] = 0.90

    assert operator_intent_fingerprint(first) != operator_intent_fingerprint(second)
    assert operator_intent_fingerprint(first) == operator_intent_fingerprint(dict(first))
