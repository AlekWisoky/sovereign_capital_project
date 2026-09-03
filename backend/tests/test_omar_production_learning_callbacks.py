from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.omar.production_learning_hook import install_production_learning_hooks
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


def test_production_learning_hooks_are_installed_once():
    install_production_learning_hooks()
    assert getattr(RuntimeDecisionFacade._apply_omar_to_candidate, "_omar_real_learning_hook", False)
    assert getattr(ExecutionService.handle_post_execute_bookkeeping, "_omar_real_learning_hook", False)
    assert getattr(RuntimeReceiptFacade._safe_finalize_receipt_side_effects, "_omar_real_learning_hook", False)


def test_omar_consumes_canonical_settled_ledger_and_updates_policy(tmp_path):
    omar = OmarRuntime(OmarConfig(enabled=True, self_play_enabled=False), chain_name="ethereum")
    runtime = SimpleNamespace(
        capital_engine_state=lambda: {
            "authority_id": "capital-authority-1",
            "available_wei": 10_000,
            "allocatable_wei": 7_500,
            "family_allocatable_wei": {"flashloan_atomic": 5_000},
            "status": "authorized",
            "freshness_class": "fresh",
            "source": "capital_engine_state",
        }
    )
    omar.bind_runtime(runtime)

    class _Policy:
        def __init__(self):
            self.calls = []

        def update_from_real_outcome(self, **kwargs):
            self.calls.append(kwargs)
            return {"updated": 1.0, "reward_scaled": kwargs["reward_scaled"]}

        def save(self):
            return True

    policy = _Policy()
    omar._trainer = SimpleNamespace(
        _role_embeds={"ARBITRAGE_AGENT": object()},
        cfg=SimpleNamespace(
            learning_rate=3e-4,
            clip_epsilon=0.2,
            role_vector_size=64,
            policy_checkpoint_enabled=False,
        ),
        state_dim=96,
        _state_vector=lambda rl_state, state_dim: object(),
        policy=policy,
    )
    omar.omar_dir = str(tmp_path)

    row = {
        "transaction_id": "ledger-1",
        "receipt_id": "0xtest",
        "status": "settled",
        "lineage": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "execution_id": "execution-1",
            "settlement_id": "settlement-1",
            "action": "EXECUTE",
            "opportunity_id": "opp-1",
            "route_id": "route-1",
        },
        "metadata": {
            "state": {"rl_state": "state-1"},
            "realized_profit_after_gas_wei": 1_000,
            "gas_cost_wei": 100,
            "risk_cost_wei": 50,
            "truth_verified": True,
            "latency_ms": 37,
        },
    }

    result = omar.observe_settled_ledger_record(row)

    assert result["ok"] is True
    assert result["eligible_for_learning"] is True
    assert result["lineage"]["decision_id"] == "decision-1"
    assert result["lineage"]["correlation_id"] == "corr-1"
    assert result["lineage"]["execution_id"] == "execution-1"
    assert result["lineage"]["settlement_id"] == "settlement-1"
    assert result["attribution"]["action"] == "EXECUTE"
    assert result["policy_update"]["updated"] is True
    assert len(policy.calls) == 1
    assert omar._real_learning._decisions["decision-1"].capital_authority.source == "capital_engine_state"
