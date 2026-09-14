from types import SimpleNamespace

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime


# Regression coverage is intentionally isolated at the OMAR context boundary.
def _runtime(tmp_path):
    runtime = OmarRuntime(
        OmarConfig(enabled=True, real_learning_enabled=True, real_learning_min_observations=1),
        chain_name="ethereum",
    )
    runtime.learning_path = str(tmp_path / "omar.json")
    runtime._real_learner.path = runtime.learning_path
    return runtime


def _verified_outcome():
    return {
        "decision_id": "decision-prev",
        "source": "phase2_canonical_outcome_ledger",
        "settlement_verified": True,
        "outcome_truth_verified": True,
        "expected_net_usd": 100.0,
        "realized_net_usd": 72.5,
        "expectation_error": -27.5,
        "strategy_family": "flash_arb",
        "execution_id": "execution-prev",
        "outcome_id": "outcome-prev",
        "sizing_id": "sizing-prev",
        "opportunity_id": "opp-prev",
        "route_id": "route-prev",
        "latency_ms": 84,
        "slippage_bps": 2.5,
        "gas_cost_usd": 0.31,
        "settled_ts_ms": 123456789,
    }


def test_recommendation_receives_only_verified_prior_canonical_outcome(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.last_outcome = _verified_outcome()
    captured = {}

    def fake_recommend(context):
        captured.update(context)
        return SimpleNamespace(to_dict=lambda: {"action": "EXECUTE"})

    runtime._real_learner.recommend = fake_recommend
    runtime.recommend({"capital_authority_status": "authorized"})

    prior = captured["prior_canonical_outcome"]
    assert prior["decision_id"] == "decision-prev"
    assert prior["expected_net_usd"] == 100.0
    assert prior["realized_net_usd"] == 72.5
    assert prior["expectation_error"] == -27.5
    assert prior["strategy_family"] == "flash_arb"
    assert prior["execution_id"] == "execution-prev"
    assert prior["outcome_id"] == "outcome-prev"
    assert prior["sizing_id"] == "sizing-prev"
    assert prior["route_id"] == "route-prev"


def test_observe_decision_persists_same_prior_context_used_for_next_learning_state(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.last_outcome = _verified_outcome()

    runtime.observe_decision(
        decision_id="decision-next",
        opportunity_id="opp-next",
        route_id="route-next",
        action="EXECUTE",
        state_key="state-next",
        context={"capital_authority_status": "authorized"},
        metadata={"canonical_lineage": {"decision_id": "decision-next", "correlation_id": "corr-next"}},
    )

    stored = runtime._pending_decisions["decision-next"]["context"]
    assert stored["prior_canonical_outcome"]["decision_id"] == "decision-prev"
    assert stored["prior_canonical_outcome"]["expectation_error"] == -27.5


def test_unverified_or_incomplete_prior_outcome_is_excluded(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.last_outcome = {**_verified_outcome(), "settlement_verified": False}
    assert runtime._prior_canonical_outcome_context() == {}

    runtime.last_outcome = {**_verified_outcome(), "execution_id": ""}
    assert runtime._prior_canonical_outcome_context() == {}

    runtime.last_outcome = {**_verified_outcome(), "source": "receipt"}
    assert runtime._prior_canonical_outcome_context() == {}


def test_nonfinite_prior_economics_are_excluded(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.last_outcome = {**_verified_outcome(), "realized_net_usd": float("nan")}
    assert runtime._prior_canonical_outcome_context() == {}
