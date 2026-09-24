from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.alpha_marketplace.sleeves import project_strategy_sleeves
from victor_ai_bot.alpha_marketplace.submissions import AlphaMarketplaceStore
from victor_ai_bot.research_pipeline.promotion import promotion_allowed, retirement_allowed


def _runtime(rows, prime):
    return SimpleNamespace(
        _ledger_repo=SimpleNamespace(all_transactions=lambda chain: list(rows)),
        cfg=SimpleNamespace(chain=SimpleNamespace(name="test")),
        internal_prime_state=lambda: dict(prime),
    )


def _settlement(strategy_id: str, *, realized: float, expected: float = 0.0, decision: str = "d1") -> dict:
    return {
        "tx_type": "receipt_settlement",
        "transaction_id": f"tx-{decision}",
        "receipt_id": f"r-{decision}",
        "ts_ms": 10,
        "metadata": {
            "strategy_id": strategy_id,
            "decision_id": decision,
            "correlation_id": f"c-{decision}",
            "execution_id": f"e-{decision}",
            "sizing_id": f"s-{decision}",
            "opportunity_id": f"o-{decision}",
            "route_id": f"route-{decision}",
            "action": "EXECUTE",
            "outcome_id": f"outcome-{decision}",
            "expected_net_usd": expected,
            "realized_net_usd": realized,
            "truth_verified": True,
            "settlement_verified": True,
            "canonical_lineage": {"strategy_id": strategy_id, "decision_id": decision},
        },
    }


def test_strategy_sleeve_projects_verified_settlement_and_prime_commitment():
    runtime = _runtime(
        [_settlement("strategy-1", realized=12.5, expected=10.0)],
        {
            "stateReady": True,
            "capacityUsd": 100000.0,
            "borrowedUsd": 25000.0,
            "utilization": 0.25,
            "openLoans": [{"loan_id": "loan-1", "strategy_id": "strategy-1", "notional_usd": 25000.0, "status": "open"}],
            "disputedLoans": [],
        },
    )
    out = project_strategy_sleeves(runtime, strategy_ids=["strategy-1"])
    sleeve = out["sleeves"]["strategy-1"]
    assert out["ok"] is True
    assert sleeve["capitalSleeveStatus"] == "funded"
    assert sleeve["primeCommittedUsd"] == 25000.0
    assert sleeve["realizedNetUsd"] == 12.5
    assert sleeve["expectedNetUsd"] == 10.0
    assert sleeve["expectationErrorUsd"] == 2.5
    assert sleeve["verifiedSettlementCount"] == 1


def test_strategy_sleeve_reports_settled_unfunded_without_prime_commitment():
    runtime = _runtime([_settlement("strategy-1", realized=1.0)], {
        "stateReady": True,
        "capacityUsd": 100000.0,
        "borrowedUsd": 0.0,
        "utilization": 0.0,
        "openLoans": [],
        "disputedLoans": [],
    })
    out = project_strategy_sleeves(runtime, strategy_ids=["strategy-1"])
    assert out["ok"] is True
    assert out["sleeves"]["strategy-1"]["capitalSleeveStatus"] == "settled_unfunded"
    assert out["sleeves"]["strategy-1"]["primeCommittedUsd"] == 0.0


def test_strategy_sleeve_fails_closed_when_prime_state_is_unavailable():
    runtime = _runtime([_settlement("strategy-1", realized=1.0)], {"stateReady": False, "stateReasonCode": "prime_state_unavailable"})
    out = project_strategy_sleeves(runtime, strategy_ids=["strategy-1"])
    assert out["ok"] is False
    assert out["reason_code"] == "prime_state_unavailable"
    assert out["sleeves"] == {}


def test_marketplace_promotion_requires_governance_and_evidence(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain="test", enabled=True)
    submitted = store.submit(title="Alpha", contributor="aqe", family="flash_arb", thesis="atomic spread")
    sid = submitted["item"]["submissionId"]
    blocked = store.promote(sid)
    assert blocked == {"ok": False, "reason": "governance_approval_required"}
    assert store.set_governance(sid, review_state="approved", governance_status="approved", reviewer="human")["ok"]
    blocked_evidence = store.promote(sid)
    assert blocked_evidence == {"ok": False, "reason": "insufficient_telemetry"}
    promoted = store.promote(sid)
    assert promoted["ok"] is False


def test_marketplace_promotion_uses_canonical_thresholds(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain="test", enabled=True)
    submitted = store.submit(title="Alpha", contributor="aqe", family="flash_arb", thesis="atomic spread")
    sid = submitted["item"]["submissionId"]
    assert store.set_governance(sid, review_state="approved", governance_status="approved", reviewer="human")["ok"]
    store._items[sid]["evidence"].update({"telemetry_count": 5, "score": 0.62, "riskScore": 0.40})
    promoted = store.promote(sid, reviewer="human")
    assert promoted["ok"] is True
    assert promoted["item"]["stage"] == "paper"


def test_retirement_is_deterministic_and_uses_existing_promotion_module():
    decision = retirement_allowed(stage="capped_live", evidence={"drawdown_pct": 9.0})
    assert decision["allowed"] is True
    assert decision["nextStage"] == "retired"
    assert promotion_allowed(score=0.62, risk_score=0.40, stage="sandbox")["allowed"] is True


def test_marketplace_records_route_evidence_without_advancing_stage(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain="test", enabled=True)
    submitted = store.submit(title="Alpha", contributor="aqe", family="flash_arb", thesis="route")
    sid = submitted["item"]["submissionId"]
    out = store.record_route_evidence(
        family="flash_arb",
        route_family="univ3_fee_tier_arb",
        realized_pnl_usd=4.25,
        gas_cost_usd=0.30,
        ok=True,
        regime="balanced",
    )
    assert out == {"ok": True, "matched": 1}
    item = store.snapshot()["items"][0]
    assert item["submissionId"] == sid
    assert item["stage"] == "sandbox"
    assert item["evidence"]["telemetry_count"] == 1
    assert item["evidence"]["success_rate"] == 1.0
    assert item["evidence"]["realized_pnl_usd"] == 4.25
    assert item["evidence"]["route_families"] == ["univ3_fee_tier_arb"]
    assert item["evidence"]["rollout_recommendation"]["reason"] == "score_and_risk_evidence_required"
