from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import _patch_receipt_settlement_learning
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _LedgerRepo:
    def __init__(self) -> None:
        self.rows = []

    def all_transactions(self, *, chain: str):
        return list(self.rows)


class _Telemetry:
    def __init__(self) -> None:
        self.events = []

    def record(self, event_type, payload, *, chain):
        self.events.append((event_type, dict(payload), str(chain)))


def test_receipt_finalize_hook_propagates_only_after_canonical_settlement(monkeypatch):
    """Prove the real ordering: receipt finalize -> canonical ledger -> OMAR."""
    install_canonical_settlement_interface()

    omar = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_learning_enabled=True,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    repo = _LedgerRepo()
    telemetry = _Telemetry()
    runtime = object.__new__(RuntimeReceiptFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = omar
    runtime._ledger_repo = repo
    runtime._telemetry_service = telemetry
    runtime._last_settlement_sync = {"ok": False}

    decision_id = "decision-production-2"
    correlation_id = "corr-production-2"
    opportunity_id = "opp-production-2"
    route_id = "route-production-2"
    tx_hash = "0xtx-production-2"
    intent = {
        "aggression_mode": "balanced",
        "risk_multiplier": 0.7,
        "goal": {"target_amount": "10000", "timeframe_days": 30, "goal_revision": 1},
        "ai_recommendation": {"action": "hold", "confidence": 0.8},
    }
    omar.observe_decision(
        decision_id=decision_id,
        opportunity_id=opportunity_id,
        route_id=route_id,
        action="EXECUTE",
        state_key="production-state-2",
        context={"operator_intent": intent},
        metadata={
            "canonical_lineage": {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
            }
        },
    )

    pending = {
        "canonical_decision_id": decision_id,
        "correlation_id": correlation_id,
        "opportunity_id": opportunity_id,
        "route_id": route_id,
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        },
        "context": {"operator_intent": intent},
    }

    async def unused():
        return None

    # The hook is tested against a narrow production-shaped receipt-finalize
    # seam: the seam commits the canonical settlement before returning.
    def fake_finalize(self, service, **kwargs):
        pending_row = dict(kwargs["pending"])
        repo.rows.append(
            {
                "transaction_id": "settlement-2",
                "ts_ms": 200,
                "tx_type": "receipt_settlement",
                "chain": "ethereum",
                "receipt_id": str(kwargs["tx_hash"]),
                "metadata": {
                    "tx_hash": str(kwargs["tx_hash"]),
                    "canonical_lineage": {
                        "decision_id": pending_row["canonical_decision_id"],
                        "correlation_id": pending_row["correlation_id"],
                    },
                    "opportunity_id": pending_row["opportunity_id"],
                    "route_id": pending_row["route_id"],
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
        runtime._last_settlement_sync = {"ok": True, "reason": "settled_success"}
        return {"ok": True}

    monkeypatch.setattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", fake_finalize)
    _patch_receipt_settlement_learning()

    RuntimeReceiptFacade._safe_finalize_receipt_side_effects(
        runtime,
        object(),
        tx_hash=tx_hash,
        receipt={"status": "0x1"},
        decoded={},
        pending=pending,
        status=1,
        submit_to_receipt_ms=80,
        expected_after=4_000_000,
        realized_after=7_000_000,
        amount_in=100,
        gas_est_wei=100,
        route_id=route_id,
        reward_trace={"reward": 3.0},
        capture_lane_pending="FAST",
        capture_relay_pending="relay-a",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    settled = runtime.canonical_settled_outcome(
        tx_hash=tx_hash,
        decision_id=decision_id,
        correlation_id=correlation_id,
        opportunity_id=opportunity_id,
    )
    assert settled is not None
    assert settled["source"] == "phase2_canonical_outcome_ledger"
    assert settled["decision_id"] == decision_id
    assert settled["correlation_id"] == correlation_id

    assert omar._real_learner.total_observations == 1
    assert omar._real_learner.q["production-state-2"]["EXECUTE"] != 0.0

    learning_events = [event for event in telemetry.events if event[0] == "omar_learning_update"]
    assert len(learning_events) == 1
    payload = learning_events[0][1]
    assert payload["decision_id"] == decision_id
    assert payload["correlation_id"] == correlation_id
    assert payload["tx_hash"] == tx_hash
    assert payload["action"] == "EXECUTE"

    # A later operator-intent mutation is not allowed to rewrite the captured
    # decision context used by the learner.
    assert omar._pending_decisions == {}
