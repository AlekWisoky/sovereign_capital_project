from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.fund_os.health_states import HealthState
from victor_ai_bot.fund_os.launch_modes import LaunchMode, LaunchProfile
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.omar.trainer import OmarTrainer


def test_runtime_method_chain_settlement_uses_real_omar_learning_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    omar = OmarRuntime(
        OmarConfig(enabled=True, self_play_enabled=False, policy_checkpoint_enabled=False),
        chain_name="ethereum",
    )

    def capital_engine_state():
        return {
            "authority_id": "prime-authority-1",
            "available_wei": 20_000,
            "allocatable_wei": 10_000,
            "family_allocatable_wei": {"flash_arb": 10_000},
            "status": "healthy",
            "freshness_class": "live",
            "source": "capital_engine_state",
        }

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=omar,
        capital_engine_state=capital_engine_state,
    )
    omar.bind_runtime(runtime)
    omar._trainer = OmarTrainer(omar.cfg, checkpoint_path=None)

    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})
    intent = {
        "aggression_mode": "aggressive",
        "risk_multiplier": 0.75,
        "desired_wealth_goal": {"target_amount": "100000", "timeframe_days": 180},
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
        "action": "EXECUTE",
        "brain": {
            "canonical_decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
        },
        "canonical_lineage": {
            "decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
            "execution_id": "exec-1",
            "settlement_id": "settle-1",
            "operator_intent": intent,
            "intent_fingerprint": "intent-fp-1",
        },
        "capital_demand": {"requested_wei": 1000, "family": "flash_arb"},
    }
    outcome = {
        "status": "settled",
        "ok": True,
        "realized_net_usd": 4.25,
        "expected_net_usd": 4.0,
        "realized_pnl_wei": 425,
        "realized_gas_wei": 25,
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
    assert result["eligible_for_learning"] is True
    assert result["lineage"]["decision_id"] == identity.decision_id
    assert result["lineage"]["correlation_id"] == identity.correlation_id
    assert result["lineage"]["execution_id"] == "exec-1"
    assert result["lineage"]["settlement_id"] == "settle-1"
    assert result["operator_intent"]["aggression_mode"] == "aggressive"
    assert result["operator_intent"]["desired_wealth_goal"]["target_amount"] == "100000"
    assert result["operator_intent"]["ai_recommendation"]["action"] == "execute"
    assert result["attribution"]["action"] == "EXECUTE"
    assert result["attribution"]["reward_wei"] == 400
    assert result["attribution"]["eligible_for_learning"] is True
    assert result["policy_update"]["updated"] is True
    assert result["policy_update"]["capital_authority_source"] == "capital_engine_state"
    assert omar._real_learning is not None
    assert identity.decision_id in omar._real_learning._decisions
    assert "exec-1" in omar._real_learning._executions
    assert "settle-1" in omar._real_learning._outcomes
    assert omar._trainer.policy.updates > 0


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
