from __future__ import annotations

import asyncio

from victor_ai_bot.ai_inference import (
    AgentDecision,
    AgentProvider,
    AgentRequest,
    GovernedAIRouter,
)
from victor_ai_bot.execution_capture.ai_latency import (
    ai_latency_cost_usd,
    ai_latency_learning_projection,
)
from victor_ai_bot.execution_capture.envelope import build_opportunity_envelope
from victor_ai_bot.execution_capture.scoring import compute_capture_score
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore
from victor_ai_bot.engine_control.admission_governor import EngineAdmissionGovernor
from victor_ai_bot.engine_control.capability_registry import default_engine_capability_registry
from victor_ai_bot.engine_control.models import EngineOpportunity


class _Router(GovernedAIRouter):
    async def _call_provider(self, provider, req):
        if provider.provider == "bad":
            raise RuntimeError("provider_down")
        await asyncio.sleep(0)
        return "evidence", {}, {"input_tokens": 10, "output_tokens": 10}


def test_router_falls_back_and_records_provenance():
    router = _Router(
        [
            AgentProvider("bad", "m1", endpoint="x", api_key_env="X", fallback_rank=0),
            AgentProvider("good", "m2", endpoint="x", api_key_env="X", fallback_rank=1),
        ]
    )
    result = asyncio.run(
        router.infer(
            AgentRequest(
                agent_id="quant",
                task="research",
                prompt="test",
                max_latency_ms=500,
                max_cost_usd=1.0,
            )
        )
    )
    assert result.ok is True
    assert result.provider.provider == "good"
    assert result.fallback_count == 1
    assert result.evidence is not None
    assert result.evidence.provenance["authority"] == "advisory_evidence_only"


def test_ai_latency_cost_is_zero_without_ai_latency_and_increases_with_decay():
    zero = ai_latency_cost_usd(
        expected_profit_usd=20.0, ai_latency_ms=0.0, latency_half_life_ms=500
    )
    slow = ai_latency_cost_usd(
        expected_profit_usd=20.0, ai_latency_ms=500.0, latency_half_life_ms=500
    )
    assert zero == 0.0
    assert slow > 0.0


def test_ai_latency_learning_is_bounded():
    projected = ai_latency_learning_projection(
        {
            "avg_ai_latency_ms": 700.0,
            "avg_expected_pnl_usd": 10.0,
            "avg_realized_pnl_usd": 4.0,
            "ai_latency_samples": 40,
        }
    )
    assert projected["ai_latency_learned_factor"] >= 0.50
    assert projected["ai_latency_learned_factor"] <= 1.0
    assert projected["ai_latency_learning_confidence"] == 1.0


def test_capture_score_prices_ai_latency_as_additive_cost():
    class O:
        id = "o1"
        route_id = "r1"
        route_family = "flashloan_atomic"
        expected_profit_usd = 20.0
        expected_profit_raw = "1"
        meta = {"ai_latency_ms": 500.0, "capital_required_usd": 100.0, "executable_depth_usd": 100.0}
        route = type("R", (), {"legs": []})()

    envelope = build_opportunity_envelope(O(), chain_id=1, regime="balanced")
    score = compute_capture_score(
        envelope,
        {
            "ai_latency_ms": 500.0,
            "avg_ai_latency_ms": 500.0,
            "ai_latency_samples": 20.0,
            "avg_expected_pnl_usd": 20.0,
            "avg_realized_pnl_usd": 20.0,
        },
    )
    assert score.ai_latency_decay_cost > 0.0
    assert score.latency_decay_cost >= score.ai_latency_decay_cost


def test_capture_telemetry_round_trips_ai_latency(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain="eth")
    store.record(
        route_family="flashloan_atomic",
        venues=["univ3"],
        lane="PRIVATE",
        relay="relay",
        rpc="rpc",
        success=True,
        drop=False,
        revert=False,
        stale=False,
        timeout=False,
        slippage_delta_bps=0.0,
        realized_pnl_usd=8.0,
        expected_pnl_usd=10.0,
        quote_drift_bps=0.0,
        latency_ms=100.0,
        ai_latency_ms=250.0,
        ai_latency_cost_usd=1.0,
    )
    feedback = store.combined_feedback(
        route_family="flashloan_atomic", venues=["univ3"], lane="PRIVATE"
    )
    assert feedback["avg_ai_latency_ms"] == 250.0
    assert feedback["ai_latency_samples"] == 1.0


def test_admission_blocks_only_opportunities_that_explicitly_require_ai_evidence():
    gov = EngineAdmissionGovernor(default_engine_capability_registry())
    base = dict(
        opportunity_id="x",
        engine_type="mev_search",
        strategy_family="mev_search",
        route_family="mev_search",
        chain="ethereum",
        chain_id=1,
        expected_profit_usd=10.0,
        expected_realized_profit_usd=8.0,
        capital_required_usd=1.0,
        inventory_requirements={},
        confidence=0.95,
        regime="balanced",
        latency_sensitivity=0.1,
        risk_flags=[],
        lifecycle_eligibility="capped_live",
        policy_eligibility="observe_only",
        venues=["univ3"],
        metadata={"ai_research_required": True},
    )
    denied = gov.decide(
        opportunity=EngineOpportunity(**base),
        env_mode="live",
        telemetry_points=100,
        calibration_points=100,
        treasury_state={"capital_engine": {"deployable_usd": 1000.0}},
    )
    assert denied.allowed is False
    assert denied.reason == "canonical_ai_evidence_required"
