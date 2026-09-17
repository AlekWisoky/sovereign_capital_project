from types import SimpleNamespace

from victor_ai_bot.execution_capture.envelope import build_opportunity_envelope
from victor_ai_bot.execution_capture.scoring import compute_capture_score
from victor_ai_bot.fund_os.profit_doctrine import executable_edge_objective


def test_executable_edge_objective_multiplies_risk_quality_factors():
    result = executable_edge_objective(
        executable_net_profit=100.0,
        probability_of_success=0.9,
        route_quality=0.8,
        liquidity_quality=0.75,
        capital_efficiency=0.6,
        latency_survivability=0.5,
        execution_reliability=0.4,
    )
    assert result["executableNetProfit"] == 100.0
    assert result["realizedEdge"] == 6.48


def test_executable_edge_objective_clips_oversized_factors_and_negative_profit():
    result = executable_edge_objective(
        executable_net_profit=-10.0,
        probability_of_success=2.0,
        route_quality=1.5,
        liquidity_quality=-1.0,
        capital_efficiency=3.0,
        latency_survivability=2.0,
        execution_reliability=2.0,
    )
    assert result["executableNetProfit"] == 0.0
    assert result["realizedEdge"] == 0.0
    assert result["liquidityQuality"] == 0.0


def test_capture_score_exposes_realized_edge_components():
    opp = SimpleNamespace(
        id="edge-objective",
        route_id="route-edge-objective",
        strategy="flashloan_atomic",
        expected_profit_usd="20.0",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(venue="univ3", token_in="WETH", token_out="USDC"),
                SimpleNamespace(venue="curve", token_in="USDC", token_out="WETH"),
            ]
        ),
        meta={
            "margin_ratio": 0.18,
            "gas_ratio": 0.15,
            "p_success": 0.9,
            "liquidity_fragility": 0.2,
            "aqe": {"mev_risk": 0.1},
            "unit_econ": {"gas_cost_usd_micro": 1_000_000},
        },
    )
    envelope = build_opportunity_envelope(opp, chain_id=1, regime="balanced")
    score = compute_capture_score(
        envelope,
        {
            "route_success_rate": 0.95,
            "lane_success_rate": 0.95,
            "venue_success_rate": 0.95,
            "venue_quality": 0.95,
            "capital_efficiency_factor": 0.8,
            "lane_avg_latency_ms": 100.0,
        },
    )
    assert score.realized_edge > 0.0
    # CaptureScore.capture_score remains the legacy expected-realized-PnL
    # surface; the new executable-edge objective is exposed separately.
    assert score.capture_score == score.expected_realized_pnl
    assert score.realized_edge != score.capture_score
    assert score.objective_components["executableNetProfit"] > 0.0
    assert 0.0 <= score.objective_components["liquidityQuality"] <= 1.0
    assert 0.0 <= score.objective_components["latencySurvivability"] <= 1.0
    assert 0.0 <= score.objective_components["executionReliability"] <= 1.0
