from __future__ import annotations

from victor_ai_bot.omar.learning_identity import DurableLearningIdentity


def test_learning_identity_survives_reload_and_deduplicates_settlement(tmp_path):
    path = str(tmp_path / "identity.json")
    first = DurableLearningIdentity(path)

    first.remember_decision(
        "decision-1",
        {
            "correlation_id": "corr-1",
            "action": "EXECUTE",
            "state_key": "state-1",
        },
    )
    assert first.pending("decision-1")["action"] == "EXECUTE"
    assert not first.is_settled("decision-1")

    first.mark_settled(
        "decision-1",
        {"correlation_id": "corr-1", "tx_hash": "0xabc"},
    )

    second = DurableLearningIdentity(path)
    assert second.is_settled("decision-1")
    assert second.pending("decision-1") == {}


def test_learning_identity_keeps_pending_decisions_until_settlement(tmp_path):
    path = str(tmp_path / "identity.json")
    store = DurableLearningIdentity(path)
    store.remember_decision("decision-2", {"action": "DECREASE_RISK"})

    reloaded = DurableLearningIdentity(path)
    assert reloaded.pending("decision-2")["action"] == "DECREASE_RISK"
    assert not reloaded.is_settled("decision-2")
