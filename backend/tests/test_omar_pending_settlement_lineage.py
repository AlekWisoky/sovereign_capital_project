from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _LedgerRepo:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def all_transactions(self, *, chain: str):
        return [row for row in self.rows if row.get("chain", chain) == chain]


def test_persist_execution_outcome_receives_complete_pending_lineage(monkeypatch):
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
        return {"ok": True, "route_family": "flashloan_atomic", "strategy_family": "flashloan_atomic", "realized_usd": float(realized_usd), "expected_usd": float(expected_usd)}

    monkeypatch.setattr(ReceiptService, "persist_execution_outcome", original_persist)
    install_production_lineage_bridge()

    result = ReceiptService().persist_execution_outcome(
        runtime=SimpleNamespace(),
        pending={
            "tx_hash": "0xtx-7",
            "decision_id": "decision-7",
            "correlation_id": "corr-7",
            "opportunity_id": "opp-7",
            "route_id": "route-7",
            "sizing_id": "sizing-7",
            "aqe_action": "EXECUTE",
        },
        status=1,
        submit_to_receipt_ms=42,
        realized_usd=7.0,
        expected_usd=5.0,
        reward_trace={"reward": 2.0},
        capture_lane_pending="private",
    )

    assert result["ok"] is True
    persisted = captured["pending"]
    assert persisted["decision_id"] == "decision-7"
    assert persisted["canonical_decision_id"] == "decision-7"
    assert persisted["correlation_id"] == "corr-7"
    assert persisted["opportunity_id"] == "opp-7"
    assert persisted["route_id"] == "route-7"
    assert persisted["sizing_id"] == "sizing-7"
    assert persisted["action"] == "EXECUTE"
    assert persisted["execution_id"]
    assert persisted["outcome_id"]
    assert persisted["canonical_lineage"]["decision_id"] == "decision-7"
    assert persisted["canonical_lineage"]["correlation_id"] == "corr-7"
    assert persisted["canonical_lineage"]["opportunity_id"] == "opp-7"
    assert persisted["canonical_lineage"]["route_id"] == "route-7"
    assert persisted["canonical_lineage"]["sizing_id"] == "sizing-7"
    assert persisted["canonical_lineage"]["action"] == "EXECUTE"
    assert persisted["canonical_lineage"]["execution_id"] == persisted["execution_id"]
    assert persisted["canonical_lineage"]["outcome_id"] == persisted["outcome_id"]


def test_actual_receipt_finalize_carries_complete_identity_to_settlement_and_persistence(monkeypatch):
    calls = []

    def original_persist(
        _self,
        *,
        runtime, pending, status, submit_to_receipt_ms, realized_usd,
        expected_usd, reward_trace, capture_lane_pending
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


def test_real_ledger_transaction_round_trip_preserves_all_lineage_fields(tmp_path: Path):
    db = PersistenceDB(str(tmp_path / "ledger.sqlite"))
    ledger = LedgerRepository(db, chain="ethereum")
    metadata = {
        "canonical_lineage": {
            "decision_id": "decision-physical",
            "correlation_id": "corr-physical",
            "execution_id": "execution-physical",
            "outcome_id": "outcome-physical",
            "sizing_id": "sizing-physical",
            "opportunity_id": "opp-physical",
            "route_id": "route-physical",
            "action": "EXECUTE",
        },
        "canonical_decision_id": "decision-physical",
        "correlation_id": "corr-physical",
        "execution_id": "execution-physical",
        "outcome_id": "outcome-physical",
        "sizing_id": "sizing-physical",
        "opportunity_id": "opp-physical",
        "route_id": "route-physical",
        "action": "EXECUTE",
        "truth_verified": True,
    }
    ledger.append_transaction(
        chain="ethereum",
        payload={
            "transaction_id": "settlement-physical",
            "ts_ms": 100,
            "tx_type": "receipt_settlement",
            "receipt_id": "0xphysical",
            "metadata": metadata,
        },
    )

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _ledger_repo=ledger,
    )
    outcome = canonical_settled_outcome(
        runtime,
        tx_hash="0xphysical",
        decision_id="decision-physical",
        correlation_id="corr-physical",
        opportunity_id="opp-physical",
    )

    assert outcome is not None
    assert outcome["lineage_persisted"] is True
    assert outcome["canonical_lineage"] == metadata["canonical_lineage"]
    stored = ledger.transactions_tail(chain="ethereum", limit=1)[0]
    assert stored["metadata"]["canonical_lineage"] == metadata["canonical_lineage"]


def test_canonical_settlement_reader_requires_physical_complete_lineage():
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _ledger_repo=_LedgerRepo(
            [
                {
                    "chain": "ethereum",
                    "transaction_id": "settlement-7",
                    "ts_ms": 100,
                    "tx_type": "receipt_settlement",
                    "receipt_id": "0xtx-7",
                    "metadata": {
                        "canonical_lineage": {
                            "decision_id": "decision-7",
                            "correlation_id": "corr-7",
                            "execution_id": "execution-7",
                            "outcome_id": "outcome-7",
                            "sizing_id": "sizing-7",
                            "opportunity_id": "opp-7",
                            "route_id": "route-7",
                            "action": "EXECUTE",
                        },
                        "canonical_decision_id": "decision-7",
                        "correlation_id": "corr-7",
                        "execution_id": "execution-7",
                        "outcome_id": "outcome-7",
                        "sizing_id": "sizing-7",
                        "opportunity_id": "opp-7",
                        "route_id": "route-7",
                        "action": "EXECUTE",
                        "truth_verified": True,
                    },
                }
            ]
        ),
    )

    outcome = canonical_settled_outcome(
        runtime,
        tx_hash="0xtx-7",
        decision_id="decision-7",
        correlation_id="corr-7",
        opportunity_id="opp-7",
    )

    assert outcome is not None
    assert outcome["lineage_persisted"] is True
    assert outcome["canonical_lineage"] == {
        "decision_id": "decision-7",
        "correlation_id": "corr-7",
        "execution_id": "execution-7",
        "outcome_id": "outcome-7",
        "sizing_id": "sizing-7",
        "opportunity_id": "opp-7",
        "route_id": "route-7",
        "action": "EXECUTE",
    }

    runtime._ledger_repo.rows[0]["metadata"]["canonical_lineage"].pop("action")
    runtime._ledger_repo.rows[0]["metadata"].pop("action")
    incomplete = canonical_settled_outcome(
        runtime,
        tx_hash="0xtx-7",
        decision_id="decision-7",
        correlation_id="corr-7",
        opportunity_id="opp-7",
    )
    assert incomplete is not None
    assert incomplete["lineage_persisted"] is False
