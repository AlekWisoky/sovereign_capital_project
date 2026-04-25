from types import SimpleNamespace

from victor_ai_bot.portfolio_optimizer import candidates_from_opps


class BadStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


class IterableBug:
    def __iter__(self):
        raise RuntimeError("iter boom")


class Opp:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_candidates_from_opps_handles_expected_meta_coercion_failures():
    opp = Opp(
        id="opp-1",
        route_id="route-1",
        meta={
            "brain": {"ev_wei": object()},
            "safety": {"gas_cost_wei": object()},
            "pool_keys": object(),
            "strategy_family": "flash",
            "engine_type": "v1",
            "chain": "base",
            "capital_required_wei": object(),
            "token_path": object(),
            "venues": object(),
        },
    )
    [cand] = candidates_from_opps([opp])
    assert cand.opp_id == "opp-1"
    assert cand.route_id == "route-1"
    assert cand.ev_wei == 0
    assert cand.gas_cost_wei == 0
    assert cand.conflict_keys == []
    assert cand.token_keys == []
    assert cand.venue_keys == []
    assert cand.capital_required_wei == 0
    assert cand.path_id == ":route-1"


class RouteIdTypeErrorOpp:
    meta = {"brain": {"ev_wei": "1"}}

    @property
    def route_id(self):
        raise TypeError("bad route")


def test_candidates_from_opps_skips_expected_bad_opportunity_shape():
    assert candidates_from_opps([RouteIdTypeErrorOpp()]) == []


def test_candidates_from_opps_does_not_swallow_unexpected_programmer_bugs():
    opp = Opp(
        id=BadStr(),
        route_id="route-1",
        meta={
            "brain": {"ev_wei": "7"},
            "pool_keys": IterableBug(),
        },
    )
    try:
        candidates_from_opps([opp])
    except RuntimeError as exc:
        assert "iter boom" in str(exc) or "boom" in str(exc)
    else:
        raise AssertionError("unexpected RuntimeError should propagate")


def test_candidates_from_opps_builds_candidate_for_valid_opp():
    opp = Opp(
        id="opp-2",
        route_id="route-2",
        meta={
            "brain": {"ev_wei": "15"},
            "safety": {"gas_cost_wei": "3"},
            "pool_keys": ["p1", None, "p2"],
            "route_family": "corr-a",
            "strategy_family": "flash",
            "engine_type": "core",
            "chain": "eth",
            "token_path": ["WETH", "USDC"],
            "venues": ["uni", "curve"],
            "capital_required_wei": "1000",
        },
    )
    [cand] = candidates_from_opps([opp])
    assert cand.ev_wei == 15
    assert cand.gas_cost_wei == 3
    assert cand.conflict_keys == ["p1", "p2"]
    assert cand.correlation_key == "corr-a"
    assert cand.token_keys == ["WETH", "USDC"]
    assert cand.venue_keys == ["uni", "curve"]
    assert cand.path_id == "corr-a:route-2"
