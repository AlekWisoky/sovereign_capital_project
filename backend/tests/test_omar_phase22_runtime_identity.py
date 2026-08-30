from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import (
    _observe_settled_outcome,
    install_omar_lifecycle_hooks,
)
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    canonical_settled_outcome,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade


class AllowingExecutionService(ExecutionService):
    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {})

    def auto_trade_family_gate(self, runtime, opp):
        return ExecutionGateResult(True, "ok", {})

    def auto_trade_execution_realism_gate(self, opp, decision, runtime=None):
        return opp, ExecutionGateResult(True, "ok", {})

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        return ExecutionGateResult(True, "ok", {})

    def auto_trade_treasury_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {})


class Rpc:
    def __init__(self, url, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class LedgerRepo:
    def __init__(self):
        self.rows = []

    def all_transactions(self, *, chain):
        return [row for row in self.rows if row.get("chain") == chain]


class Telemetry:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload, *, chain):
        self.events.append((event_type, dict(payload), str(chain)))


def runtime(tmp_path: Path):
    omar = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_learning_enabled=True,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    omar.data_dir = str(tmp_path)
    omar.learning_path = str(tmp_path / "policy.json")
    omar._learning_cursor_path = str(tmp_path / "cursor.json")
    omar._seen_outcome_ids = set()
    rt = object.__new__(RuntimeBundle)
    rt.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(dry_run=False, gas_mode="standard", send_mode="public"),
    )
    rt.metrics = SimpleNamespace(gas_mode="standard", send_mode="public", last_submitted_block=17)
    rt.rpc_manager = SimpleNamespace(
        best_read=lambda: "read",
        best_send=lambda: "send",
        best_private=lambda: "private",
    )
    rt._execution_service = AllowingExecutionService()
    rt._omar = omar
    rt._cc = SimpleNamespace(
        controls=SimpleNamespace(aggression_mode="balanced", risk_multiplier=0.7)
    )
    rt._wealth_goal_service = None
    rt._ai_recommendation = {
        "action": "WAIT",
        "posture": "protect_capital",
        "confidence": 0.9,
    }
    rt._market_regime = {"volatility": 0.1}
    rt._last_submitted_block = 17
    rt._mev_guard = None
    rt.cache = None
    rt._lat = None
    rt._fioa = None
    rt._super = None
    rt._consensus = None
    rt._gov = None
    rt._pending = {}
    rt._exec_log = []
    rt._pending_gas_est_wei = 0
    rt._receipt_q = None
    rt.capital_engine_state = lambda: {
        "capital_engine": {
            "available_bankroll_wei": 9000,
            "deployable_bankroll_wei": 5000,
            "family_allocations_wei": {"flash_arb": 5000},
            "status": "authorized",
            "freshness_class": "fresh",
            "authority_id": "authority-phase22",
            "source": "capital-engine",
            "internal_prime_available": True,
            "prime_capacity_ratio": 0.8,
            "prime_cost_bps": 4.0,
        }
    }
    return rt, omar


