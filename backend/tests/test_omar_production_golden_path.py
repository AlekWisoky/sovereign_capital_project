from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime


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


class _CanonicalLedger:
    def __init__(self, outcome):
        self.outcome = outcome

    def poll(self, *, limit):
        assert limit == 1
        outcome, self.outcome = self.outcome, None
        return [outcome] if outcome is not None else []


class _CapitalLedger:
    def transactions_all(self):
        return [
            {
                "tx_type": "receipt_settlement",
                "receipt_id": "0xflash",
                "transaction_id": "ledger-settlement-1",
                "metadata": {"status": "settled"},
            }
        ]


class _ProductionRuntime:
    _exec_log = [
        {
            "tx_hash": "0xflash",
            "opportunity_id": "opp-flash",
            "route_id": "flash-route",
            "plan": {
                "identity": {
                    "decision_id": "decision-flash",
                    "correlation_id": "corr-flash",
                    "execution_id": "exec-flash",
                }
            },
        }
    ]
    _ledger = _CapitalLedger()

    @staticmethod
    def capital_engine_state():
        return {
            "authority_id": "prime-1",
            "available_wei": 10_000,
            "allocatable_wei": 10_000,
            "status": "healthy",
            "freshness_class": "fresh",
            "source": "capital_engine_state",
        }


def test_flash_arb_success_closes_canonical_ledger_to_omar_policy_update():
    cfg = OmarConfig(
        enabled=True,
        self_play_enabled=False,
        real_outcome_learning_enabled=True,
        real_outcome_batch_size=1,
        policy_checkpoint_enabled=False,
    )
    omar = OmarRuntime(cfg, chain_name="ethereum")
    production = _ProductionRuntime()
    omar.bind_runtime(production)
    omar._trainer = _Trainer()

    omar.observe_decision(
        decision_id="decision-flash",
        correlation_id="corr-flash",
        action="EXECUTE",
        opp_id="opp-flash",
        route_id="flash-route",
        state={"rl_state": "flash-state"},
        metadata={"strategy_family": "flashloan_atomic"},
    )

    outcome = SimpleNamespace(
        tx_hash="0xflash",
        opportunity_id="opp-flash",
        route_id="flash-route",
        ok=True,
        realized_profit_after_gas_wei=1_000,
        realized_profit_after_gas_usd_micro=4_250_000,
        realized_gas_cost_wei=100,
        latency_ms=37,
        rl_action_index=5,
        context={"strategy": "flashloan_atomic"},
    )
    omar._ledger = _CanonicalLedger(outcome)
    omar._learn_real_outcomes()

    call = omar._trainer.policy.calls[0]
    assert call["action_index"] == 5
    assert call["reward_scaled"] == 90_000.0
    assert omar.last_real_learning["eligible_for_learning"] is True
    assert omar.last_real_learning["lineage"] == {
        "decision_id": "decision-flash",
        "correlation_id": "corr-flash",
        "execution_id": "exec-flash",
        "settlement_id": "ledger-settlement-1",
    }
    assert omar.last_real_learning["policy_update"]["updated"] is True


def test_flash_arb_lineage_gap_cannot_update_policy():
    cfg = OmarConfig(enabled=True, self_play_enabled=False, policy_checkpoint_enabled=False)
    omar = OmarRuntime(cfg, chain_name="ethereum")
    omar.bind_runtime(_ProductionRuntime())
    omar._trainer = _Trainer()
    omar.observe_decision(
        decision_id="decision-flash",
        correlation_id="corr-flash",
        action="EXECUTE",
        state={"rl_state": "flash-state"},
    )

    omar._bound_runtime._ledger = SimpleNamespace(transactions_all=lambda: [])
    omar._ledger = _CanonicalLedger(
        SimpleNamespace(
            tx_hash="0xflash",
            opportunity_id="opp-flash",
            route_id="flash-route",
            ok=True,
            realized_profit_after_gas_wei=1_000,
            realized_profit_after_gas_usd_micro=4_250_000,
            realized_gas_cost_wei=100,
            latency_ms=37,
            rl_action_index=5,
            context={},
        )
    )

    omar._learn_real_outcomes()

    assert omar._trainer.policy.calls == []
    assert omar.last_real_learning["eligible_for_learning"] is False
    assert "missing_settlement_id" in omar.last_real_learning["reason_codes"]
