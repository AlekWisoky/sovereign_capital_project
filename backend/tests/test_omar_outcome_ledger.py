import json
import sqlite3

from victor_ai_bot.learning.outcome_ledger import CanonicalOutcomeLedger
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.trainer import OmarTrainer


def _make_db(path):
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY,
            ts INTEGER,
            chain TEXT,
            opportunity_id TEXT,
            route_id TEXT,
            tx_hash TEXT,
            mode TEXT,
            receipt_status INTEGER,
            expected_profit_after_costs_wei TEXT,
            estimated_gas_cost_wei TEXT,
            flashloan_fee_wei TEXT,
            realized_gas_cost_wei TEXT,
            realized_profit_after_gas_wei TEXT,
            realized_profit_token TEXT,
            realized_profit_token_wei TEXT,
            realized_gas_cost_in_profit_token_wei TEXT,
            realized_profit_usd_micro TEXT,
            realized_gas_cost_usd_micro TEXT,
            realized_profit_after_gas_usd_micro TEXT,
            strategy_type TEXT,
            income_stream TEXT,
            venue_path TEXT
        )
        """
    )
    con.execute(
        """
        INSERT INTO trades VALUES
        (1, 100, 'arbitrum', 'opp-1', 'route-1', '0xabc', 'auto', 1,
         '100', '20', '5', '10', '90', 'WETH', '100', '10', '90', '10', '80',
         'flashloan_atomic', 'arbitrage', 'dex-a->dex-b')
        """
    )
    con.commit()
    con.close()


def test_canonical_outcome_ledger_joins_real_outcome_to_learning_context(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _make_db(data_dir / "pnl_arbitrum.sqlite")

    training_dir = data_dir / "training"
    training_dir.mkdir()
    with (training_dir / "rl_training_arbitrum.jsonl").open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": 101,
                    "chain": "arbitrum",
                    "tx_hash": "0xabc",
                    "amount_in_wei": "1000",
                    "rl_state": "m_mid|g_low|p_uni|l2",
                    "rl_action_index": 3,
                    "extra": {
                        "strategy": "arbitrage",
                        "brain": {"borrow_mult": 1.0},
                    },
                }
            )
            + "\n"
        )

    ledger = CanonicalOutcomeLedger(data_dir=str(data_dir), chain="arbitrum")
    outcomes = ledger.poll(limit=10)

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.tx_hash == "0xabc"
    assert outcome.ok is True
    assert outcome.amount_in_wei == 1000
    assert outcome.realized_profit_after_gas_wei == 90
    assert outcome.rl_state == "m_mid|g_low|p_uni|l2"
    assert outcome.rl_action_index == 3
    assert outcome.reward_scaled_ppm == 90000
    assert ledger.poll(limit=10) == []


def test_omar_real_outcome_learning_persists_policy(tmp_path):
    cfg = OmarConfig(
        enabled=True,
        self_play_enabled=False,
        real_outcome_learning_enabled=True,
        policy_checkpoint_enabled=True,
        roles=["ARBITRAGE_AGENT"],
    )
    checkpoint = tmp_path / "omar" / "policy.json"
    trainer = OmarTrainer(cfg, checkpoint_path=str(checkpoint))

    class Outcome:
        ok = True
        rl_state = "m_mid|g_low|p_uni|l2"
        reward_scaled_float = 25.0
        tx_hash = "0xabc"
        context = {"brain": {"borrow_mult": 1.0}}

    result = trainer.learn_from_real_outcomes([Outcome()])

    assert result["seen"] == 1
    assert result["learned"] == 1
    assert trainer.policy.updates == 1
    assert checkpoint.exists()

    restored = OmarTrainer(cfg, checkpoint_path=str(checkpoint))
    assert restored.policy.updates == 1
