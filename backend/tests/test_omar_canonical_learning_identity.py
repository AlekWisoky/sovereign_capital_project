from __future__ import annotations

from victor_ai_bot.omar.real_learning import OmarRealLearner


def test_real_learner_requires_canonical_decision_identity(tmp_path):
    learner = OmarRealLearner(path=str(tmp_path / "policy.json"), min_observations=1)
    state_key = learner.state_key(
        {
            "margin_ratio": 0.001,
            "gas_ratio": 0.0004,
            "p_success": 0.82,
            "drawdown_pct": 1.0,
            "execution_realism": 0.8,
            "stability": 0.8,
            "goal_gap_pct": 1.0,
            "volatility": 0.1,
        }
    )

    missing = learner.observe(
        state_key=state_key,
        action="EXECUTE",
        reward=1.0,
        outcome={"tx_hash": "0x-no-substitute"},
    )
    assert missing == {"ok": False, "reason": "missing_canonical_decision_id"}
    assert learner.total_observations == 0


def test_real_learner_persists_canonical_decision_identity_and_lineage(tmp_path):
    policy_path = tmp_path / "policy.json"
    learner = OmarRealLearner(path=str(policy_path), min_observations=1)
    state_key = learner.state_key(
        {
            "margin_ratio": 0.001,
            "gas_ratio": 0.0004,
            "p_success": 0.82,
            "drawdown_pct": 1.0,
            "execution_realism": 0.8,
            "stability": 0.8,
            "goal_gap_pct": 1.0,
            "volatility": 0.1,
        }
    )

    result = learner.observe(
        state_key=state_key,
        action="EXECUTE",
        reward=2.5,
        outcome={
            "canonical_decision_id": "decision-canonical-123",
            "correlation_id": "corr-123",
            "execution_id": "execution-123",
            "outcome_id": "outcome-123",
            "tx_hash": "0x-real-fill",
            "latency_ms": 37,
        },
    )

    assert result["ok"] is True
    assert result["canonical_decision_id"] == "decision-canonical-123"
    assert result["correlation_id"] == "corr-123"
    assert result["action"] == "EXECUTE"

    event_path = str(policy_path) + ".jsonl"
    event = open(event_path, encoding="utf-8").read()
    assert '"canonical_decision_id": "decision-canonical-123"' in event
    assert '"correlation_id": "corr-123"' in event
    assert '"tx_hash": "0x-real-fill"' in event
    assert '"latency_ms": 37' in event


def test_learning_identity_does_not_use_tx_hash_as_decision_id(tmp_path):
    learner = OmarRealLearner(path=str(tmp_path / "policy.json"), min_observations=1)
    state_key = learner.state_key({})

    result = learner.observe(
        state_key=state_key,
        action="WAIT",
        reward=0.0,
        outcome={"tx_hash": "0x-must-not-become-decision-id"},
    )

    assert result["ok"] is False
    assert result["reason"] == "missing_canonical_decision_id"
