from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome
from victor_ai_bot.omar.runtime import OmarRuntime


def test_canonical_decision_to_settlement_to_learning_closed_loop(tmp_path):
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})
    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=100,
        operator_intent={
            "aggression_mode": "balanced",
            "risk_multiplier": 0.7,
            "goal": {"target_amount": "10000", "timeframe_days": 30, "goal_revision": 1},
            "ai_recommendation": {"action": "hold", "confidence": 0.8},
            "authority": "operator_intent_only",
        },
        intent_fingerprint="intent-fp-1",
    )

    assert identity.decision_id == opp.meta["brain"]["canonical_decision_id"]
    assert identity.correlation_id == opp.meta["brain"]["correlation_id"]
    assert not identity.decision_id.startswith("omar-")

    omar = OmarRuntime(
        OmarConfig(enabled=True, real_learning_enabled=True, real_learning_min_observations=1),
        chain_name="ethereum",
    )
    omar.learning_path = str(tmp_path / "omar.json")
    omar._real_learner.path = omar.learning_path

    pending = {
        "canonical_decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "state_key": "state-1",
        "context": {
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "authorized",
            "capital_authority_freshness": "fresh",
            "operator_intent": opp.meta["brain"]["operator_intent"],
        },
        "canonical_lineage": {
            "decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
            "execution_id": "execution-1",
            "outcome_id": "outcome-1",
            "sizing_id": "sizing-1",
            "opportunity_id": "opp-1",
            "route_id": "route-1",
            "action": "EXECUTE",
        },
    }
    omar._pending_decisions[identity.decision_id] = pending

    runtime = SimpleNamespace(_omar=omar)
    outcome = {
        "status": "settled",
        "source": "phase2_canonical_outcome_ledger",
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
        "execution_id": "execution-1",
        "outcome_id": "outcome-1",
        "sizing_id": "sizing-1",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "ok": True,
        "realized_net_usd": 7.0,
        "expected_net_usd": 4.0,
        "amount_in_wei": 100,
        "gas_cost_usd": 0.2,
        "slippage_bps": 3.0,
        "latency_ms": 80,
        "truth_verified": True,
        "tx_hash": "0xtx-1",
    }

    result = _observe_settled_outcome(runtime, pending=pending, outcome=outcome)
    assert result["ok"] is True
    assert omar._real_learner.total_observations == 1


def test_learning_rejects_missing_physical_attribution(tmp_path):
    omar = OmarRuntime(
        OmarConfig(enabled=True, real_learning_enabled=True, real_learning_min_observations=1),
        chain_name="ethereum",
    )
    omar.learning_path = str(tmp_path / "omar.json")
    omar._real_learner.path = omar.learning_path
    decision_id = "decision-2"
    omar._pending_decisions[decision_id] = {
        "correlation_id": "corr-2",
        "opportunity_id": "opp-2",
        "route_id": "route-2",
        "action": "EXECUTE",
        "state_key": "state-2",
        "context": {
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "authorized",
            "capital_authority_freshness": "fresh",
        },
        "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-2"},
    }
    result = omar.observe_outcome(
        decision_id=decision_id,
        ok=True,
        realized_net_usd=100.0,
        expected_net_usd=1.0,
        amount_in_wei=100,
        route_id="route-2",
        tx_hash="0xbad",
        outcome_truth_verified=True,
        metadata={
            "source": "phase2_canonical_outcome_ledger",
            "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-2"},
            "settlement": {
                "status": "settled",
                "source": "phase2_canonical_outcome_ledger",
                "decision_id": decision_id,
                "correlation_id": "corr-2",
                "opportunity_id": "opp-2",
                "route_id": "route-2",
                "action": "EXECUTE",
                "truth_verified": True,
            },
        },
    )
    assert result["learned"] is False
    assert result["reason"] == "missing_execution_id"
    assert omar._real_learner.total_observations == 0
