from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.learning_integrity import validate_learning_transition
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome
from victor_ai_bot.omar.real_learning import OmarRealLearner
from victor_ai_bot.omar.runtime import OmarRuntime


def _pending(decision_id="decision-1", correlation_id="corr-1", expected=100.0):
    return {
        "canonical_decision_id": decision_id,
        "correlation_id": correlation_id,
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "state_key": "state-1",
        "expected_net_usd": expected,
        "context": {
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "authorized",
            "capital_authority_freshness": "fresh",
        },
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "execution_id": "execution-1",
            "outcome_id": "outcome-1",
            "sizing_id": "sizing-1",
            "opportunity_id": "opp-1",
            "route_id": "route-1",
            "action": "EXECUTE",
        },
    }


def _settlement(decision_id="decision-1", correlation_id="corr-1", expected=100.0, realized=70.0, verified=True):
    return {
        "status": "settled",
        "source": "phase2_canonical_outcome_ledger",
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "execution_id": "execution-1",
        "outcome_id": "outcome-1",
        "sizing_id": "sizing-1",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "ok": True,
        "realized_net_usd": realized,
        "expected_net_usd": expected,
        "expectation_error": realized - expected,
        "amount_in_wei": 100,
        "gas_cost_usd": 0.2,
        "slippage_bps": 3.0,
        "latency_ms": 80,
        "truth_verified": verified,
        "settlement_verified": verified,
        "tx_hash": "0xtx-1",
    }


def _runtime(tmp_path, min_observations=1):
    omar = OmarRuntime(OmarConfig(enabled=True, real_learning_enabled=True, real_learning_min_observations=min_observations), chain_name="ethereum")
    omar.learning_path = str(tmp_path / "omar.json")
    omar._real_learner.path = omar.learning_path
    return omar


def test_canonical_decision_to_settlement_to_learning_closed_loop(tmp_path):
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})
    identity = ensure_decision_identity(
        opp, decision, chain_name="ethereum", current_block=100,
        operator_intent={"aggression_mode": "balanced", "risk_multiplier": 0.7, "goal": {"target_amount": "10000", "timeframe_days": 30, "goal_revision": 1}, "ai_recommendation": {"action": "hold", "confidence": 0.8}, "authority": "operator_intent_only"},
        intent_fingerprint="intent-fp-1",
    )
    assert identity.decision_id == opp.meta["brain"]["canonical_decision_id"]
    assert identity.correlation_id == opp.meta["brain"]["correlation_id"]
    assert not identity.decision_id.startswith("omar-")

    omar = _runtime(tmp_path)
    pending = _pending(identity.decision_id, identity.correlation_id, expected=4.0)
    pending["canonical_lineage"]["execution_id"] = "execution-1"
    omar._pending_decisions[identity.decision_id] = pending
    runtime = SimpleNamespace(_omar=omar)
    result = _observe_settled_outcome(runtime, pending=pending, outcome=_settlement(identity.decision_id, identity.correlation_id, expected=4.0, realized=7.0))
    assert result["ok"] is True
    assert result["expected_net_usd"] == 4.0
    assert result["realized_net_usd"] == 7.0
    assert result["expectation_error"] == 3.0
    assert omar._real_learner.total_observations == 1


def test_learning_rejects_missing_physical_attribution(tmp_path):
    omar = _runtime(tmp_path)
    decision_id = "decision-2"
    pending = _pending(decision_id, "corr-2", expected=1.0)
    pending["opportunity_id"] = "opp-2"; pending["route_id"] = "route-2"; pending["canonical_lineage"].update({"opportunity_id": "opp-2", "route_id": "route-2"})
    omar._pending_decisions[decision_id] = pending
    result = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=100.0, expected_net_usd=1.0, amount_in_wei=100, route_id="route-2", tx_hash="0xbad", outcome_truth_verified=True, metadata={"source": "phase2_canonical_outcome_ledger", "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-2"}, "settlement": {"status": "settled", "source": "phase2_canonical_outcome_ledger", "decision_id": decision_id, "correlation_id": "corr-2", "opportunity_id": "opp-2", "route_id": "route-2", "action": "EXECUTE", "truth_verified": True}})
    assert result["learned"] is False
    assert result["reason"] == "missing_execution_id"
    assert omar._real_learner.total_observations == 0


