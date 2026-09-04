from __future__ import annotations

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime


def test_omar_observe_outcome_updates_policy_once(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    runtime = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            policy_checkpoint_enabled=False,
        ),
        chain_name="ethereum",
    )

    before = runtime.state()["policy"]
    result = runtime.observe_outcome(
        decision_id="decision-1",
        correlation_id="corr-1",
        execution_id="execution-1",
        settlement_id="settlement-1",
        action="EXECUTE",
        tx_hash="0xabc",
        reward_scaled=12.5,
        state_key="state-1",
        role="ARBITRAGE_AGENT",
        latency_ms=37,
        outcome_truth_verified=True,
        metadata={"operator_intent": {"aggression_mode": "balanced"}},
    )

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert runtime.last_observation["settlement_id"] == "settlement-1"
    assert runtime.last_observation["policy_update"]["updated"] == 1.0
    assert runtime.state()["policy"]["updates"] > before.get("updates", 0)


def test_omar_observe_outcome_is_idempotent_for_settlement(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    runtime = OmarRuntime(
        OmarConfig(enabled=True, self_play_enabled=False, policy_checkpoint_enabled=False),
        chain_name="ethereum",
    )
    kwargs = {
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "execution_id": "execution-1",
        "settlement_id": "settlement-1",
        "action": "EXECUTE",
        "reward_scaled": 10.0,
        "state_key": "state-1",
    }
    first = runtime.observe_outcome(**kwargs)
    second = runtime.observe_outcome(**kwargs)

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["duplicate"] is True
    assert runtime.state()["policy"]["updates"] == 1
