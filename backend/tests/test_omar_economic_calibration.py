from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.trainer import OmarTrainer


def test_omar_real_learning_penalizes_only_negative_expectation_error():
    trainer = OmarTrainer(OmarConfig(enabled=True, self_play_enabled=False), checkpoint_path=None)

    underperforming = SimpleNamespace(
        amount_in_wei=1000,
        expected_profit_after_costs_wei=1000,
        realized_profit_after_gas_wei=500,
        reward_scaled_float=500000.0,
        latency_ms=180.0,
        context={"brain": {"economic_context": {"expected_latency_ms": 100.0}}},
    )
    outperforming = SimpleNamespace(
        amount_in_wei=1000,
        expected_profit_after_costs_wei=1000,
        realized_profit_after_gas_wei=1500,
        reward_scaled_float=1500000.0,
        latency_ms=80.0,
        context={"brain": {"economic_context": {"expected_latency_ms": 100.0}}},
    )

    under_reward, under_pct, under_latency, under_error = trainer._real_learning_reward(underperforming)
    over_reward, over_pct, over_latency, over_error = trainer._real_learning_reward(outperforming)

    assert under_error == -500
    assert under_pct == -50.0
    assert under_latency == 80.0
    assert under_reward < 500000.0

    assert over_error == 500
    assert over_pct == 50.0
    assert over_latency == -20.0
    assert over_reward == 1500000.0
