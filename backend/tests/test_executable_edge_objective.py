from types import SimpleNamespace

from victor_ai_bot.aqe.arbitrage.cross_cex_dex_engine import CrossCEXDEXArbitrageEngine
from victor_ai_bot.execution_capture.envelope import build_opportunity_envelope
from victor_ai_bot.execution_capture.scoring import compute_capture_score
from victor_ai_bot.fund_os.profit_doctrine import capital_efficiency_quality, executable_edge_objective


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


def _score(*, executable_depth_usd: float, capital_required_usd: float):
    opp = SimpleNamespace(
        id="edge-objective",
        route_id="route-edge-objective",
        strategy="flashloan_atomic",
        expected_profit_usd="20.0",
        capital_required_usd=capital_required_usd,
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
            "executable_depth_usd": executable_depth_usd,
            "capital_required_usd": capital_required_usd,
            "aqe": {"mev_risk": 0.1},
            "unit_econ": {"gas_cost_usd_micro": 1_000_000},
        },
    )
    envelope = build_opportunity_envelope(opp, chain_id=1, regime="balanced")
    return compute_capture_score(
        envelope,
        {
            "route_success_rate": 0.95,
            "lane_success_rate": 0.95,
            "venue_success_rate": 0.95,
            "venue_quality": 0.95,
            "lane_avg_latency_ms": 100.0,
        },
    )


def test_liquidity_quality_uses_executable_depth_coverage():
    shallow = _score(executable_depth_usd=50.0, capital_required_usd=100.0)
    deep = _score(executable_depth_usd=100.0, capital_required_usd=100.0)

    assert shallow.objective_components["liquidityQuality"] == 0.5
    assert deep.objective_components["liquidityQuality"] == 1.0
    assert deep.realized_edge > shallow.realized_edge


def test_capital_efficiency_uses_existing_portfolio_preference_curve():
    same_economics_more_capital = _score(executable_depth_usd=200.0, capital_required_usd=200.0)
    same_economics_less_capital = _score(executable_depth_usd=200.0, capital_required_usd=100.0)

    assert capital_efficiency_quality(0.05) == 1.0
    assert capital_efficiency_quality(0.10) == 1.25
    assert (
        same_economics_less_capital.objective_components["capitalEfficiency"]
        > same_economics_more_capital.objective_components["capitalEfficiency"]
    )
    assert same_economics_less_capital.realized_edge > same_economics_more_capital.realized_edge


def test_cross_cex_dex_exposes_limiting_executable_depth_and_capital_truth():
    rows = CrossCEXDEXArbitrageEngine().scan(
        quotes=[
            {
                "symbol": "ETHUSDT",
                "venue": "binance",
                "bid": 2050.0,
                "ask": 2051.0,
                "depth_usd": 4000.0,
            }
        ],
        dex_prices={"ETHUSDT": 2025.0},
        dex_depths={"ETHUSDT": 3000.0},
        venue_inventory={"binance": {"ETHUSDT": 1.5}, "dex": {"ETHUSDT": 1.5}},
    )

    assert rows
    assert rows[0].metadata["executable_depth_usd"] == 3000.0
    assert rows[0].metadata["capital_required_usd"] == 1050.0


def test_capture_score_preserves_legacy_capture_surface():
    score = _score(executable_depth_usd=100.0, capital_required_usd=50.0)

    assert score.realized_edge > 0.0
    # CaptureScore.capture_score remains the legacy expected-realized-PnL
    # surface; the new executable-edge objective is exposed separately.
    assert score.capture_score == score.expected_realized_pnl
    assert score.realized_edge != score.capture_score
    assert score.objective_components["executableNetProfit"] > 0.0
    assert 0.0 <= score.objective_components["liquidityQuality"] <= 1.0
    assert 0.0 <= score.objective_components["capitalEfficiency"] <= 1.0
    assert 0.0 <= score.objective_components["latencySurvivability"] <= 1.0
    assert 0.0 <= score.objective_components["executionReliability"] <= 1.0
