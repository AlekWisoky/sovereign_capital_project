from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.learning.net_economics import resolve_net_economics
from victor_ai_bot.learning.outcome_ledger import CanonicalOutcomeLedger
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.trainer import DEFAULT_ACTION_KEYS, OmarTrainer


def _outcome(*, ok: bool = True, latency_ms: int = 100, action_index: int = 5):
    return SimpleNamespace(
        rl_state="margin_mid|gas_low|p_high",
        rl_action_index=action_index,
        tx_hash="0xnetcost",
        ok=ok,
        realized_profit_usd_micro=10_000_000,
        realized_gas_cost_usd_micro=1_000_000,
        realized_profit_after_gas_usd_micro=9_000_000,
        latency_ms=latency_ms,
        context={
            "brain": {"role": "ARBITRAGE_AGENT"},
            "borrowing": {"realized_cost_usd": 2.0},
            "costs": {
                "slippage_cost_usd": 0.50,
                "execution_fee_usd": 0.25,
            },
        },
    )


def test_net_profit_after_costs_subtracts_realized_cost_components():
    economics = resolve_net_economics(_outcome())

    assert economics.gross_profit_usd == pytest.approx(10.0)
    assert economics.gas_cost_usd == pytest.approx(1.0)
    assert economics.financing_cost_usd == pytest.approx(2.0)
    assert economics.slippage_cost_usd == pytest.approx(0.50)
    assert economics.execution_cost_usd == pytest.approx(0.25)
    assert economics.net_profit_after_costs_usd == pytest.approx(6.25)
    assert economics.complete is True


def test_explicit_settled_net_pnl_is_authoritative():
    outcome = _outcome()
    outcome.context["settled_economics"] = {"signed_pnl_usd": 4.75}

    economics = resolve_net_economics(outcome)

    assert economics.net_profit_after_costs_usd == pytest.approx(4.75)
    assert economics.source == "settled_authoritative"


def test_failed_settlement_counts_realized_gas_as_loss():
    outcome = _outcome(ok=False)
    outcome.realized_profit_usd_micro = 0
    outcome.realized_profit_after_gas_usd_micro = 0

    economics = resolve_net_economics(outcome)

    assert economics.net_profit_after_costs_usd == pytest.approx(-3.75)
    assert economics.learning_reward < 0.0


def test_lower_latency_gets_higher_learning_reward_without_changing_pnl():
    fast = resolve_net_economics(_outcome(latency_ms=100))
    slow = resolve_net_economics(_outcome(latency_ms=900))

    assert fast.net_profit_after_costs_usd == pytest.approx(slow.net_profit_after_costs_usd)
    assert fast.latency_quality > slow.latency_quality
    assert fast.learning_reward > slow.learning_reward


def test_latency_is_not_treated_as_a_financial_cost():
    fast = resolve_net_economics(_outcome(latency_ms=10))
    slow = resolve_net_economics(_outcome(latency_ms=10_000))

    assert fast.net_profit_after_costs_usd == pytest.approx(6.25)
    assert slow.net_profit_after_costs_usd == pytest.approx(6.25)


def test_trainer_uses_exact_recorded_action_and_net_after_costs():
    trainer = OmarTrainer(OmarConfig(self_play_episodes=1, policy_checkpoint_enabled=False))
    outcome = _outcome(action_index=DEFAULT_ACTION_KEYS.index("EXECUTE"))

    before = trainer.policy.updates
    stats = trainer.learn_from_real_outcomes([outcome])

    assert stats["seen"] == 1
    assert stats["learned"] == 1
    assert stats["skipped"] == 0
    assert stats["mean_net_profit_after_costs_usd"] == pytest.approx(6.25)
    assert stats["mean_latency_quality"] > 0.0
    assert trainer.policy.updates > before


def test_safety_reserve_is_not_double_counted_as_realized_cost():
    outcome = _outcome()
    outcome.context["capital"] = {"safety_reserve_usd": 999.0}

    economics = resolve_net_economics(outcome)

    assert economics.net_profit_after_costs_usd == pytest.approx(6.25)


def test_canonical_ledger_carries_net_profit_and_latency_truth(tmp_path):
    ledger = CanonicalOutcomeLedger(data_dir=str(tmp_path), chain="test")
    row = {
        "id": 7,
        "ts": 1,
        "chain": "test",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "tx_hash": "0xnetcost",
        "mode": "auto",
        "receipt_status": 1,
        "expected_profit_after_costs_wei": 100,
        "estimated_gas_cost_wei": 10,
        "flashloan_fee_wei": 5,
        "realized_gas_cost_wei": 10,
        "realized_profit_after_gas_wei": 900,
        "realized_profit_token": "USDC",
        "realized_profit_token_wei": 900,
        "realized_gas_cost_in_profit_token_wei": 10,
        "realized_profit_usd_micro": 10_000_000,
        "realized_gas_cost_usd_micro": 1_000_000,
        "realized_profit_after_gas_usd_micro": 9_000_000,
        "strategy_type": "arbitrage",
        "income_stream": "arb",
        "venue_path": "a>b",
    }
    training = {
        "ts": 1,
        "tx_hash": "0xnetcost",
        "amount_in_wei": "1000",
        "rl_state": "margin_mid|gas_low|p_high",
        "rl_action_index": DEFAULT_ACTION_KEYS.index("EXECUTE"),
        "extra": {
            "latency_ms": 100,
            "brain": {"role": "ARBITRAGE_AGENT"},
            "borrowing": {"realized_cost_usd": 2.0},
            "costs": {"slippage_cost_usd": 0.50, "execution_fee_usd": 0.25},
        },
    }

    outcome = ledger._normalize(row, training)

    assert outcome.net_profit_after_costs_usd_micro == 6_250_000
    assert outcome.learning_reward > 0.0
    assert outcome.latency_quality > 0.0
    assert outcome.to_dict()["netProfitAfterCostsUsdMicro"] == "6250000"
    assert outcome.to_dict()["context"]["netEconomics"]["source"] == "derived_from_settled_components"
