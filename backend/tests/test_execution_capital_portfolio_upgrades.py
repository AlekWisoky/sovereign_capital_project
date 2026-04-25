import json
from victor_ai_bot.execution_capture.aging import aging_factor
from victor_ai_bot.execution_capture.path_diversity import PathDiversityMemory
from victor_ai_bot.execution_capture.risk_memory import ExecutionRiskMemory
from victor_ai_bot.execution_capture.venue_profiles import VenueReliabilityStore
from victor_ai_bot.execution_capture.calibration import EmpiricalCalibrationStore
from victor_ai_bot.treasury.family_allocator import compute_dynamic_family_weights
from victor_ai_bot.treasury.crowding import crowding_check
from victor_ai_bot.treasury.risk_controls import drawdown_contraction
from victor_ai_bot.strategies.covariance import FamilyCovarianceStore
from victor_ai_bot.strategies.interaction_model import interaction_risk
from victor_ai_bot.strategies.lifecycle_history import StrategyLifecycleMemory


def test_execution_calibration_and_venue_profiles(tmp_path):
    cal = EmpiricalCalibrationStore(data_dir=str(tmp_path), chain="eth")
    cal.observe(
        route_family="cross_cex_dex",
        lane="PROTECTED",
        regime="balanced",
        projected_gross_edge_usd=14.0,
        projected_realized_edge_usd=10.0,
        actual_realized_edge_usd=7.5,
        predicted_success_probability=0.7,
        actual_success=True,
        predicted_slippage_usd=1.0,
        actual_slippage_usd=1.4,
        predicted_interference_probability=0.2,
        actual_stale=False,
    )
    pri = cal.priors(route_family="cross_cex_dex", lane="PROTECTED", regime="balanced")
    assert round(pri["projected_gross_edge_usd"], 6) == 14.0
    assert round(pri["calibration_factor"], 6) == 0.75

    venues = VenueReliabilityStore(data_dir=str(tmp_path), chain="eth")
    venues.observe(
        venue="uni_v3",
        success=False,
        stale_quote=True,
        slippage_bias_bps=18.0,
        latency_ms=900.0,
        route_success_contribution=0.0,
    )
    venues.observe(
        venue="uni_v3",
        success=True,
        stale_quote=False,
        slippage_bias_bps=6.0,
        latency_ms=400.0,
        route_success_contribution=1.0,
    )
    profile = venues.profile(venue="uni_v3")
    assert profile["venue_reliability_score"] > 0
    assert profile["venue_failure_penalty"] > 0


def test_risk_memory_aging_and_path_diversity(tmp_path):
    mem = ExecutionRiskMemory(str(tmp_path / "risk.json"), horizon_ms=60_000)
    mem.observe_failure(
        route_family="flashloan_atomic",
        venue="uni_v3",
        token_pair="WETH/USDC",
        strategy_family="flashloan_atomic",
        chain="eth",
        pool_path="p1",
        ts_ms=1_000,
    )
    mem.observe_failure(
        route_family="flashloan_atomic",
        venue="uni_v3",
        token_pair="WETH/USDC",
        strategy_family="flashloan_atomic",
        chain="eth",
        pool_path="p1",
        ts_ms=2_000,
    )
    pen = mem.penalty(
        route_family="flashloan_atomic",
        venue="uni_v3",
        token_pair="WETH/USDC",
        strategy_family="flashloan_atomic",
        chain="eth",
        pool_path="p1",
        ts_ms=2_500,
    )
    assert pen["penalty"] > 0
    assert "recent_route_failures" in pen["reason_codes"]

    assert aging_factor(route_family="funding_arb", age_ms=1_000) > aging_factor(
        route_family="flashloan_atomic", age_ms=1_000
    )

    div = PathDiversityMemory(str(tmp_path / "paths.json"), horizon_ms=60_000)
    div.observe("eth:uni:weth-usdc", ts_ms=1_000)
    div.observe("eth:uni:weth-usdc", ts_ms=2_000)
    assert div.penalty("eth:uni:weth-usdc", ts_ms=3_000) > 0