def test_new_state_after_global_warmup_uses_baseline(tmp_path):
    learner = OmarRealLearner(path=str(tmp_path / "learner.json"), min_observations=20)
    learner.total_observations = 20
    key = "new-state"
    learner._ensure(key); learner.q[key]["WAIT"] = 100.0
    rec = learner.recommend({"capital_authority_status": "authorized", "capital_authority_freshness": "fresh"})
    assert rec.action == "EXECUTE"
    assert rec.trained is False
    assert rec.observations == 0


def test_state_local_threshold_controls_learned_eligibility(tmp_path):
    learner = OmarRealLearner(path=str(tmp_path / "learner.json"), min_observations=20)
    context = {"capital_authority_status": "authorized", "capital_authority_freshness": "fresh"}
    key = learner.state_key(context); learner._ensure(key); learner.q[key]["WAIT"] = 100.0
    learner.n[key] = 19; learner.total_observations = 100
    assert learner.recommend(context).action == "EXECUTE"
    learner.n[key] = 20
    assert learner.recommend(context).action == "WAIT"
    assert learner.recommend(context).trained is True


def test_expectation_error_learned_only_after_verified_settlement(tmp_path):
    omar = _runtime(tmp_path, min_observations=1)
    decision_id = "decision-3"
    pending = _pending(decision_id, "corr-3", expected=100.0)
    omar._pending_decisions[decision_id] = pending
    unverified = _settlement(decision_id, "corr-3", expected=100.0, realized=70.0, verified=False)
    first = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=70.0, expected_net_usd=100.0, amount_in_wei=100, route_id="route-1", tx_hash="0xtx-1", metadata={"settlement": unverified, "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-3"}, "source": "phase2_canonical_outcome_ledger"})
    assert first["learned"] is False
    assert omar._real_learner.total_observations == 0
    verified = _settlement(decision_id, "corr-3", expected=100.0, realized=70.0, verified=True)
    second = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=70.0, expected_net_usd=100.0, amount_in_wei=100, route_id="route-1", tx_hash="0xtx-1", metadata={"settlement": verified, "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-3"}, "source": "phase2_canonical_outcome_ledger"})
    assert second["learned"] is True
    assert second["expectation_error"] == -30.0
    assert omar._real_learner.total_observations == 1


def test_invalid_or_missing_economics_fail_closed(tmp_path):
    cases = [(None, 70.0), (100.0, None), (float("nan"), 70.0), (100.0, float("inf"))]
    for index, (expected, realized) in enumerate(cases):
        omar = _runtime(tmp_path / str(index), min_observations=1)
        decision_id = f"decision-invalid-{index}"
        omar._pending_decisions[decision_id] = _pending(decision_id, f"corr-invalid-{index}", expected=expected)
        settlement = _settlement(decision_id, f"corr-invalid-{index}", expected=100.0, realized=70.0)
        if expected is None:
            settlement.pop("expected_net_usd", None)
            settlement.pop("expectation_error", None)
        elif realized is None:
            settlement.pop("realized_net_usd", None)
            settlement.pop("expectation_error", None)
        else:
            settlement["expected_net_usd"] = expected
            settlement["realized_net_usd"] = realized
            settlement["expectation_error"] = realized - expected
        result = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=realized, expected_net_usd=expected, amount_in_wei=100, route_id="route-1", tx_hash="0xtx", metadata={"settlement": settlement, "canonical_lineage": {"decision_id": decision_id, "correlation_id": f"corr-invalid-{index}"}, "source": "phase2_canonical_outcome_ledger"})
        assert result["learned"] is False
        assert omar._real_learner.total_observations == 0