@pytest.mark.asyncio
async def test_phase22_one_canonical_decision_id_survives_production_lifecycle(monkeypatch, tmp_path):
    """Verify one canonical decision ID is invariant across the production-shaped chain."""
    install_canonical_settlement_interface()
    install_production_lineage_bridge()
    install_omar_lifecycle_hooks()
    rt, omar = runtime(tmp_path)
    telemetry = Telemetry()
    repo = LedgerRepo()
    rt._ledger_repo = repo
    rt._telemetry_service = telemetry

    async def fake_execute(*args, **kwargs):
        return SimpleNamespace(
            ok=True,
            dry_run=False,
            submitted=True,
            tx_hash="0xphase22",
            plan={"latency_stages_ms": {"total": 8.0}},
        )

    monkeypatch.setattr(
        runtime_execute_wrapper_facade,
        "_compat_execution_wrapper_symbols",
        lambda: (Rpc, fake_execute),
    )

    async def record_exec(result, opp, *, latency_ms, mode):
        rt._exec_log.append(
            {"result": result, "opp": opp, "latency_ms": latency_ms, "mode": mode}
        )

    rt._record_exec = record_exec

    opp = SimpleNamespace(
        id="opp-phase22",
        route_id="route-phase22",
        can_execute=True,
        expected_profit_raw="1000000000000000",
        meta={"brain": {}, "safety": {"exec_ready": True, "profit_after_costs_wei": "10"}},
    )
    rt._opps = [opp]
    rt._auto_trading = True
    rt._cb = SimpleNamespace(allow_auto_trading=lambda: True)
    rt._exec_task = None

    # 1) Production decision boundary creates the identity and OMAR observes it.
    chosen, decision = rt._apply_omar_to_candidate(opp, None, current_block=222)
    assert chosen is opp
    canonical_id = decision.metadata["canonical_decision_id"]
    correlation_id = decision.metadata["correlation_id"]
    assert canonical_id == lineage_from_opportunity(opp)["decision_id"]
    assert correlation_id == lineage_from_opportunity(opp)["correlation_id"]
    assert omar._pending_decisions[canonical_id]["decision_id"] == canonical_id
    assert omar._pending_decisions[canonical_id]["context"]["capital_authority_source"] == "capital_engine_state"

    # 2) Production RuntimeBundle auto execution reaches the real wrapper seam.
    await rt._execute_auto(opp, 222, decision=decision)
    result = rt._exec_log[0]["result"]
    assert result.plan["canonical_decision_id"] == canonical_id
    assert result.plan["canonical_lineage"]["decision_id"] == canonical_id
    assert result.plan["correlation_id"] == correlation_id

    # 3) Canonical Phase 2 settlement is the only accepted outcome source.
    execution_id = result.plan.get("execution_id") or f"execution:{canonical_id}"
    outcome_id = f"outcome:{canonical_id}"
    repo.rows.append(
        {
            "transaction_id": "settlement-phase22",
            "tx_type": "receipt_settlement",
            "chain": "ethereum",
            "receipt_id": "0xphase22",
            "ts_ms": 222,
            "metadata": {
                "canonical_lineage": {
                    "decision_id": canonical_id,
                    "correlation_id": correlation_id,
                    "execution_id": execution_id,
                    "outcome_id": outcome_id,
                },
                "canonical_decision_id": canonical_id,
                "correlation_id": correlation_id,
                "opportunity_id": opp.id,
                "route_id": opp.route_id,
                "execution_id": execution_id,
                "outcome_id": outcome_id,
                "ok": True,
                "expected_net_usd": 4.0,
                "realized_net_usd": 7.0,
                "amount_in_wei": 100,
                "gas_cost_usd": 0.2,
                "slippage_bps": 3.0,
                "latency_ms": 8,
                "truth_verified": True,
            },
        }
    )

    settled = canonical_settled_outcome(
        rt,
        tx_hash="0xphase22",
        decision_id=canonical_id,
        correlation_id=correlation_id,
        opportunity_id=opp.id,
    )
    assert settled is not None
    assert settled["decision_id"] == canonical_id
    assert settled["correlation_id"] == correlation_id
    assert settled["execution_id"] == execution_id
    assert settled["outcome_id"] == outcome_id
    assert settled["lineage_complete"] is True

    # 4) Lineage resolution -> OMAR outcome -> real policy update.
    pending = omar._pending_decisions[canonical_id]
    observed = _observe_settled_outcome(rt, pending=pending, outcome=settled)
    assert observed["ok"] is True
    assert observed["canonical_decision_id"] == canonical_id
    assert observed["oos_evidence"]["lineage"]["decision_id"] == canonical_id
    assert observed["oos_evidence"]["lineage"]["correlation_id"] == correlation_id
    assert observed["oos_evidence"]["lineage"]["execution_id"] == execution_id
    assert observed["oos_evidence"]["lineage"]["outcome_id"] == outcome_id
    assert omar._real_learner.total_observations == 1
    assert omar._real_learner.q[pending["state_key"]][pending["action"]] != 0.0

    learning = [e for e in telemetry.events if e[0] == "omar_learning_update"]
    assert len(learning) == 1
    assert learning[0][1]["decision_id"] == canonical_id
    assert learning[0][1]["correlation_id"] == correlation_id

    # 5) A cross-trade settlement cannot be attributed to this decision.
    cross = canonical_settled_outcome(
        rt,
        tx_hash="0xdifferent",
        decision_id="different-decision",
        correlation_id=correlation_id,
        opportunity_id=opp.id,
    )
    assert cross is None
