from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.fund_os.health_states import HealthState
from victor_ai_bot.fund_os.launch_modes import LaunchMode, LaunchProfile
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome


class _Omar:
    enabled = True

    def __init__(self):
        self.calls = []

    def observe_outcome(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "state_key": "state-1", "action": "EXECUTE", "reward": 1.5, "observations": 1}


def test_runtime_method_chain_settlement_uses_canonical_lineage_for_learning():
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=_Omar(),
        _telemetry_service=None,
    )
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})
    intent = {
        "aggression_mode": "aggressive",
        "risk_multiplier": 0.75,
        "goal": {"target_amount": "100000", "timeframe_days": 180},
        "ai_recommendation": {"action": "execute", "confidence": 0.92},
    }

    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=intent,
        intent_fingerprint="intent-fp-1",
    )
    lineage = lineage_from_opportunity(opp)
    assert lineage == {
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
    }

    pending = {
        "opportunity_id": opp.id,
        "route_id": opp.route_id,
        "brain": {
            "canonical_decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
        },
        "canonical_lineage": {
            "decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
            "operator_intent": intent,
            "intent_fingerprint": "intent-fp-1",
        },
    }
    outcome = {
        "status": "settled",
        "ok": True,
        "realized_net_usd": 4.25,
        "expected_net_usd": 4.0,
        "amount_in_wei": 1000,
        "gas_cost_usd": 0.10,
        "slippage_bps": 2.0,
        "latency_ms": 37,
        "route_id": opp.route_id,
        "tx_hash": "0xabc",
        "truth_verified": True,
    }

    result = _observe_settled_outcome(runtime, pending=pending, outcome=outcome)

    assert result["ok"] is True
    assert len(runtime._omar.calls) == 1
    call = runtime._omar.calls[0]
    assert call["decision_id"] == identity.decision_id
    assert call["route_id"] == opp.route_id
    assert call["tx_hash"] == "0xabc"
    assert call["latency_ms"] == 37
    assert call["outcome_truth_verified"] is True
    assert call["metadata"]["source"] == "phase2_canonical_outcome_ledger"
    assert call["metadata"]["canonical_lineage"] == lineage
    assert call["metadata"]["operator_intent"]["aggression_mode"] == "aggressive"
    assert call["metadata"]["operator_intent"]["goal"]["target_amount"] == "100000"
    assert call["metadata"]["operator_intent"]["ai_recommendation"]["action"] == "execute"


def test_v1_only_rollout_progresses_with_flash_arb_as_only_live_family():
    manager = object.__new__(StagedRolloutManager)
    manager.profile = LaunchProfile(mode=LaunchMode.V1_ONLY.value)

    manager._normalize_profile()

    assert manager.profile.active_families == ["flash_arb"]
    assert manager.profile.family_states["flash_arb"] == HealthState.LIVE.value
    assert all(
        state == HealthState.OBSERVE_ONLY.value
        for family, state in manager.profile.family_states.items()
        if family != "flash_arb"
    )
    assert manager.profile.exploration_budget["used_trades"] == 0
    assert manager.profile.exploration_budget["used_cost_usd"] == 0.0
