from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.autonomous_learning_gate import install_autonomous_learning_gate
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime


def _runtime(tmp_path):
    rt = OmarRuntime(
        OmarConfig(
            enabled=True,
            self_play_enabled=False,
            real_learning_enabled=True,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    rt.learning_path = str(tmp_path / "omar.json")
    rt._real_learner.path = rt.learning_path
    rt._pending_decisions = {}
    install_autonomous_learning_gate()
    return rt


def _decision(rt, *, decision_id="decision-7", correlation_id="corr-7", action="EXECUTE"):
    rt.observe_decision(
        decision_id=decision_id,
        opportunity_id="opp-7",
        route_id="route-7",
        action=action,
        state_key="state-7",
        context={
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "authorized",
            "capital_authority_freshness": "fresh",
        },
        metadata={
            "canonical_lineage": {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
            }
        },
    )


def test_phase7_production_learning_gate_proves_exact_attribution_and_fails_closed(tmp_path):
    """One production-shaped learning boundary: exact canonical settlement trains; bad truth/source cannot."""
    rt = _runtime(tmp_path)
    decision_id = "decision-7"
    correlation_id = "corr-7"
    _decision(rt, decision_id=decision_id, correlation_id=correlation_id)

    accepted = rt.observe_outcome(
        decision_id=decision_id,
        ok=True,
        realized_net_usd=7.0,
        expected_net_usd=4.0,
        amount_in_wei=100,
        gas_cost_usd=0.2,
        slippage_bps=3.0,
        latency_ms=80,
        route_id="route-7",
        tx_hash="0xtx-7",
        outcome_truth_verified=True,
        metadata={
            "source": "phase2_canonical_outcome_ledger",
            "canonical_lineage": {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
            },
            "settlement": {
                "status": "settled",
                "source": "phase2_canonical_outcome_ledger",
                "decision_id": decision_id,
                "correlation_id": correlation_id,
                "opportunity_id": "opp-7",
                "route_id": "route-7",
                "action": "EXECUTE",
                "truth_verified": True,
                "realized_net_usd": 7.0,
                "expected_net_usd": 4.0,
                "amount_in_wei": 100,
                "gas_cost_usd": 0.2,
                "slippage_bps": 3.0,
                "latency_ms": 80,
                "tx_hash": "0xtx-7",
            },
        },
    )
    assert accepted["ok"] is True
    assert accepted["action"] == "EXECUTE"
    assert rt._real_learner.total_observations == 1
    assert rt._real_learner.q["state-7"]["EXECUTE"] != 0.0

    _decision(rt, decision_id="decision-7-bad", correlation_id="corr-7-bad")
    rejected = rt.observe_outcome(
        decision_id="decision-7-bad",
        ok=True,
        realized_net_usd=100.0,
        expected_net_usd=1.0,
        amount_in_wei=100,
        route_id="route-7",
        tx_hash="0xtx-bad",
        outcome_truth_verified=False,
        metadata={
            "source": "execution_receipt",
            "canonical_lineage": {
                "decision_id": "decision-7-bad",
                "correlation_id": "corr-7-bad",
            },
            "settlement": {
                "status": "settled",
                "source": "execution_receipt",
                "decision_id": "decision-7-bad",
                "correlation_id": "corr-7-bad",
                "opportunity_id": "opp-7",
                "route_id": "route-7",
                "action": "EXECUTE",
                "truth_verified": False,
            },
        },
    )
    assert rejected["ok"] is False
    assert rejected["learned"] is False
    assert rejected["reason"] == "outcome_truth_unverified"
    assert rt._real_learner.total_observations == 1
