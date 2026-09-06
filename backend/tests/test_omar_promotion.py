from victor_ai_bot.omar.promotion import PromotionBoundary, PromotionThresholds, evaluate_oos


def _events(count=4):
    return [
        {
            "evaluation_split": "oos",
            "decision_id": f"decision-{i}",
            "outcome_id": f"outcome-{i}",
            "state_key": f"state-{i}",
            "candidate_reward_usd": 10.0,
            "baseline_reward_usd": 8.0,
        }
        for i in range(count)
    ]


def test_oos_gate_rejects_training_or_in_sample_records():
    result = evaluate_oos(
        "candidate-test",
        [
            {
                "evaluation_split": "training",
                "decision_id": "d1",
                "outcome_id": "o1",
                "state_key": "s1",
                "candidate_reward_usd": 10,
                "baseline_reward_usd": 1,
            },
            {
                "evaluation_split": "in_sample",
                "decision_id": "d2",
                "outcome_id": "o2",
                "state_key": "s2",
                "candidate_reward_usd": 10,
                "baseline_reward_usd": 1,
            },
        ],
        PromotionThresholds(min_oos_observations=1, min_unique_states=1),
    )
    assert result.ready is False
    assert result.reason == "insufficient_oos_observations"


def test_promotion_requires_oos_advantage_and_registers_active_version(tmp_path):
    boundary = PromotionBoundary(
        str(tmp_path / "promotion.json"),
        PromotionThresholds(
            min_oos_observations=4, min_unique_states=4, min_mean_advantage_bps=1, min_win_rate=0.75
        ),
    )
    candidate = boundary.register_candidate(
        {"q": {"state-0": {"EXECUTE": 1.0}}, "n": {"state-0": 20}, "total_observations": 20},
        source_observations=20,
    )
    decision = boundary.evaluate(candidate, _events())
    assert decision.ready is True
    assert decision.evaluation_fingerprint
    policy = boundary.promote(decision)
    assert policy.version == candidate
    assert boundary.active_version == candidate
    assert boundary.active_snapshot()["q"]["state-0"]["EXECUTE"] == 1.0


def test_promotion_never_activates_without_successful_oos_gate(tmp_path):
    boundary = PromotionBoundary(str(tmp_path / "promotion.json"))
    candidate = boundary.register_candidate(
        {"q": {}, "n": {}, "total_observations": 1}, source_observations=1
    )
    decision = boundary.evaluate(candidate, _events(1))
    assert decision.ready is False
    assert boundary.active_version == "baseline-v0"
    try:
        boundary.promote(decision)
    except ValueError as exc:
        assert "candidate_not_promotable" in str(exc)
    else:
        raise AssertionError("promotion unexpectedly succeeded")
