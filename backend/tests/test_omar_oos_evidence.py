import json

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.oos_evidence import oos_evidence_path
from victor_ai_bot.omar.performance_promotion import (
    PerformancePromotionThresholds,
)
from victor_ai_bot.omar.runtime import OmarRuntime


def test_oos_evidence_requires_explicit_oos_split_and_real_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    rt = OmarRuntime(OmarConfig(enabled=True, real_learning_min_observations=1), chain_name="test")
    result = rt.observe_decision(
        decision_id="dec-1",
        opportunity_id="opp-1",
        route_id="route-1",
        action="EXECUTE",
        state_key="state-1",
        context={"evaluation_split": "out_of_sample"},
        metadata={"correlation_id": "corr-1"},
    )
    assert result is None

    outcome = rt.observe_outcome(
        decision_id="dec-1",
        ok=True,
        realized_net_usd=12.0,
        expected_net_usd=10.0,
        amount_in_wei=100,
        route_id="route-1",
        tx_hash="0xabc",
        outcome_id="out-1",
        execution_id="exec-1",
        metadata={"evaluation_split": "out_of_sample"},
    )
    assert outcome["ok"] is True
    assert outcome["oos_evidence"]["ok"] is False
    assert outcome["oos_evidence"]["reason"] == "missing_realized_baseline"
    assert not (tmp_path / "superstructure" / "omar_learning" / "oos_evidence_test.jsonl").exists()


def test_settled_outcome_emits_canonical_oos_record_and_promotion_reads_it(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    rt = OmarRuntime(OmarConfig(enabled=True, real_learning_min_observations=1), chain_name="test")
    rt.observe_decision(
        decision_id="dec-2",
        opportunity_id="opp-2",
        route_id="route-2",
        action="EXECUTE",
        state_key="state-2",
        context={"evaluation_split": "out_of_sample"},
        metadata={"correlation_id": "corr-2"},
    )
    outcome = rt.observe_outcome(
        decision_id="dec-2",
        ok=True,
        realized_net_usd=12.0,
        expected_net_usd=10.0,
        amount_in_wei=100,
        route_id="route-2",
        tx_hash="0xdef",
        outcome_id="out-2",
        execution_id="exec-2",
        metadata={"evaluation_split": "out_of_sample", "baseline_reward_usd": 10.0},
    )
    assert outcome["oos_evidence"]["ok"] is True

    path = oos_evidence_path(rt)
    row = json.loads(open(path, encoding="utf-8").readline())
    assert row["evaluation_split"] == "out_of_sample"
    assert row["decision_id"] == "dec-2"
    assert row["correlation_id"] == "corr-2"
    assert row["execution_id"] == "exec-2"
    assert row["outcome_id"] == "out-2"
    assert row["candidate_reward_usd"] == 12.0
    assert row["baseline_reward_usd"] == 10.0

    result = rt.performance_promotion()
    assert result["observations"] == 1
    assert result["candidate_reward_usd"] == 12.0
    assert result["baseline_reward_usd"] == 10.0
    assert result["promotion_allowed"] is False


def test_oos_promotion_can_pass_when_thresholds_are_met(tmp_path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    rt = OmarRuntime(OmarConfig(enabled=True, real_learning_min_observations=1), chain_name="test")
    for i in range(2):
        rt.observe_decision(
            decision_id=f"dec-{i}",
            opportunity_id=f"opp-{i}",
            route_id=f"route-{i}",
            action="EXECUTE",
            state_key=f"state-{i}",
            context={"evaluation_split": "oos"},
            metadata={"correlation_id": f"corr-{i}"},
        )
        rt.observe_outcome(
            decision_id=f"dec-{i}",
            ok=True,
            realized_net_usd=10.0,
            expected_net_usd=8.0,
            amount_in_wei=100,
            metadata={"evaluation_split": "oos", "baseline_reward_usd": 9.0},
        )

    result = rt.performance_promotion()
    assert result["observations"] == 2
    assert result["mean_advantage_usd"] == 1.0
    assert result["win_rate"] == 1.0

    from victor_ai_bot.omar.performance_promotion_runtime import performance_promotion

    passed = performance_promotion(
        rt,
        thresholds=PerformancePromotionThresholds(
            min_evaluation_observations=2,
            min_unique_states=2,
            min_mean_advantage_usd=0.5,
            min_mean_advantage_bps=1000.0,
            min_win_rate=1.0,
            min_lower_confidence_advantage_usd=0.0,
        ),
    )
    assert passed.ready is True
