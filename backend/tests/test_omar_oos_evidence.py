import pytest

from victor_ai_bot.omar.oos_evidence import OosEvidenceError, produce_oos_evidence


def settled(**changes):
    row = {
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
        "execution_record_id": "exec-1",
        "outcome_id": "outcome-1",
        "action": "EXECUTE",
        "state_key": "state-a",
        "policy_revision": "policy-r1",
        "settled_at": "2026-08-27T10:00:00Z",
        "settlement_source": "canonical_outcome_ledger",
        "settlement_truth_verified": True,
        "candidate_reward_usd": 12.5,
        "baseline_reward_usd": 10.0,
    }
    row.update(changes)
    return row


def test_producer_emits_complete_lineage_and_performance_evidence():
    rows = produce_oos_evidence([settled()])
    assert len(rows) == 1
    row = rows[0]
    assert row["evaluation_split"] == "out_of_sample"
    assert row["decision_id"] == "decision-1"
    assert row["correlation_id"] == "corr-1"
    assert row["execution_record_id"] == "exec-1"
    assert row["outcome_id"] == "outcome-1"
    assert row["action"] == "EXECUTE"
    assert row["policy_revision"] == "policy-r1"
    assert row["advantage_usd"] == pytest.approx(2.5)
    assert row["advantage_bps"] == pytest.approx(2500.0)
    assert row["evidence_id"].startswith("oos-")


def test_producer_is_deterministic_for_same_canonical_record():
    first = produce_oos_evidence([settled()])[0]
    second = produce_oos_evidence([settled()])[0]
    assert first == second


def test_producer_requires_canonical_settlement_and_truth():
    with pytest.raises(OosEvidenceError, match="noncanonical_settlement_source"):
        produce_oos_evidence([settled(settlement_source="receipt")])
    with pytest.raises(OosEvidenceError, match="unverified_settlement_truth"):
        produce_oos_evidence([settled(settlement_truth_verified=False)])


def test_producer_requires_complete_identity_and_explicit_baseline():
    with pytest.raises(OosEvidenceError, match="missing_canonical_fields:decision_id"):
        produce_oos_evidence([settled(decision_id="")])
    with pytest.raises(OosEvidenceError, match="invalid_baseline_reward_usd"):
        produce_oos_evidence([settled(baseline_reward_usd=None)])


def test_producer_rejects_duplicate_evidence_identity():
    with pytest.raises(OosEvidenceError, match="duplicate_oos_evidence_identity"):
        produce_oos_evidence([settled(), settled()])


def test_producer_never_accepts_training_split_as_oos():
    with pytest.raises(OosEvidenceError, match="invalid_evaluation_split"):
        produce_oos_evidence([settled()], evaluation_split="training")
