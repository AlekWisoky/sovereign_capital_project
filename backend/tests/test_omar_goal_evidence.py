from __future__ import annotations

from datetime import datetime, timedelta, timezone

from victor_ai_bot.omar.goal_evidence import build_goal_evidence_snapshot


def _outcome(ts: datetime, equity: float, realized: float, expected: float = 10.0) -> dict:
    return {
        "ts": ts.isoformat(),
        "equity_usd": equity,
        "realized_pnl_usd": realized,
        "realized_profit_after_gas_usd": realized,
        "expected_profit_after_costs_usd": expected,
        "slippage_bps": 4.0,
        "latency_ms": 120,
        "realized_gas_cost_wei": 10,
        "status": "settled",
    }


def test_goal_evidence_consumes_authoritative_capital_and_settled_outcomes() -> None:
    now = datetime.now(timezone.utc)
    outcomes = [
        _outcome(now - timedelta(days=730), 1000.0, 10.0),
        _outcome(now - timedelta(days=365), 1100.0, 90.0),
        _outcome(now, 1200.0, 100.0),
    ]
    snapshot = build_goal_evidence_snapshot(
        settled_outcomes=outcomes,
        capital_engine_state={"current_capital_usd": 1200.0},
        internal_prime_state={"utilization_ratio": 0.25, "headroom_wei": 5000},
        treasury_state={"reserves_usd": 800.0},
        strategy_state={"capacity_usd": 1500.0},
        omar_state={"confidence": 0.82},
        wealth_goal={"target_usd": 2000.0, "timeframe_days": 365, "aggressiveness": 1.0},
    )

    assert snapshot.current_capital == 1200.0
    assert snapshot.stable_cagr > 0.0
    assert 0.0 <= snapshot.drawdown <= 1.0
    assert 0.0 <= snapshot.execution_realism <= 1.0
    assert snapshot.strategy_capacity == 1500.0
    assert "utilization=0.2500" in snapshot.prime_utilization_capacity
    assert snapshot.treasury_reserves == 800.0
    assert snapshot.omar_confidence == 0.82
    assert snapshot.recommended_goal >= snapshot.current_capital


def test_goal_evidence_fails_closed_when_authoritative_evidence_is_missing() -> None:
    snapshot = build_goal_evidence_snapshot(
        settled_outcomes=[],
        capital_engine_state={},
        internal_prime_state={},
        treasury_state={},
        strategy_state={},
        omar_state={},
        wealth_goal={"target_usd": 1000000.0, "timeframe_days": 30},
    )

    assert snapshot.current_capital == 0.0
    assert snapshot.stable_cagr == 0.0
    assert snapshot.risk_posture == "defensive"
    assert "capital_unavailable" in snapshot.block_reasons
    assert "no_settled_outcome_evidence" in snapshot.block_reasons
    assert "strategy_capacity_unavailable" in snapshot.block_reasons
    assert "treasury_reserves_unavailable" in snapshot.block_reasons
    assert "omar_confidence_low" in snapshot.block_reasons
    assert snapshot.recommended_goal == 0.0


def test_recommendation_contract_has_exact_required_fields() -> None:
    snapshot = build_goal_evidence_snapshot(
        settled_outcomes=[
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "equity_usd": 1000.0,
                "realized_pnl_usd": 10.0,
                "expected_profit_after_costs_usd": 10.0,
                "slippage_bps": 2.0,
                "latency_ms": 50,
                "realized_gas_cost_wei": 1,
            }
        ],
        capital_engine_state={"current_capital_usd": 1000.0},
        internal_prime_state={"utilization_ratio": 0.1, "capacity_wei": 10000},
        treasury_state={"reserves_usd": 1000.0},
        strategy_state={"capacity_usd": 2000.0},
        omar_state={"confidence": 0.9},
    )
    contract = snapshot.to_contract()

    assert list(contract) == [
        "Current capital",
        "Stable CAGR",
        "Drawdown",
        "Execution realism",
        "Strategy capacity",
        "Prime utilization/capacity",
        "Treasury reserves",
        "OMAR confidence",
        "Recommended goal",
        "Next goal",
        "Risk posture",
        "Block reasons",
    ]
