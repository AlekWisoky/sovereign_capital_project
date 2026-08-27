from victor_ai_bot.omar.real_learning import OmarRealLearner


def test_prime_economics_change_learning_state_but_prime_id_does_not():
    base = {
        "margin_ratio": 0.001,
        "gas_ratio": 0.0005,
        "p_success": 0.85,
        "drawdown_pct": 1.0,
        "execution_realism": 0.9,
        "stability": 0.9,
        "goal_gap_pct": 1.0,
        "volatility": 0.1,
        "legs": 2,
        "capital_source": "internal_prime",
        "internal_prime_available": True,
        "prime_capacity_ratio": 0.8,
        "prime_cost_bps": 4.0,
        "internal_prime_id": "prime-A",
        "correlation_id": "corr-A",
    }
    same_economics = {**base, "internal_prime_id": "prime-B", "correlation_id": "corr-B"}
    expensive_prime = {**base, "prime_cost_bps": 20.0}

    assert OmarRealLearner.state_key(base) == OmarRealLearner.state_key(same_economics)
    assert OmarRealLearner.state_key(base) != OmarRealLearner.state_key(expensive_prime)


def test_outcome_lineage_preserves_decision_and_transaction_identity(tmp_path):
    learner = OmarRealLearner(path=str(tmp_path / "policy.json"), min_observations=1)
    result = learner.observe(
        state_key="state",
        action="EXECUTE",
        reward=1.0,
        outcome={"decision_id": "decision-1", "correlation_id": "corr-1", "tx_hash": "0xabc"},
    )

    assert result["ok"] is True
    events = (tmp_path / "policy.json.jsonl").read_text(encoding="utf-8")
    assert "decision-1" in events
    assert "corr-1" in events
    assert "0xabc" in events
