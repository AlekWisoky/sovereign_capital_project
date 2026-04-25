from types import SimpleNamespace
from victor_ai_bot.portfolio_optimizer import Candidate, candidates_from_opps, select_portfolio


def test_portfolio_non_conflicting_and_budget():
    c1 = Candidate(opp_id="a", route_id="r1", ev_wei=100, gas_cost_wei=10, conflict_keys=["k1"])
    c2 = Candidate(
        opp_id="b", route_id="r2", ev_wei=90, gas_cost_wei=10, conflict_keys=["k1"]
    )  # conflicts
    c3 = Candidate(
        opp_id="c", route_id="r3", ev_wei=80, gas_cost_wei=15, conflict_keys=["k2"]
    )  # ok
    picked = select_portfolio([c1, c2, c3], gas_budget_remaining_wei=25, max_trades=3)
    ids = [p.opp_id for p in picked]
    assert "a" in ids
    assert "b" not in ids  # conflict
    assert "c" in ids


def test_portfolio_budget_caps():
    c1 = Candidate(opp_id="a", route_id="r1", ev_wei=100, gas_cost_wei=30, conflict_keys=["k1"])
    c2 = Candidate(opp_id="b", route_id="r2", ev_wei=90, gas_cost_wei=10, conflict_keys=["k2"])
    picked = select_portfolio([c1, c2], gas_budget_remaining_wei=15, max_trades=2)
    assert [p.opp_id for p in picked] == ["b"]


def test_portfolio_prefers_capital_efficient_trade_when_ev_and_gas_are_equal():
    c1 = Candidate(
        opp_id="capital-heavy",
        route_id="r1",
        ev_wei=100,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        capital_required_wei=1_000,
    )
    c2 = Candidate(
        opp_id="capital-efficient",
        route_id="r2",
        ev_wei=100,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        capital_required_wei=100,
    )
    picked = select_portfolio([c1, c2], gas_budget_remaining_wei=10, max_trades=1)
    assert [p.opp_id for p in picked] == ["capital-efficient"]


def test_portfolio_penalizes_crowded_token_and_venue_overlap():
    first = Candidate(
        opp_id="first",
        route_id="r1",
        ev_wei=120,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        token_keys=["WETH", "USDC"],
        venue_keys=["uni"],
        strategy_family="flashloan_atomic",
        engine_type="core",
    )
    crowded = Candidate(
        opp_id="crowded",
        route_id="r2",
        ev_wei=110,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        token_keys=["WETH", "USDC"],
        venue_keys=["uni"],
        strategy_family="flashloan_atomic",
        engine_type="core",
    )
    diversified = Candidate(
        opp_id="diversified",
        route_id="r3",
        ev_wei=108,
        gas_cost_wei=10,
        conflict_keys=["k3"],
        token_keys=["WBTC", "USDT"],
        venue_keys=["curve"],
        strategy_family="funding_arb",
        engine_type="alt",
    )
    picked = select_portfolio(
        [first, crowded, diversified], gas_budget_remaining_wei=20, max_trades=2
    )
    assert [p.opp_id for p in picked] == ["first", "diversified"]


class _RouteLeg:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Opp:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_candidates_from_opps_derives_overlap_but_not_capital_from_route_amount_in_when_meta_sparse():
    opp = _Opp(
        id="opp-route",
        route_id="route-xyz",
        chain="base",
        strategy="flashloan_atomic",
        route=SimpleNamespace(
            legs=[
                _RouteLeg(
                    venue="uni_v3",
                    dex="univ3",
                    token_in="WETH",
                    token_out="USDC",
                    amount_in="1500",
                    data="3000",
                ),
                _RouteLeg(
                    venue="curve_3pool",
                    dex="curve",
                    token_in="USDC",
                    token_out="DAI",
                    amount_in="1490",
                    data="tri",
                ),
            ]
        ),
        meta={"brain": {"ev_wei": "10"}, "safety": {"gas_cost_wei": "2"}},
    )
    [cand] = candidates_from_opps([opp])
    assert cand.chain == "base"
    assert cand.strategy_family == "flashloan_atomic"
    assert cand.capital_required_wei == 0
    assert cand.token_keys == ["WETH", "USDC", "DAI"]
    assert cand.venue_keys == ["uni_v3", "curve_3pool"]
    assert cand.conflict_keys == [
        "routeleg:uni_v3:USDC:WETH:3000",
        "routeleg:curve_3pool:DAI:USDC:tri",
    ]
    assert cand.path_id == ":route-xyz"


