from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.trainer import OmarTrainer
from victor_ai_bot.learning.borrowing_truth import BorrowingTruth


def _outcome(*, settled: float, action: int = 5):
    return SimpleNamespace(
        rl_state="state-1",
        rl_action_index=action,
        reward_scaled_float=2500.0,
        ok=True,
        tx_hash="0xabc",
        context={"brain": {"role": "ARBITRAGE_AGENT"}},
        borrowing=BorrowingTruth(
            requested_usd=10_000.0,
            authorized_usd=10_000.0,
            deployed_usd=10_000.0,
            settled_usd=settled,
            realized_cost_usd=5.0,
            capacity_usd=100_000.0,
            utilization=0.2,
            source="internal_prime_loan",
            status="settled" if settled else "deployed",
            reason_code="borrowing_settled" if settled else "borrowing_deployed",
            loan_id="loan-1",
        ),
    )


def test_borrowing_state_features_are_visible_to_policy():
    trainer = OmarTrainer(OmarConfig(self_play_episodes=1))
    state = trainer._state_vector(
        "state-1",
        trainer.state_dim,
        BorrowingTruth(
            requested_usd=20.0,
            authorized_usd=20.0,
            deployed_usd=10.0,
            settled_usd=10.0,
            realized_cost_usd=2.0,
            capacity_usd=100.0,
            utilization=0.4,
            source="internal_prime_loan",
            status="settled",
            reason_code="borrowing_settled",
            loan_id="loan-1",
        ),
    )

    assert state.shape == (trainer.state_dim,)
    np.testing.assert_allclose(state[:6], [0.2, 1.0, 0.5, 0.5, 0.1, 0.4], atol=1e-6)


def test_borrowing_trade_does_not_update_policy_before_settlement():
    trainer = OmarTrainer(OmarConfig(self_play_episodes=1))
    before = int(trainer.policy.updates)

    stats = trainer.learn_from_real_outcomes([_outcome(settled=0.0)])

    assert stats["seen"] == 1
    assert stats["learned"] == 0
    assert stats["borrowing_unresolved"] == 1
    assert int(trainer.policy.updates) == before


def test_settled_borrowing_trade_uses_exact_recorded_action():
    trainer = OmarTrainer(OmarConfig(self_play_episodes=1))

    stats = trainer.learn_from_real_outcomes([_outcome(settled=10_000.0, action=2)])

    assert stats["seen"] == 1
    assert stats["learned"] == 1
    assert stats["borrowing_settled"] == 1
    assert int(trainer.policy.updates) > 0
