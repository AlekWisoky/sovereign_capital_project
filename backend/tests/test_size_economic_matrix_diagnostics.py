from types import SimpleNamespace

from victor_ai_bot.arb_engine import _record_size_economic_diagnostic
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    _build_size_economic_matrix,
)


def test_size_economic_matrix_preserves_gross_rejected_diagnostics():
    rejected = {
        "route_id": "route-near-miss",
        "amount_in": "5000000000000000",
        "amount_out_wei": "5001786893695962",
        "gross_profit_wei": "1786893695962",
        "flashloan_fee_wei": "16082043263",
        "gas_cost_wei": "900000000000",
        "gas_cost_profit_token_wei": "810000000000",
        "after_cost_profit_wei": "0",
        "revalidated": False,
        "authoritative": False,
        "reason": "non_positive_gross_profit",
    }

    matrix = _build_size_economic_matrix(
        [{
            "amount_in": 5_000_000_000_000_000,
            "two": [],
            "three": [],
            "two_metrics": {
                "quote_requests": 3,
                "quote_successes": 3,
                "size_economic_diagnostics": [rejected],
            },
            "three_metrics": {},
        }]
    )

    assert len(matrix) == 1
    assert matrix[0]["amount_in"] == "5000000000000000"
    assert matrix[0]["quote_requests"] == 3
    assert matrix[0]["selection_basis"] == "gross_profit_diagnostic_only"
    assert matrix[0]["candidates"] == [{
        **rejected,
        "gross_minus_flashloan_fee_wei": "1770811652699",
        "gross_minus_flashloan_fee_minus_gas_wei": "960811652699",
        "repayment_valid": True,
        "diagnostic_only": True,
    }]
    assert matrix[0]["selected_route_id"] == ""
    assert matrix[0]["selected_after_cost_profit_wei"] == "0"
    assert matrix[0]["candidates"][0]["amount_out_wei"] == "5001786893695962"
    assert matrix[0]["candidates"][0]["gas_cost_profit_token_wei"] == "810000000000"


def test_size_economic_matrix_models_non_repay_signed_economics():
    non_repay = {
        "route_id": "route-non-repay",
        "amount_in": "15000000000000000",
        "amount_out_wei": "15000039805733327",
        "gross_profit_wei": "39805733327",
        "flashloan_fee_wei": "13500000000000",
        "gas_cost_wei": "300000000000",
        "gas_cost_profit_token_wei": "2568984000000",
        "after_cost_profit_wei": "-1",
        "revalidated": True,
        "authoritative": False,
        "reason": "does_not_repay_flashloan",
    }
    actual_loss = {
        "route_id": "route-real-loss",
        "amount_in": "20000000000000000",
        "amount_out_wei": "19999900000000000",
        "gross_profit_wei": "-100000000000",
        "flashloan_fee_wei": "18000000000000",
        "gas_cost_wei": "300000000000",
        "gas_cost_profit_token_wei": "250000000000",
        "after_cost_profit_wei": "-18250000000000",
        "revalidated": False,
        "authoritative": False,
        "reason": "profit_after_costs_not_positive",
    }

    matrix = _build_size_economic_matrix([{
        "amount_in": 15_000_000_000_000_000,
        "two": [],
        "three": [],
        "two_metrics": {
            "quote_requests": 2,
            "quote_successes": 2,
            "size_economic_diagnostics": [non_repay, actual_loss],
        },
        "three_metrics": {},
    }])

    row = matrix[0]
    assert row["economic_optimum_route_id"] == "route-non-repay"
    assert row["economic_optimum_after_cost_profit_wei"] == "-16029178266673"
    assert row["economic_optimum_executable"] is False
    by_route = {candidate["route_id"]: candidate for candidate in row["candidates"]}
    assert by_route["route-non-repay"]["repayment_valid"] is False
    assert by_route["route-non-repay"]["gross_minus_flashloan_fee_wei"] == "-13460194266673"
    assert by_route["route-non-repay"]["gross_minus_flashloan_fee_minus_gas_wei"] == "-16029178266673"
    assert by_route["route-non-repay"]["after_cost_profit_wei"] == "-1"
    assert by_route["route-non-repay"]["economic_after_cost_profit_wei"] == "-16029178266673"
    assert by_route["route-real-loss"]["economic_after_cost_profit_wei"] == "-18250000000000"


def test_size_economic_diagnostics_are_bounded_per_route_not_global_top_n():
    metrics = {}
    for route_id in ("route-a", "route-b"):
        for i in range(20):
            _record_size_economic_diagnostic(
                metrics,
                route_id=route_id,
                amount_in=i + 1,
                gross_profit_wei=i,
                flashloan_fee_wei=0,
                gas_cost_wei=0,
                reason="non_positive_gross_profit",
            )

    candidates = metrics["size_economic_diagnostics"]
    assert len(candidates) == 32
    counts = {route_id: 0 for route_id in ("route-a", "route-b")}
    for candidate in candidates:
        counts[candidate["route_id"]] += 1
    assert counts == {"route-a": 16, "route-b": 16}
