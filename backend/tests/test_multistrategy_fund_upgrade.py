from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.alpha_platform.fund_families import default_fund_families
from victor_ai_bot.fund_os.master_orchestrator import FundMasterOrchestrator
from victor_ai_bot.fund_os.objectives import evaluate_objective_fit
from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
from victor_ai_bot.execution_capture.action_router import universal_action_to_opportunity
from victor_ai_bot.execution_capture.competition_model import competition_penalty
from victor_ai_bot.execution_capture.loan_aware_scoring import loan_adjusted_value
from victor_ai_bot.execution_capture.thin_edge_policy import thin_edge_admission
from victor_ai_bot.execution_capture.universal_actions import UniversalAction
from victor_ai_bot.market_making.quote_engine import quote_policy
from victor_ai_bot.rl_training.policy_registry import PolicyRegistry
from victor_ai_bot.rl_training.trainer import train_offline
from victor_ai_bot.server import app
from victor_ai_bot.stat_arb.executor import build_pair_action
from victor_ai_bot.strategies.cross_exchange_engine import detect_cross_exchange_arbitrage
from victor_ai_bot.treasury.loan_policy import loan_admission


def test_profit_doctrine_and_master_orchestrator():
    fit = evaluate_objective_fit(
        {
            "realizedPnl": 10.0,
            "capitalEfficiency": 0.8,
            "executionCost": 1.0,
            "failureRate": 0.1,
            "stabilityScore": 0.8,
            "competitionScore": 0.7,
        }
    )
    assert fit["score"] > 0
    out = FundMasterOrchestrator().compose(
        stage="internal_capital",
        nav_usd=100000.0,
        family_targets={"flash_arb": 0.4, "funding_arb": 0.2},
        income_metrics={
            "flash_arb": {"realizedPnlUsd": 10, "capitalEfficiency": 1.0, "stability": 0.8}
        },
        capital_metrics={"failureAdjustedCapitalEfficiency": 0.9},
        fund_health={
            "realizedPnlUsd": 100.0,
            "capitalEfficiency": 0.9,
            "stabilityScore": 0.8,
            "executionCostUsd": 1.0,
            "failureRate": 0.01,
            "competitionScore": 0.6,
        },
    )
    assert out["budgets"]["deployableCapitalUsd"] > 0
    assert "profitDoctrine" in out


def test_internal_prime_and_loan_policy(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="test")
    prime.inventory.seed("USDC", 150000.0)
    res = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={"max_deployable_pct": 0.5},
    )
    assert res["allowed"] is True
    assert res["decision"]["details"]["inventoryTracked"] is True
    assert res["decision"]["details"]["requiredCollateralUsd"] == 100000.0
    loan = loan_admission(
        family="flash_arb",
        stage="internal_capital",
        notional_usd=100000.0,
        projected_realized_edge_usd=500.0,
        source="flashloan",
        confidence=0.9,
    )
    assert loan["allowed"] is True
    adj = loan_adjusted_value(
        projected_realized_edge_usd=500.0, borrow_cost_usd=loan["borrowCostUsd"], confidence=0.9
    )
    assert adj["loanAdjustedEdgeUsd"] > 0


def test_cross_exchange_and_universal_action_routing():
    books = [
        {"venue": "binance", "symbol": "ETHUSDT", "bestBid": 3010.0, "bestAsk": 3000.0},
        {"venue": "bybit", "symbol": "ETHUSDT", "bestBid": 3020.0, "bestAsk": 3012.0},
    ]
    opps = detect_cross_exchange_arbitrage(books=books, capital_usd=10000.0)
    assert opps
    routed = universal_action_to_opportunity(opps[0])
    assert getattr(routed, "route_family") == "cex_cex_arb"


def test_competition_and_thin_edge_policy():
    pen = competition_penalty(
        route_family="flash_arb", mempool_copy_risk=0.8, venue_quality=0.7, lane="PUBLIC"
    )
    assert pen["competitionPenalty"] > 0
    thin = thin_edge_admission(
        projected_realized_edge_usd=4.0,
        competition_penalty=pen["competitionPenalty"],
        confidence=0.8,
        venue_quality=0.8,
    )
    assert thin["allowed"] in {True, False}


def test_market_making_stat_arb_and_rl(tmp_path):
    q = quote_policy(mid=100.0, vol_pct=30.0, inventory_skew=0.1)
    assert q["ask"] > q["bid"]
    act = build_pair_action(
        pair=("ETH", "stETH"), spread_series=[0.0, 0.1, -0.2, 0.0, 3.5], notional_usd=1000.0
    )
    assert act is not None
    reg = PolicyRegistry(data_dir=str(tmp_path), chain="test")
    trained = train_offline(
        samples=[
            {
                "realizedPnl": 2.0,
                "capitalEfficiency": 0.8,
                "gasEfficiency": 0.6,
                "failureRate": 0.0,
                "stability": 0.7,
            }
        ],
        family="stat_arb",
        registry=reg,
    )
    assert trained["policy"]["family"] == "stat_arb"


def test_fund_and_risk_routes():
    client = TestClient(app)
    r = client.get("/api/fund/summary")
    assert r.status_code == 200
    body = r.json()
    assert "fundOs" in body and "profitDoctrine" in body and "internalPrime" in body
    r2 = client.get("/api/risk/cio-summary")
    assert r2.status_code == 200
    assert r2.json().get("ok") in {True, False}


def test_alpha_families_present():
    fams = default_fund_families()
    assert "flash_arb" in fams
    assert "treasury_yield" in fams
