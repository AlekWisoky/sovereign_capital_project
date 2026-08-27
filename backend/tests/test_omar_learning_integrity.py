from __future__ import annotations

from victor_ai_bot.omar.learning_integrity import validate_learning_transition


def _pending() -> dict:
    return {
        "correlation_id": "corr-1",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "state_key": "state-1",
        "context": {
            "capital_authority_source": "capital_engine_state",
            "capital_authority_status": "authorized",
            "capital_authority_freshness": "fresh",
        },
    }


def _settled() -> dict:
    return {
        "status": "settled",
        "source": "canonical_outcome_ledger",
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "truth_verified": True,
        "canonical_lineage": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
        },
    }


def test_learning_integrity_allows_exact_canonical_settlement():
    result = validate_learning_transition(_pending(), _settled(), decision_id="decision-1")
    assert result.allowed is True
    assert result.reason == "integrity_verified"


def test_learning_integrity_rejects_unsettled_or_noncanonical_outcome():
    outcome = _settled()
    outcome["status"] = "submitted"
    result = validate_learning_transition(_pending(), outcome, decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "outcome_not_canonically_settled"

    outcome = _settled()
    outcome["status"] = "settled"
    outcome["source"] = "execution_receipt"
    result = validate_learning_transition(_pending(), outcome, decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "noncanonical_learning_source"


def test_learning_integrity_rejects_lineage_or_action_mismatch():
    outcome = _settled()
    outcome["correlation_id"] = "wrong"
    result = validate_learning_transition(_pending(), outcome, decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "correlation_lineage_mismatch"

    outcome = _settled()
    outcome["action"] = "DECREASE_RISK"
    result = validate_learning_transition(_pending(), outcome, decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "action_attribution_mismatch"


def test_learning_integrity_requires_verified_truth_and_capital_authority():
    outcome = _settled()
    outcome["truth_verified"] = False
    result = validate_learning_transition(_pending(), outcome, decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "outcome_truth_unverified"

    pending = _pending()
    pending["context"]["capital_authority_status"] = "unavailable"
    result = validate_learning_transition(pending, _settled(), decision_id="decision-1")
    assert result.allowed is False
    assert result.reason == "capital_authority_unavailable"
