from pathlib import Path

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.real_learning import ACTIONS, OmarRealLearner
from victor_ai_bot.omar.runtime import OmarRuntime


def test_real_learner_persists_and_reloads(tmp_path: Path):
    path = tmp_path / "omar.json"
    learner = OmarRealLearner(path=str(path), min_observations=1)
    key = learner.state_key(
        {
            "margin_ratio": 0.001,
            "gas_ratio": 0.0004,
            "p_success": 0.9,
            "drawdown_pct": 1.0,
            "execution_realism": 0.9,
            "stability": 0.9,
            "goal_gap_pct": 0.0,
            "volatility": 0.1,
            "legs": 2,
        }
    )
    result = learner.observe(state_key=key, action="EXECUTE", reward=5.0, outcome={"ok": True})
    assert result["ok"] is True
    learner.save()

    reloaded = OmarRealLearner(path=str(path), min_observations=1)
    rec = reloaded.recommend({"margin_ratio": 0.001, "gas_ratio": 0.0004, "p_success": 0.9, "legs": 2})
    assert rec.trained is True
    assert rec.action in ACTIONS
    assert reloaded.total_observations == 1


def test_operator_intent_and_goal_shape_learning_state():
    learner = OmarRealLearner(path="/tmp/omar-intent-test.json", min_observations=1)
    base = {
        "margin_ratio": 0.001,
        "gas_ratio": 0.0004,
        "p_success": 0.9,
        "drawdown_pct": 1.0,
        "execution_realism": 0.9,
        "stability": 0.9,
        "goal_gap_pct": 0.0,
        "volatility": 0.1,
        "legs": 2,
        "aggression_mode": "conservative",
        "risk_multiplier": 0.5,
        "goal_target_amount": "10000",
        "goal_timeframe_days": 30,
        "ai_recommendation_action": "hold",
        "ai_recommendation_posture": "defensive",
        "ai_recommendation_confidence": 0.8,
    }
    aggressive = dict(base)
    aggressive.update(
        {
            "aggression_mode": "aggressive",
            "risk_multiplier": 1.0,
            "goal_target_amount": "100000",
            "goal_timeframe_days": 180,
            "ai_recommendation_action": "execute",
            "ai_recommendation_posture": "risk_on",
            "ai_recommendation_confidence": 0.95,
        }
    )
    assert learner.state_key(base) != learner.state_key(aggressive)


def test_untrained_omar_does_not_influence_live_decision(tmp_path: Path):
    rt = OmarRuntime(OmarConfig(enabled=True, self_play_enabled=False, real_learning_min_observations=20), "test")
    rt.learning_path = str(tmp_path / "omar.json")
    rt._real_learner = OmarRealLearner(path=rt.learning_path, min_observations=20)
    rec = rt.recommend({"margin_ratio": 0.001, "gas_ratio": 0.0004, "p_success": 0.9, "legs": 2})
    assert rec.trained is False
    assert rec.veto is False
    assert rec.size_mult == 1.0
