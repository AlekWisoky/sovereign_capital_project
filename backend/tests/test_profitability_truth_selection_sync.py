from types import SimpleNamespace

from victor_ai_bot.backtest.replay import select_best_trade
from victor_ai_bot.features import build_features
from victor_ai_bot.runtime_services.profitability_truth import (
    inspect_profit_after_costs_truth,
    opportunity_profit_sort_key,
)


class _Leg:
    def __init__(self, *, amount_in: str = "1000", min_out: str = "1100", dex: str = "univ3"):
        self.amount_in = amount_in
        self.min_out = min_out
        self.dex = dex
        self.venue = dex
        self.token_in = "WETH"
        self.token_out = "USDC"


class _Opp(SimpleNamespace):
    pass


def _opp(*, opp_id: str = "opp-1", route_id: str = "route-1", meta: dict | None = None):
    return _Opp(
        id=opp_id,
        route_id=route_id,
        expected_profit_raw="999",
        expected_profit_usd="1.0",
        can_execute=True,
        route=SimpleNamespace(legs=[_Leg()]),
        min_outs=["1100"],
        meta=meta if meta is not None else {},
    )


def test_profitability_truth_prefers_canonical_invalid_contract_over_legacy_positive_values():
    opp = _opp(
        meta={
            "profit_after_costs": "100",
            "safety": {"profit_after_costs_wei": "100", "revalidated": True},
            "profitability": {
                "stage": "search",
                "source": "scan",
                "reason": "profitability_metadata_stale",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "100",
            },
            "post_mutation_revalidation": {
                "reason_code": "route_mutated",
                "profitability": {
                    "stage": "post_mutation_submission_gate",
                    "source": "execution",
                    "reason": "route_mutated",
                    "revalidated": False,
                    "stale": True,
                    "valid": False,
                    "authoritative": False,
                    "profit_after_costs_wei": "100",
                },
            },
        }
    )

    truth = inspect_profit_after_costs_truth(opp)

    assert truth.contract_present is True
    assert truth.verified is False
    assert truth.positive is False
    assert truth.value_wei == 0
    assert truth.reason_code == "route_mutated"


def test_profit_sort_key_does_not_resurrect_stale_contract_with_gross_fallback():
    opp = _opp(
        meta={
            "profit_after_gas_estimate_wei": "555",
            "profitability": {
                "stage": "search",
                "source": "scan",
                "reason": "profitability_metadata_stale",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "444",
            },
            "post_mutation_revalidation": {
                "reason_code": "route_mutated",
                "profitability": {
                    "stage": "post_mutation_submission_gate",
                    "source": "execution",
                    "reason": "route_mutated",
                    "revalidated": False,
                    "stale": True,
                    "valid": False,
                    "authoritative": False,
                    "profit_after_costs_wei": "444",
                },
            },
        }
    )

    bucket, value, _route_id = opportunity_profit_sort_key(opp)

    assert bucket == 0
    assert value == 0


def test_build_features_zeroes_stale_canonical_profitability_truth():
    opp = _opp(
        meta={
            "safety": {
                "profit_after_costs_wei": "77",
                "gas_cost_wei": "2",
                "flashloan_fee_wei": "1",
            },
            "profitability": {
                "stage": "search",
                "source": "scan",
                "reason": "profitability_metadata_stale",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "77",
            },
            "post_mutation_revalidation": {
                "reason_code": "route_mutated",
                "profitability": {
                    "stage": "post_mutation_submission_gate",
                    "source": "execution",
                    "reason": "route_mutated",
                    "revalidated": False,
                    "stale": True,
                    "valid": False,
                    "authoritative": False,
                    "profit_after_costs_wei": "77",
                },
            },
        }
    )

    fv = build_features(opp)

    assert fv.profit_after_costs_wei == 0
    assert fv.gas_cost_wei == 2
    assert fv.flash_fee_wei == 1


def test_select_best_trade_skips_stale_canonical_profitability_even_when_legacy_safety_is_positive():
    stale = _opp(
        opp_id="opp-stale",
        route_id="route-stale",
        meta={
            "safety": {"profit_after_costs_wei": "500"},
            "brain": {"p_success": "0.9"},
            "profitability": {
                "stage": "search",
                "source": "scan",
                "reason": "profitability_metadata_stale",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": "500",
            },
            "post_mutation_revalidation": {
                "reason_code": "route_mutated",
                "profitability": {
                    "stage": "post_mutation_submission_gate",
                    "source": "execution",
                    "reason": "route_mutated",
                    "revalidated": False,
                    "stale": True,
                    "valid": False,
                    "authoritative": False,
                    "profit_after_costs_wei": "500",
                },
            },
        },
    )
    ready = _opp(
        opp_id="opp-ready",
        route_id="route-ready",
        meta={
            "safety": {"profit_after_costs_wei": "200", "revalidated": True},
            "brain": {"p_success": "0.5"},
        },
    )

    best = select_best_trade([stale, ready])

    assert best is not None
    assert best.opportunity_id == "opp-ready"
