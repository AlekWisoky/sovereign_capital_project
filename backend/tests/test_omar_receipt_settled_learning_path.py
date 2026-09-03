from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace

from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.learning.outcome_ledger import CanonicalOutcomeLedger
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.treasury.ledger import TreasuryLedger


class _Policy:
    def __init__(self):
        self.calls = []

    def update_from_real_outcome(self, **kwargs):
        self.calls.append(kwargs)
        return {"updated": 1.0, "reward_scaled": kwargs["reward_scaled"]}


class _Trainer:
    def __init__(self):
        self.policy = _Policy()
        self._role_embeds = {"ARBITRAGE_AGENT": [0.0] * 64}
        self.cfg = SimpleNamespace(
            role_vector_size=64,
            learning_rate=3e-4,
            clip_epsilon=0.2,
            policy_checkpoint_enabled=False,
        )
        self.state_dim = 96

    @staticmethod
    def _state_vector(_state_key, dim):
        return [0.0] * dim


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = ""
    profit_to = "0x1111111111111111111111111111111111111111"
    withdraw_mode = "txdata"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _BankrollState:
    realized_profit_wei = 0
    last_amount_in_wei = 1000


class _BankrollCfg:
    auto_reinvest_enabled = False
    reinvest_rate_pct = 0.0


class _Bankroll:
    state = _BankrollState()
    cfg = _BankrollCfg()


class _Runtime:
    cfg = _Cfg()
    _bankroll = _Bankroll()
    _exec_log = [
        {
            "tx_hash": "0xomar",
            "opportunity_id": "opp-omar",
            "route_id": "route-omar",
            "plan": {
                "identity": {
                    "decision_id": "decision-omar",
                    "correlation_id": "corr-omar",
                    "execution_id": "exec-omar",
                }
            },
        }
    ]

    def __init__(self, tmp_path):
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._ledger_repo = LedgerRepository(self._db)
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain="ethereum")
        self._pnl = PnLStore(str(tmp_path / "pnl_ethereum.sqlite"))
        self._cc = SimpleNamespace(audit=AuditStore(str(tmp_path / "cc_audit.jsonl")))

    def treasury_state(self):
        return {"enabled": True}

    def capital_engine_state(self):
        return {
            "authority_id": "prime-omar",
            "available_wei": 10_000,
            "allocatable_wei": 10_000,
            "status": "healthy",
            "freshness_class": "fresh",
            "source": "capital_engine_state",
        }

    def internal_prime_state(self):
        return {"capacityUsd": 1_000_000.0, "utilization": 0.0}

    def launch_state(self):
        return {}


def _seed_trade(runtime: _Runtime) -> None:
    async def _seed() -> None:
        await runtime._pnl.init()
        trade_id = await runtime._pnl.add_trade(
            {
                "ts": 1,
                "chain": "ethereum",
                "opportunity_id": "opp-omar",
                "route_id": "route-omar",
                "tx_hash": "0xomar",
                "mode": "auto",
                "dry_run": False,
                "ok": True,
                "reason": "submitted",
                "expected_gross_profit_wei": "1100",
                "expected_profit_after_costs_wei": "900",
                "estimated_gas_cost_wei": "100",
                "flashloan_fee_wei": "1",
                "gas_limit": 21000,
                "max_fee_wei": "1",
                "priority_fee_wei": "1",
                "strategy_type": "flash_arb",
                "income_stream": "arb",
                "venue_path": "uniswap",
            }
        )
        con = sqlite3.connect(runtime._pnl.path)
        try:
            con.execute(
                "UPDATE trades SET receipt_status=?, realized_gas_cost_wei=?, realized_profit_after_gas_wei=?, realized_profit_token=?, realized_profit_token_wei=?, realized_profit_after_gas_usd_micro=? WHERE id=?",
                (1, "100", "1000", "USDC", "1100", "4250000", int(trade_id)),
            )
            con.commit()
        finally:
            con.close()

    asyncio.run(_seed())


def test_receipt_to_settled_ledger_to_omar_policy_update(tmp_path):
    runtime = _Runtime(tmp_path)
    _seed_trade(runtime)

    receipt_result = ReceiptService().synchronize_settlement_accounting(
        runtime,
        tx_hash="0xomar",
        pending={"strategy_family": "flash_arb", "route_family": "flash_arb"},
        decoded={
            "realized_profit_after_gas_wei": "1000",
            "realized_profit_token": "USDC",
            "realized_profit_token_wei": "1100",
            "realized_profit_after_gas_usd_micro": "4250000",
        },
        status=1,
        amount_in=1000,
        expected_after=900,
        realized_after=1000,
        submit_to_receipt_ms=37,
        route_id="route-omar",
        route_family="flash_arb",
        strategy_family="flash_arb",
        capture_lane_pending="private",
        outcome_truth_verified=True,
        outcome_truth_reason_code="ok",
    )

    assert receipt_result["ok"] is True
    assert runtime._ledger_repo.has_receipt_transaction(
        chain="ethereum", receipt_id="0xomar", tx_type="receipt_settlement"
    )
    settlement = runtime._ledger.transactions_tail(limit=10)[-1]
    assert settlement["receipt_id"] == "0xomar"
    assert settlement["tx_type"] == "receipt_settlement"

    omar = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_outcome_learning_enabled=True,
            real_outcome_batch_size=1,
            policy_checkpoint_enabled=False,
        ),
        chain_name="ethereum",
    )
    omar.bind_runtime(runtime)
    omar._trainer = _Trainer()
    omar.observe_decision(
        decision_id="decision-omar",
        correlation_id="corr-omar",
        action="EXECUTE",
        opp_id="opp-omar",
        route_id="route-omar",
        policy_version="policy-test-v1",
        state={"rl_state": "flash-state"},
    )
    omar._ledger = CanonicalOutcomeLedger(
        data_dir=str(tmp_path), chain="ethereum", bootstrap_history=1
    )

    omar._learn_real_outcomes()

    assert omar.last_real_learning["eligible_for_learning"] is True
    assert omar.last_real_learning["lineage"] == {
        "decision_id": "decision-omar",
        "correlation_id": "corr-omar",
        "execution_id": "exec-omar",
        "settlement_id": settlement["transaction_id"],
    }
    assert omar.last_real_learning["policy_update"]["updated"] is True
    assert omar._trainer.policy.calls[0]["action_index"] == 5
    assert omar._trainer.policy.calls[0]["reward_scaled"] == 100_000.0
