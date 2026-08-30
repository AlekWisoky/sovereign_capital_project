from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_interface,
)


class _LedgerRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def all_transactions(self, *, chain: str):
        return [row for row in self.rows if row.get("chain") == chain]


class _Telemetry:
    def __init__(self):
        self.events = []

    def record(self, event_type, payload, *, chain):
        self.events.append((event_type, dict(payload), str(chain)))


def _runtime(tmp_path: Path):
    omar = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_learning_enabled=True,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    omar.learning_path = str(tmp_path / "real_policy.json")
    omar._learning_cursor_path = str(tmp_path / "cursor.json")
    omar._seen_outcome_ids = set()
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=omar,
        _ledger_repo=_LedgerRepo(),
        _telemetry_service=_Telemetry(),
    )
    return runtime, omar


def test_canonical_decision_execution_settlement_propagates_once(tmp_path):
    """One production-shaped settlement trains OMAR exactly once with frozen context."""
    install_canonical_settlement_interface()
    runtime, omar = _runtime(tmp_path)

    decision_id = "decision-canonical-1"
    correlation_id = "corr-canonical-1"
    execution_id = "execution-canonical-1"
    opportunity_id = "opp-canonical-1"
    tx_hash = "0xcanonical-1"
    outcome_id = "outcome-canonical-1"

    context = {
        "operator_intent": {
            "aggression_mode": "aggressive",
            "risk_multiplier": 0.75,
            "goal": {
                "target_amount": "100000",
                "timeframe_days": 90,
                "goal_revision": 3,
            },
            "ai_recommendation": {
                "action": "WAIT",
                "posture": "protect_capital",
                "confidence": 0.91,
            },
        },
        "capital_authority_source": "capital_engine_state",
        "capital_available_wei": 9000,
        "capital_allocatable_wei": 5000,
        "capital_authority_status": "authorized",
        "capital_authority_freshness": "fresh",
        "internal_prime_available": True,
        "prime_capacity_ratio": 0.8,
        "prime_cost_bps": 4.0,
    }
    omar.observe_decision(
        decision_id=decision_id,
        opportunity_id=opportunity_id,
        route_id="route-canonical-1",
        action="EXECUTE",
        state_key="canonical-state-1",
        context=context,
        metadata={
            "canonical_lineage": {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
                "execution_id": execution_id,
            }
        },
    )

    # Prove decision-time context is immutable evidence.
    context["operator_intent"]["goal"]["target_amount"] = "999999"
    context["operator_intent"]["ai_recommendation"]["action"] = "EXECUTE"
    context["capital_allocatable_wei"] = 1

    pending = {
        "canonical_decision_id": decision_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "opportunity_id": opportunity_id,
        "route_id": "route-canonical-1",
        "context": omar._pending_decisions[decision_id]["context"],
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "execution_id": execution_id,
        },
    }

    runtime._ledger_repo.rows.append(
        {
            "transaction_id": "settlement-ledger-1",
            "ts_ms": 100,
            "tx_type": "receipt_settlement",
            "chain": "ethereum",
            "receipt_id": tx_hash,
            "metadata": {
                "tx_hash": tx_hash,
                "canonical_lineage": {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                    "execution_id": execution_id,
                },
                "outcome_id": outcome_id,
                "opportunity_id": opportunity_id,
                "route_id": "route-canonical-1",
                "ok": True,
                "expected_net_usd": 4.0,
                "realized_net_usd": 7.0,
                "amount_in_wei": 100,
                "gas_cost_usd": 0.2,
                "slippage_bps": 3.0,
                "latency_ms": 80,
                "truth_verified": True,
            },
        }
    )

    settled = runtime._ledger_repo.rows[0]
    from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome

    canonical = canonical_settled_outcome(
        runtime,
        tx_hash=tx_hash,
        decision_id=decision_id,
        correlation_id=correlation_id,
        opportunity_id=opportunity_id,
    )
    assert canonical is not None
    assert canonical["status"] == "settled"
    assert canonical["decision_id"] == decision_id
    assert canonical["correlation_id"] == correlation_id
    assert canonical["execution_id"] == execution_id
    assert canonical["outcome_id"] == outcome_id
    assert canonical["lineage_complete"] is True

    first = _observe_settled_outcome(runtime, pending=pending, outcome=canonical)
    assert first["ok"] is True
    assert first["execution_id"] == execution_id
    assert first["outcome_id"] == outcome_id
    assert omar._real_learner.total_observations == 1
    assert omar._real_learner.q["canonical-state-1"]["EXECUTE"] != 0.0

    # The same canonical settlement is replayed: it must not produce a second
    # policy update, even if the lifecycle bridge invokes the learner twice.
    duplicate = omar.observe_outcome(
        decision_id=decision_id,
        execution_id=execution_id,
        outcome_id=outcome_id,
        settlement_status="settled",
        ok=True,
        realized_net_usd=7.0,
        expected_net_usd=4.0,
        amount_in_wei=100,
        gas_cost_usd=0.2,
        slippage_bps=3.0,
        latency_ms=80,
        route_id="route-canonical-1",
        tx_hash=tx_hash,
        outcome_truth_verified=True,
        metadata={"canonical_lineage": {"decision_id": decision_id, "correlation_id": correlation_id}},
    )
    assert duplicate["reason"] == "duplicate_canonical_settlement"
    assert omar._real_learner.total_observations == 1

    # An unsettled observation is rejected before the learner is touched.
    unsettled = omar.observe_outcome(
        decision_id="decision-unsettled",
        execution_id="execution-unsettled",
        outcome_id="outcome-unsettled",
        settlement_status="pending",
        ok=True,
        realized_net_usd=99.0,
        expected_net_usd=1.0,
        amount_in_wei=100,
        tx_hash="0xpending",
    )
    assert unsettled["reason"] == "outcome_not_settled"
    assert omar._real_learner.total_observations == 1

    # The frozen snapshot still contains the original operator/goal/AI/capital
    # values that existed when the decision was recorded.
    assert pending["context"]["operator_intent"]["goal"]["target_amount"] == "100000"
    assert pending["context"]["operator_intent"]["ai_recommendation"]["action"] == "WAIT"
    assert pending["context"]["capital_allocatable_wei"] == 5000

    learning_events = [
        event for event in runtime._telemetry_service.events if event[0] == "omar_learning_update"
    ]
    assert len(learning_events) == 1
    assert learning_events[0][1]["decision_id"] == decision_id
    assert learning_events[0][1]["correlation_id"] == correlation_id
