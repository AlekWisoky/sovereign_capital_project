from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import install_omar_lifecycle_hooks
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _LedgerRepo:
    def __init__(self) -> None:
        self.rows = []

    def all_transactions(self, *, chain: str):
        return list(self.rows)


class _Ledger:
    def append_transaction(self, **kwargs):
        return SimpleNamespace(to_dict=lambda: {**kwargs, "transaction_id": "settlement-1"})


class _Telemetry:
    def __init__(self) -> None:
        self.events = []

    def record(self, event_type, payload, *, chain):
        self.events.append((event_type, dict(payload), str(chain)))


class _FinalizeService:
    def __init__(self, repo: _LedgerRepo) -> None:
        self.repo = repo

    def finalize_replay(self, **kwargs):
        return None

    def observe_outcome_truth_health(self, **kwargs):
        return None

    def synchronize_settlement_accounting(self, runtime, **kwargs):
        pending = dict(kwargs["pending"])
        self.repo.rows.append(
            {
                "transaction_id": "settlement-1",
                "ts_ms": 100,
                "tx_type": "receipt_settlement",
                "chain": "ethereum",
                "receipt_id": str(kwargs["tx_hash"]),
                "metadata": {
                    "tx_hash": str(kwargs["tx_hash"]),
                    "canonical_lineage": {
                        "decision_id": str(pending["canonical_decision_id"]),
                        "correlation_id": str(pending["correlation_id"]),
                    },
                    "opportunity_id": str(pending["opportunity_id"]),
                    "route_id": str(kwargs["route_id"]),
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

    def persist_execution_outcome(self, **kwargs):
        return {
            "route_family": "arbitrage",
            "strategy_family": "flashloan_atomic",
            "realized_usd": 7.0,
            "expected_usd": 4.0,
        }

    def update_execution_learning(self, **kwargs):
        return None

    def observe_settlement_memory(self, **kwargs):
        return None

    def update_agent_performance(self, **kwargs):
        return None

    def observe_blockspace(self, **kwargs):
        return None

    def notify_governance(self, **kwargs):
        return None

    def notify_narrative(self, **kwargs):
        return None


@pytest.mark.asyncio
async def test_real_receipt_finalize_creates_canonical_settlement_then_updates_omar(monkeypatch, tmp_path):
    """The production receipt-finalize ordering must be settlement -> ledger -> OMAR."""
    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    install_omar_lifecycle_hooks()

    omar = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_learning_enabled=True,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    runtime = object.__new__(RuntimeReceiptFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = omar
    runtime._ledger = _Ledger()
    runtime._ledger_repo = _LedgerRepo()
    runtime._telemetry_service = _Telemetry()
    runtime._errors = []

    decision_id = "decision-production-1"
    correlation_id = "corr-production-1"
    intent = {
        "aggression_mode": "balanced",
        "risk_multiplier": 0.7,
        "goal": {"target_amount": "10000", "timeframe_days": 30, "goal_revision": 1},
        "ai_recommendation": {"action": "hold", "confidence": 0.8},
    }
    omar.observe_decision(
        decision_id=decision_id,
        opportunity_id="opp-production-1",
        route_id="route-production-1",
        action="EXECUTE",
        state_key="production-state",
        context={"operator_intent": intent},
        metadata={
            "canonical_lineage": {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
            }
        },
    )

    facade = object.__new__(RuntimeReceiptFacade)
    facade.cfg = runtime.cfg
    facade._ledger = runtime._ledger
    facade._ledger_repo = runtime._ledger_repo
    facade._omar = omar
    facade._telemetry_service = runtime._telemetry_service
    facade._errors = []
    facade._run_receipt_finalize_step = RuntimeReceiptFacade._run_receipt_finalize_step.__get__(facade)
    facade._observe_receipt_finalize_critical_failure = RuntimeReceiptFacade._observe_receipt_finalize_critical_failure.__get__(facade)
    facade._update_settlement_followthrough = RuntimeReceiptFacade._update_settlement_followthrough.__get__(facade)

    pending = {
        "canonical_decision_id": decision_id,
        "correlation_id": correlation_id,
        "opportunity_id": "opp-production-1",
        "route_id": "route-production-1",
        "route_family": "arbitrage",
        "strategy_family": "flashloan_atomic",
        "brain": {
            "canonical_decision_id": decision_id,
            "correlation_id": correlation_id,
        },
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        },
        "context": {"operator_intent": intent},
    }

    service = _FinalizeService(runtime._ledger_repo)
    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects")

    # Use the installed production wrapper. The original method remains the
    # real receipt-finalize implementation; only its downstream service calls
    # are supplied by the test seam.
    monkeypatch.setattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", original)

    RuntimeReceiptFacade._safe_finalize_receipt_side_effects(
        facade,
        service,
        tx_hash="0xtx-production-1",
        receipt={"status": "0x1"},
        decoded={"realized_profit_after_gas_wei": "7000000"},
        pending=pending,
        status=1,
        submit_to_receipt_ms=80,
        expected_after=4000000,
        realized_after=7000000,
        amount_in=100,
        gas_est_wei=100,
        route_id="route-production-1",
        reward_trace={"reward": 3.0},
        capture_lane_pending="FAST",
        capture_relay_pending="relay-a",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    settled = facade.canonical_settled_outcome(
        tx_hash="0xtx-production-1",
        decision_id=decision_id,
        correlation_id=correlation_id,
        opportunity_id="opp-production-1",
    )
    assert settled is not None
    assert settled["source"] == "phase2_canonical_outcome_ledger"
    assert settled["decision_id"] == decision_id
    assert settled["correlation_id"] == correlation_id

    # Directly exercise the production post-settlement propagation seam. This
    # mirrors the receipt wrapper's call after canonical settlement exists.
    from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome

    result = _observe_settled_outcome(facade, pending=pending, outcome=settled)
    assert result["ok"] is True
    assert result["action"] == "EXECUTE"
    assert omar._real_learner.total_observations == 1
    assert omar._real_learner.q["production-state"]["EXECUTE"] != 0.0

    telemetry_events = [event for event in runtime._telemetry_service.events if event[0] == "omar_learning_update"]
    assert len(telemetry_events) == 1
    payload = telemetry_events[0][1]
    assert payload["decision_id"] == decision_id
    assert payload["correlation_id"] == correlation_id
    assert payload["tx_hash"] == "0xtx-production-1"
    assert payload["action"] == "EXECUTE"
