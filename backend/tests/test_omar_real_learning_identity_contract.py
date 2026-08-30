from pathlib import Path

from victor_ai_bot.omar.real_learning import OmarRealLearner


def test_real_learning_requires_canonical_decision_identity(tmp_path: Path):
    learner = OmarRealLearner(path=str(tmp_path / "omar.json"), min_observations=1)
    key = learner.state_key({"margin_ratio": 0.001, "gas_ratio": 0.0004, "p_success": 0.9})

    rejected = learner.observe(
        state_key=key,
        action="EXECUTE",
        reward=1.0,
        outcome={"ok": True},
    )

    assert rejected == {"ok": False, "reason": "missing_canonical_decision_id"}
    assert learner.total_observations == 0


def test_real_learning_accepts_settled_transition_with_canonical_identity(tmp_path: Path):
    learner = OmarRealLearner(path=str(tmp_path / "omar.json"), min_observations=1)
    key = learner.state_key({"margin_ratio": 0.001, "gas_ratio": 0.0004, "p_success": 0.9})

    accepted = learner.observe(
        state_key=key,
        action="EXECUTE",
        reward=1.0,
        outcome={
            "ok": True,
            "status": "settled",
            "canonical_decision_id": "decision-contract-1",
            "correlation_id": "corr-contract-1",
        },
    )

    assert accepted["ok"] is True
    assert accepted["canonical_decision_id"] == "decision-contract-1"
    assert accepted["correlation_id"] == "corr-contract-1"
    assert learner.total_observations == 1