def test_route_derived_overlap_signals_enable_diversified_second_pick():
    first = _Opp(
        id="first",
        route_id="r1",
        chain="eth",
        strategy="flashloan_atomic",
        route=SimpleNamespace(
            legs=[_RouteLeg(venue="uni", token_in="WETH", token_out="USDC", amount_in="1000")]
        ),
        meta={"brain": {"ev_wei": "120", "action": "trade"}, "safety": {"gas_cost_wei": "10"}},
        can_execute=True,
    )
    crowded = _Opp(
        id="crowded",
        route_id="r2",
        chain="eth",
        strategy="flashloan_atomic",
        route=SimpleNamespace(
            legs=[_RouteLeg(venue="uni", token_in="USDC", token_out="WETH", amount_in="1000")]
        ),
        meta={"brain": {"ev_wei": "110", "action": "trade"}, "safety": {"gas_cost_wei": "10"}},
        can_execute=True,
    )
    diversified = _Opp(
        id="diversified",
        route_id="r3",
        chain="arb",
        strategy="funding_arb",
        route=SimpleNamespace(
            legs=[_RouteLeg(venue="curve", token_in="WBTC", token_out="USDT", amount_in="1000")]
        ),
        meta={"brain": {"ev_wei": "108", "action": "trade"}, "safety": {"gas_cost_wei": "10"}},
        can_execute=True,
    )
    cands = candidates_from_opps([first, crowded, diversified])
    picked = select_portfolio(cands, gas_budget_remaining_wei=20, max_trades=2)
    assert [p.opp_id for p in picked] == ["first", "diversified"]


def test_portfolio_prefers_more_reliable_trade_when_ev_is_close():
    less_reliable = Candidate(
        opp_id="less-reliable",
        route_id="r1",
        ev_wei=110,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        p_success=0.70,
        quality_edge_wei=100,
    )
    more_reliable = Candidate(
        opp_id="more-reliable",
        route_id="r2",
        ev_wei=108,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        p_success=0.95,
        quality_edge_wei=108,
    )
    picked = select_portfolio(
        [less_reliable, more_reliable], gas_budget_remaining_wei=10, max_trades=1
    )
    assert [p.opp_id for p in picked] == ["more-reliable"]


def test_candidates_from_opps_derives_execution_quality_signals_from_brain_and_route_plan():
    opp = _Opp(
        id="opp-quality",
        route_id="route-quality",
        chain="base",
        strategy="flashloan_atomic",
        route=SimpleNamespace(
            legs=[
                _RouteLeg(venue="uni_v3", token_in="WETH", token_out="USDC", amount_in="2000"),
            ]
        ),
        meta={
            "brain": {"ev_wei": "12", "ev_score_wei": "9", "p_success": "0.88"},
            "safety": {"gas_cost_wei": "3"},
            "execution_route_plan": {
                "split": [
                    {"venue": "uni_v3", "share": 0.6, "venue_quality": 0.90},
                    {"venue": "curve", "share": 0.4, "venue_quality": 0.70},
                ]
            },
        },
    )
    [cand] = candidates_from_opps([opp])
    assert cand.p_success == 0.88
    assert cand.quality_edge_wei == 9
    assert cand.route_quality_score == 0.8


def test_candidates_from_opps_skips_explicitly_invalid_route_plan():
    invalid = _Opp(
        id="invalid-route",
        route_id="r-invalid",
        meta={
            "brain": {"ev_wei": "100", "action": "trade"},
            "safety": {"gas_cost_wei": "10"},
            "execution_route_plan": {
                "executable": False,
                "route_invalid_causes": ["leg:0:venue-a:invalid"],
            },
        },
    )
    valid = _Opp(
        id="valid-route",
        route_id="r-valid",
        meta={
            "brain": {"ev_wei": "80", "action": "trade"},
            "safety": {"gas_cost_wei": "10"},
        },
    )
    cands = candidates_from_opps([invalid, valid])
    assert [c.opp_id for c in cands] == ["valid-route"]


def test_candidates_from_opps_skips_degraded_execution_route_runtime():
    opp = _Opp(
        id="runtime-degraded",
        route_id="r-runtime",
        meta={
            "brain": {"ev_wei": "100", "action": "trade"},
            "safety": {"gas_cost_wei": "10"},
            "execution_route_runtime": {
                "profit": {"ok": False, "code": "plan_profit_after_costs_mismatch"}
            },
        },
    )
    assert candidates_from_opps([opp]) == []


def test_portfolio_respects_total_capital_budget():
    c1 = Candidate(
        opp_id="capital-heavy",
        route_id="r1",
        ev_wei=120,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        capital_required_wei=2_000,
    )
    c2 = Candidate(
        opp_id="capital-fit",
        route_id="r2",
        ev_wei=100,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        capital_required_wei=900,
    )
    picked = select_portfolio(
        [c1, c2],
        gas_budget_remaining_wei=20,
        max_trades=1,
        capital_budget_remaining_wei=1_000,
    )
    assert [p.opp_id for p in picked] == ["capital-fit"]


def test_portfolio_respects_family_capital_budget():
    c1 = Candidate(
        opp_id="family-over",
        route_id="r1",
        ev_wei=120,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        capital_required_wei=2_000,
        strategy_family="flashloan_atomic",
    )
    c2 = Candidate(
        opp_id="family-fit",
        route_id="r2",
        ev_wei=100,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        capital_required_wei=900,
        strategy_family="flashloan_atomic",
    )
    picked = select_portfolio(
        [c1, c2],
        gas_budget_remaining_wei=20,
        max_trades=1,
        family_capital_remaining_wei={"flashloan_atomic": 1_000},
    )
    assert [p.opp_id for p in picked] == ["family-fit"]