def test_canonical_decision_id_is_the_only_learning_identity(tmp_path):
    omar = _runtime(tmp_path, min_observations=1)
    decision_id = "canonical-decision-5"
    pending = _pending(decision_id, "corr-5", expected=100.0)
    omar.observe_decision(decision_id=decision_id, opportunity_id="opp-1", route_id="route-1", action="EXECUTE", state_key="state-1", context=pending["context"], metadata={"canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-5"}, "expected_net_usd": 100.0})
    assert list(omar._pending_decisions) == [decision_id]
    result = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=70.0, expected_net_usd=100.0, amount_in_wei=100, route_id="route-1", tx_hash="0xtx-5", metadata={"settlement": _settlement(decision_id, "corr-5", 100.0, 70.0), "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-5"}, "source": "phase2_canonical_outcome_ledger"})
    assert result["decision_id"] == decision_id
    assert omar.last_outcome["decision_id"] == decision_id
    assert decision_id not in omar._pending_decisions
    duplicate = omar.observe_outcome(decision_id=decision_id, ok=True, realized_net_usd=70.0, expected_net_usd=100.0, amount_in_wei=100, route_id="route-1", tx_hash="0xtx-5", metadata={"settlement": _settlement(decision_id, "corr-5", 100.0, 70.0), "canonical_lineage": {"decision_id": decision_id, "correlation_id": "corr-5"}, "source": "phase2_canonical_outcome_ledger"})
    assert duplicate["learned"] is False
    assert omar._real_learner.total_observations == 1


def test_learning_integrity_rejects_authority_and_lineage_mutations():
    pending = _pending("decision-negative", "corr-negative", expected=12.0)
    settled = _settlement("decision-negative", "corr-negative", expected=12.0, realized=15.0)

    cases = [
        ("noncanonical_learning_source", {"source": "receipt"}),
        ("settlement_unverified", {"settlement_verified": False, "truth_verified": False}),
        ("correlation_lineage_mismatch", {"correlation_id": "corr-other"}),
        ("action_attribution_mismatch", {"action": "WAIT"}),
        ("expected_net_attribution_mismatch", {"expected_net_usd": 99.0}),
        ("expectation_error_mismatch", {"expectation_error": 999.0}),
        ("capital_authority_not_canonical", {"pending_context": {"capital_authority_source": "ui_balance"}}),
        ("capital_authority_unavailable", {"pending_context": {"capital_authority_status": "unavailable"}}),
        ("capital_authority_freshness_unknown", {"pending_context": {"capital_authority_freshness": "unknown"}}),
    ]

    for expected_reason, mutation in cases:
        pending_case = dict(pending)
        pending_case["context"] = dict(pending["context"])
        outcome_case = dict(settled)
        for key, value in mutation.items():
            if key == "pending_context":
                pending_case["context"].update(value)
            else:
                outcome_case[key] = value
        result = validate_learning_transition(pending_case, outcome_case, decision_id="decision-negative")
        assert result.allowed is False
        assert result.reason == expected_reason


def test_learning_integrity_rejects_each_required_physical_identity():
    pending = _pending("decision-identities", "corr-identities", expected=5.0)
    settled = _settlement("decision-identities", "corr-identities", expected=5.0, realized=6.0)
    for field in ("execution_id", "outcome_id", "sizing_id", "opportunity_id", "route_id"):
        outcome = dict(settled)
        outcome[field] = ""
        result = validate_learning_transition(pending, outcome, decision_id="decision-identities")
        assert result.allowed is False
        assert result.reason == f"missing_{field}"


def test_learning_integrity_rejects_unsettled_outcome_before_economic_processing():
    pending = _pending("decision-pending", "corr-pending", expected=8.0)
    outcome = _settlement("decision-pending", "corr-pending", expected=8.0, realized=9.0)
    outcome["status"] = "pending"
    outcome["realized_net_usd"] = None
    result = validate_learning_transition(pending, outcome, decision_id="decision-pending")
    assert result.allowed is False
    assert result.reason == "outcome_not_canonically_settled"
