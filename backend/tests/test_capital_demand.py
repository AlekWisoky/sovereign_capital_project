from types import SimpleNamespace

from victor_ai_bot.runtime_services.capital_demand import compose_capital_demand


def _opp(*, family="flashloan_atomic", source="bankroll", notional=100.0):
    return SimpleNamespace(
        strategy="",
        capital_required_usd=notional,
        loan_source=source,
        meta={"strategy_family": family, "capital_source": source},
    )


def test_demand_uses_capital_engine_as_bankroll_authority():
    out = compose_capital_demand(
        [_opp(notional=500.0)],
        capital_engine_state={
            "capital_engine": {
                "deployable_bankroll_wei": 1_000,
                "family_allocations_wei": {"flashloan_atomic": 800},
            }
        },
        internal_prime_state={
            "stateReady": True,
            "capacityUsd": 10_000.0,
            "borrowedUsd": 2_000.0,
        },
        wealth_goal_state={"state": {"aggressivenessCap": 0.8}},
    )

    assert out.requested_notional_usd == 500.0
    assert out.authorized_bankroll_wei == 800
    assert out.family_caps_wei["flashloan_atomic"] == 640
    assert out.goal_aggressiveness_cap == 0.8


def test_internal_prime_headroom_blocks_prime_family_without_state_truth():
    out = compose_capital_demand(
        [_opp(family="prime_arb", source="internal_prime", notional=1_000.0)],
        capital_engine_state={
            "capital_engine": {
                "deployable_bankroll_wei": 5_000,
                "family_allocations_wei": {"prime_arb": 4_000},
            }
        },
        internal_prime_state={
            "stateReady": False,
            "capacityUsd": 0.0,
            "borrowedUsd": 0.0,
        },
        wealth_goal_state={"state": {"aggressivenessCap": 1.0}},
    )

    assert out.family_caps_wei["prime_arb"] == 0
    assert "prime_family_blocked:prime_arb" in out.reason_codes


def test_prime_headroom_is_ratio_not_added_to_bankroll():
    out = compose_capital_demand(
        [_opp(family="prime_arb", source="internal_prime", notional=1_000.0)],
        capital_engine_state={
            "capital_engine": {
                "deployable_bankroll_wei": 10_000,
                "family_allocations_wei": {"prime_arb": 8_000},
            }
        },
        internal_prime_state={
            "stateReady": True,
            "capacityUsd": 1_000_000.0,
            "borrowedUsd": 250_000.0,
        },
        wealth_goal_state={"state": {"aggressivenessCap": 1.0}},
    )

    assert out.authorized_bankroll_wei == 10_000
    assert out.prime_headroom_ratio == 0.75
    assert out.family_caps_wei["prime_arb"] == 6_000