def test_dynamic_allocation_crowding_and_portfolio_memory(tmp_path):
    scorecards = {
        "families": [
            {
                "family": "flashloan_atomic",
                "realizedPnlUsd": 100.0,
                "drawdownPenaltyUsd": 5.0,
                "gasEfficiency": 1.8,
                "executionSuccessRate": 0.82,
                "stability": 0.80,
                "regimePerformance": {"balanced": {"successRate": 0.82, "pnlUsd": 100.0}},
            },
            {
                "family": "funding_arb",
                "realizedPnlUsd": 40.0,
                "drawdownPenaltyUsd": 2.0,
                "gasEfficiency": 1.2,
                "executionSuccessRate": 0.70,
                "stability": 0.74,
                "regimePerformance": {"balanced": {"successRate": 0.70, "pnlUsd": 40.0}},
            },
        ]
    }
    weights = compute_dynamic_family_weights(
        base_targets={"flashloan_atomic": 0.5, "funding_arb": 0.5},
        scorecards=scorecards,
        regime="balanced",
        capital_metrics={"utilization_rate": 0.72},
        covariance_penalties={"funding_arb": 0.10},
    )
    assert weights["flashloan_atomic"] > weights["funding_arb"]

    crowd = crowding_check(
        current_allocations={
            "engine": {"cross_cex_dex": 0.32},
            "family": {"cross_cex_dex": 0.40},
            "chain": {"eth": 0.50},
        },
        candidate_engine="cross_cex_dex",
        candidate_family="cross_cex_dex",
        candidate_chain="eth",
        capital_share=0.10,
    )
    assert crowd["scale"] < 1.0
    assert crowd["reason_codes"] != ["ok"]

    contraction = drawdown_contraction(drawdown_pct=8.0)
    assert contraction["contraction_factor"] < 1.0

    cov = FamilyCovarianceStore(str(tmp_path / "family_cov.json"))
    for x, y in [(0.05, 0.04), (0.02, 0.03), (-0.01, -0.02), (0.06, 0.05)]:
        cov.observe("flashloan_atomic", x)
        cov.observe("cross_cex_dex", y)
    mat = cov.covariance_matrix()
    assert "cross_cex_dex" in mat["flashloan_atomic"]

    inter = interaction_risk(
        family_a="flashloan_atomic",
        family_b="cross_cex_dex",
        tokens_a=["WETH", "USDC"],
        tokens_b=["WETH", "USDC"],
        venues_a=["uniswap", "aave"],
        venues_b=["binance", "uniswap"],
        chains_a=["eth"],
        chains_b=["eth"],
        shared_failure_mode=True,
    )
    assert inter["interaction_risk"] > 0.5

    life = StrategyLifecycleMemory(str(tmp_path / "strategies" / "lifecycle.json"), chain="eth")
    life.append(family="cross_cex_dex", strategy_id="s1", stage="sandbox", reason_code="generated")
    snap = life.snapshot(family="cross_cex_dex")
    assert snap["items"]


def test_family_covariance_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "family_cov.json"
    path.write_text("{not valid json", encoding="utf-8")

    cov = FamilyCovarianceStore(str(path))
    assert cov.covariance_matrix() == {}
    assert cov.penalties() == {}


def test_family_covariance_sanitizes_malformed_persisted_returns(tmp_path):
    path = tmp_path / "family_cov.json"
    path.write_text(
        json.dumps(
            {
                "returns": {
                    "flashloan_atomic": [0.1, "0.2", "bad", None, -0.05],
                    "cross_cex_dex": [0.08, 0.18, "0.01"],
                    "": [1.0],
                    "junk": "nope",
                }
            }
        ),
        encoding="utf-8",
    )

    cov = FamilyCovarianceStore(str(path))
    assert cov._state == {
        "returns": {
            "flashloan_atomic": [0.1, 0.2, -0.05],
            "cross_cex_dex": [0.08, 0.18, 0.01],
        }
    }
    mat = cov.covariance_matrix()
    assert "cross_cex_dex" in mat["flashloan_atomic"]


def test_lifecycle_memory_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "strategies" / "lifecycle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    life = StrategyLifecycleMemory(str(path), chain="eth")
    assert life.snapshot() == {"items": []}


def test_lifecycle_memory_sanitizes_malformed_persisted_items(tmp_path):
    path = tmp_path / "strategies" / "lifecycle.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "ts_ms": "1234",
                        "family": "cross_cex_dex",
                        "strategy_id": "s1",
                        "stage": "sandbox",
                        "reason_code": "generated",
                        "payload": {"x": 1},
                    },
                    {
                        "ts_ms": "oops",
                        "family": "funding_arb",
                        "strategy_id": "",
                        "stage": "live",
                        "reason_code": "promoted",
                        "payload": ["bad"],
                    },
                    "junk",
                ]
            }
        ),
        encoding="utf-8",
    )

    life = StrategyLifecycleMemory(str(path), chain="eth")
    snap = life.snapshot()
    assert snap == {
        "items": [
            {
                "ts_ms": 1234,
                "family": "cross_cex_dex",
                "strategy_id": "s1",
                "stage": "sandbox",
                "reason_code": "generated",
                "payload": {"x": 1},
            }
        ]
    }


def test_risk_memory_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text("{not valid json", encoding="utf-8")

    mem = ExecutionRiskMemory(str(path), horizon_ms=60_000)
    assert mem.snapshot() == {"failures": {}}


def test_risk_memory_sanitizes_malformed_persisted_failures(tmp_path):
    path = tmp_path / "risk.json"
    path.write_text(
        json.dumps(
            {
                "failures": {
                    "route:flashloan_atomic": [1000, "2000", "bad", None],
                    "venue:uni_v3": ["3000"],
                    "pair:WETH/USDC": "bad",
                    "": [1],
                    "broken": [2],
                    7: [4000],
                }
            }
        ),
        encoding="utf-8",
    )

    mem = ExecutionRiskMemory(str(path), horizon_ms=60_000)
    assert mem.snapshot() == {
        "failures": {
            "route:flashloan_atomic": [1000, 2000],
            "venue:uni_v3": [3000],
        }
    }