def test_candidates_from_opps_converts_capital_required_usd_to_budget_wei():
    opp = _Opp(
        id="opp-usd-capital",
        route_id="route-usd-capital",
        chain="base",
        strategy="cross_cex_dex",
        capital_required_usd=1250.25,
        meta={"brain": {"ev_wei": "12"}, "safety": {"gas_cost_wei": "3"}},
    )
    [cand] = candidates_from_opps([opp])
    assert cand.strategy_family == "cross_cex_dex"
    assert cand.capital_required_wei == 1250250000000000000000


def test_portfolio_normalizes_family_capital_aliases_fail_closed():
    canonical = Candidate(
        opp_id="canonical",
        route_id="r1",
        ev_wei=120,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        capital_required_wei=900,
        strategy_family="flashloan_atomic",
    )
    alias = Candidate(
        opp_id="alias",
        route_id="r2",
        ev_wei=100,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        capital_required_wei=900,
        strategy_family="flash_arb",
    )
    picked = select_portfolio(
        [canonical, alias],
        gas_budget_remaining_wei=20,
        max_trades=2,
        family_capital_remaining_wei={"flash_arb": 1_200, "flashloan_atomic": 1_000},
    )
    assert [p.opp_id for p in picked] == ["canonical"]


def test_select_portfolio_blocks_unknown_capital_when_budget_truth_is_active():
    unknown_capital = Candidate(
        opp_id="unknown-capital",
        route_id="r-unknown",
        ev_wei=150,
        gas_cost_wei=10,
        conflict_keys=["k1"],
        capital_required_wei=0,
        strategy_family="flashloan_atomic",
    )
    explicit_capital = Candidate(
        opp_id="explicit-capital",
        route_id="r-explicit",
        ev_wei=120,
        gas_cost_wei=10,
        conflict_keys=["k2"],
        capital_required_wei=900,
        strategy_family="flashloan_atomic",
    )

    picked = select_portfolio(
        [unknown_capital, explicit_capital],
        gas_budget_remaining_wei=20,
        max_trades=2,
        capital_budget_remaining_wei=1_000,
        family_capital_remaining_wei={"flashloan_atomic": 1_000},
    )

    assert [p.opp_id for p in picked] == ["explicit-capital"]


def test_candidates_from_opps_uses_notional_usd_fallback_for_capital_truth():
    opp = _Opp(
        id="opp-notional-usd",
        route_id="route-notional-usd",
        chain="base",
        strategy="funding_arb",
        route=SimpleNamespace(
            legs=[_RouteLeg(venue="binance", token_in="BTC", token_out="BTC", amount_in="1")]
        ),
        meta={
            "brain": {"ev_wei": "12"},
            "safety": {"gas_cost_wei": "3"},
            "notional_usd": "2500.25",
        },
    )
    [cand] = candidates_from_opps([opp])
    assert cand.capital_required_wei == 2500250000000000000000


def test_candidates_from_opps_rounds_up_numeric_string_gas_and_capital_requirements():
    opp = _Opp(
        id="opp-numeric-strings",
        route_id="route-numeric-strings",
        chain="base",
        strategy="flashloan_atomic",
        route=SimpleNamespace(
            legs=[
                _RouteLeg(
                    venue="uni_v3",
                    token_in="WETH",
                    token_out="USDC",
                    amount_in="1000.1",
                ),
            ]
        ),
        meta={
            "brain": {"ev_wei": "12.9", "ev_score_wei": "11.4"},
            "safety": {"gas_cost_wei": "3.1"},
            "capital_required_wei": "1000.1",
        },
    )
    [cand] = candidates_from_opps([opp])
    assert cand.ev_wei == 12
    assert cand.quality_edge_wei == 11
    assert cand.gas_cost_wei == 4
    assert cand.capital_required_wei == 1001


def test_select_portfolio_fail_closed_for_stringified_budget_and_candidate_fields():
    blocked = Candidate(
        opp_id="blocked",
        route_id="r-blocked",
        ev_wei="120.9",
        gas_cost_wei="10.1",
        conflict_keys=["k1"],
        capital_required_wei="1000.1",
        strategy_family="flash_arb",
    )
    allowed = Candidate(
        opp_id="allowed",
        route_id="r-allowed",
        ev_wei="100.1",
        gas_cost_wei="10.0",
        conflict_keys=["k2"],
        capital_required_wei="900.0",
        strategy_family="flashloan_atomic",
    )

    picked = select_portfolio(
        [blocked, allowed],
        gas_budget_remaining_wei=20,
        max_trades=2,
        capital_budget_remaining_wei="1000.0",
        family_capital_remaining_wei={"flash_arb": "900.0"},
    )

    assert [p.opp_id for p in picked] == ["allowed"]
