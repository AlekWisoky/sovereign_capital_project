from types import SimpleNamespace

from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge


def test_persist_execution_outcome_receives_complete_pending_lineage(monkeypatch):
    db = PersistenceDB(":memory:")
    repo = LedgerRepository(db)
    captured = {}

    def original_persist(
        _self,
        *,
        runtime,
        pending,
        status,
        submit_to_receipt_ms,
        realized_usd,
        expected_usd,
        reward_trace,
        capture_lane_pending,
    ):
        captured["pending"] = dict(pending)
        return {
            "ok": True,
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "realized_usd": float(realized_usd),
            "expected_usd": float(expected_usd),
        }

    monkeypatch.setattr(ReceiptService, "persist_execution_outcome", original_persist)
    install_production_lineage_bridge()

    result = ReceiptService().persist_execution_outcome(
        runtime=SimpleNamespace(_ledger_repo=repo),
        pending={
            "tx_hash": "0xtx-7",
            "decision_id": "decision-7",
            "correlation_id": "corr-7",
            "opportunity_id": "opp-7",
            "route_id": "route-7",
            "sizing_id": "sizing-7",
        },
        status="settled",
        submit_to_receipt_ms=80,
        realized_usd=20.0,
        expected_usd=10.0,
        reward_trace={"reward": 1.0},
        capture_lane_pending="private",
    )

    assert result["ok"] is True
    assert captured["pending"]["decision_id"] == "decision-7"
    assert captured["pending"]["correlation_id"] == "corr-7"
    assert captured["pending"]["execution_id"]
    assert captured["pending"]["outcome_id"]
    assert captured["pending"]["canonical_lineage"]["decision_id"] == "decision-7"
    assert captured["pending"]["canonical_lineage"]["correlation_id"] == "corr-7"
    assert captured["pending"]["canonical_lineage"]["execution_id"] == captured["pending"]["execution_id"]
    assert captured["pending"]["canonical_lineage"]["outcome_id"] == captured["pending"]["outcome_id"]


def test_canonical_settled_outcome_returns_none_without_settlement_transaction():
    repo = LedgerRepository(PersistenceDB(":memory:"))
    assert canonical_settled_outcome(repo, tx_hash="0xmissing", decision_id="decision-1") is None


def test_actual_receipt_finalize_carries_complete_identity_to_settlement_and_persistence(monkeypatch):
    calls = []

    def original_persist(
        _self,
        *,
        runtime,
        pending,
        status,
        submit_to_receipt_ms,
        realized_usd,
        expected_usd,
        reward_trace,
        capture_lane_pending,
    ):
        calls.append(("persist", dict(pending)))
        return {
            "ok": True,
            "route_family": str(pending.get("route_family") or "flashloan_atomic"),
            "strategy_family": str(pending.get("strategy_family") or "flashloan_atomic"),
            "realized_usd": float(realized_usd),
            "expected_usd": float(expected_usd),
        }

    monkeypatch.setattr(ReceiptService, "persist_execution_outcome", original_persist)
    install_production_lineage_bridge()

    service = SimpleNamespace()
    service.finalize_replay = lambda **kwargs: calls.append(("replay", kwargs))
    service.observe_outcome_truth_health = lambda **kwargs: calls.append(("truth_health", kwargs))
    service.synchronize_settlement_accounting = lambda **kwargs: calls.append(("settlement", dict(kwargs["pending"]))) or {"ok": True, "transaction_id": "settlement-7"}
    service.persist_execution_outcome = ReceiptService().persist_execution_outcome
    service.update_execution_learning = lambda **kwargs: calls.append(("learning", dict(kwargs["pending"])))
    service.observe_settlement_memory = lambda **kwargs: calls.append(("memory", dict(kwargs["pending"])))
    service.update_agent_performance = lambda **kwargs: calls.append(("performance", dict(kwargs["pending"])))
    service.observe_blockspace = lambda **kwargs: calls.append(("blockspace", kwargs))
    service.notify_governance = lambda **kwargs: calls.append(("governance", kwargs))
    service.notify_narrative = lambda **kwargs: calls.append(("narrative", kwargs))
    service._realized_usd_from_wei = lambda value: float(value) / 1e18

    runtime = object.__new__(RuntimeReceiptFacade)
    runtime._last_settlement_sync = {"ok": True}
    runtime._errors = []

    pending = {
        "tx_hash": "0xtx-7",
        "decision_id": "decision-7",
        "correlation_id": "corr-7",
        "opportunity_id": "opp-7",
        "route_id": "route-7",
        "sizing_id": "sizing-7",
        "amount_in": 100,
        "expected_after": 110,
        "latency_ms": 12,
        "mode": "auto",
        "rl_state": "state-7",
        "rl_action": 2,
        "aqe_action": "EXECUTE",
        "gas_est_wei": 5,
        "route_family": "flashloan_atomic",
        "strategy_family": "flashloan_atomic",
    }

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xtx-7",
        receipt={"status": "0x1"},
        decoded={"realized_after_gas_wei": 20},
        pending=pending,
        status=1,
        submit_to_receipt_ms=80,
        expected_after=110,
        realized_after=120,
        amount_in=100,
        gas_est_wei=5,
        route_id="route-7",
        reward_trace={"reward": 1.0},
        capture_lane_pending="private",
        capture_relay_pending="relay-7",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    settlement = next(row for kind, row in calls if kind == "settlement")
    persisted = next(row for kind, row in calls if kind == "persist")
    for row in (settlement, persisted):
        assert row["decision_id"] == "decision-7"
        assert row["correlation_id"] == "corr-7"
        assert row["execution_id"]
        assert row["outcome_id"]
        assert row["opportunity_id"] == "opp-7"
        assert row["route_id"] == "route-7"
        assert row["sizing_id"] == "sizing-7"
        assert row["action"] == "EXECUTE"
        assert row["canonical_lineage"]["decision_id"] == "decision-7"
        assert row["canonical_lineage"]["correlation_id"] == "corr-7"
        assert row["canonical_lineage"]["execution_id"] == row["execution_id"]
        assert row["canonical_lineage"]["outcome_id"] == row["outcome_id"]
        assert row["canonical_lineage"]["sizing_id"] == "sizing-7"
        assert row["canonical_lineage"]["action"] == "EXECUTE"

    assert settlement["execution_id"] == persisted["execution_id"]
    assert settlement["outcome_id"] == persisted["outcome_id"]
