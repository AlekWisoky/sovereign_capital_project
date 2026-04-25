from victor_ai_bot.treasury.allocation_engine import allocate_capital
from victor_ai_bot.treasury.reinvestment import reinvestment_policy
from victor_ai_bot.treasury.metrics import capital_efficiency_metrics


def test_capital_buckets_and_family_allocations():
    out = allocate_capital(
        estimated_capital_wei=1_000_000,
        drawdown_pct=3.0,
        regime="balanced",
        aggressiveness_level="MODERATE",
    )
    assert out["deployable_bankroll_wei"] > 0
    assert "flashloan_atomic" in out["family_allocations_wei"]


def test_reinvestment_policy_split():
    out = reinvestment_policy(
        realized_profit_wei=1_000_000, aggressiveness_level="HIGH", auto_reinvest_enabled=True
    )
    assert out["reinvest_wei"] > out["treasury_wei"]


def test_capital_efficiency_metrics():
    out = capital_efficiency_metrics(
        realized_pnl_wei=500_000,
        deployed_capital_wei=2_000_000,
        at_risk_capital_wei=1_000_000,
        gas_cost_wei=100_000,
        utilization_rate=0.75,
        failures=1,
    )
    assert out["return_on_deployed_capital"] > 0
    assert out["idle_capital_ratio"] == 0.25
