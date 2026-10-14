from types import SimpleNamespace

from victor_ai_bot.arb_engine import _record_size_economic_diagnostic
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    _build_size_economic_matrix,
    _diagnostic_size_probe_candidates,
    _size_matrix_selection,
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
        "economic_after_cost_profit_wei": "960811652699",
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
        "gas_cost_conversion_available": True,
        "gross_minus_flashloan_fee_wei": "1770811652699",
        "gross_minus_flashloan_fee_minus_gas_wei": "960811652699",
        "repayment_valid": True,
        "diagnostic_only": True,
    }]
    assert matrix[0]["selected_route_id"] == ""
    assert matrix[0]["selected_after_cost_profit_wei"] == ""
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
    assert by_route["route-real-loss"]["economic_after_cost_profit_wei"] == "-18350000000000"


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


def test_missing_gas_conversion_is_upper_bound_not_economic_optimum():
    metrics = {}
    _record_size_economic_diagnostic(
        metrics,
        route_id="route-unknown-gas",
        amount_in=1_000,
        gross_profit_wei=-100,
        flashloan_fee_wei=9,
        gas_cost_wei=500,
        gas_cost_profit_token_wei=None,
        reason="non_positive_gross_profit",
    )
    _record_size_economic_diagnostic(
        metrics,
        route_id="route-known-gas",
        amount_in=1_000,
        gross_profit_wei=-300,
        flashloan_fee_wei=10,
        gas_cost_wei=500,
        gas_cost_profit_token_wei=190,
        reason="non_positive_gross_profit",
    )

    matrix = _build_size_economic_matrix([{
        "amount_in": 1_000,
        "two": [],
        "three": [],
        "two_metrics": {"size_economic_diagnostics": metrics["size_economic_diagnostics"]},
        "three_metrics": {},
    }])

    row = matrix[0]
    # The unknown route's gross-minus-fee upper bound is less negative, but its
    # actual net is unknown. It must never displace the fully converted estimate.
    assert row["economic_optimum_route_id"] == "route-known-gas"
    assert row["economic_optimum_after_cost_profit_wei"] == "-500"
    assert row["economic_optimum_status"] == "signed_after_cost_diagnostic"
    assert row["economic_upper_bound_route_id"] == "route-unknown-gas"
    assert row["economic_upper_bound_after_flashloan_fee_wei"] == "-109"
    assert row["economic_optimum_route_id"] == "route-known-gas"

    # If no dimensionally valid signed estimate exists, the optimum P&L is
    # unknown/empty rather than fabricated as zero. Here the known converted
    # diagnostic is the signed optimum, so it must remain -500.
    assert row["economic_optimum_after_cost_profit_wei"] == "-500"

    candidates = {item["route_id"]: item for item in row["candidates"]}
    unknown = candidates["route-unknown-gas"]
    assert unknown["gas_cost_conversion_available"] is False
    assert unknown["after_cost_profit_wei"] == ""
    assert unknown["economic_after_cost_profit_wei"] == ""
    assert unknown["gross_minus_flashloan_fee_upper_bound_wei"] == "-109"
    assert unknown["after_cost_profit_is_upper_bound"] is True

    upper_only_matrix = _build_size_economic_matrix([{
        "amount_in": 1_000,
        "two": [],
        "three": [],
        "two_metrics": {
            "size_economic_diagnostics": [
                metrics["size_economic_diagnostics"][0],
            ]
        },
        "three_metrics": {},
    }])
    upper_only = upper_only_matrix[0]
    assert upper_only["selection_basis"] == "gross_profit_upper_bound_only"
    assert upper_only["economic_optimum_status"] == "upper_bound_only_gas_conversion_unavailable"
    assert upper_only["economic_optimum_route_id"] == ""
    assert upper_only["economic_optimum_after_cost_profit_wei"] == ""
    assert upper_only["economic_optimum_executable"] is False
    assert upper_only["economic_upper_bound_route_id"] == "route-unknown-gas"
    assert upper_only["selected_after_cost_profit_wei"] == ""



def test_diagnostic_routes_are_rehydrated_only_with_exact_quote_parameters():
    route_id = "0x" + "ab" * 32
    evidence = [{
        "route_id": route_id,
        "amount_in": "1000",
        "gross_profit_wei": "-5",
        "flashloan_fee_wei": "3",
        "gas_cost_conversion_available": False,
        "diagnostic_only": True,
        "reason": "non_positive_gross_profit",
        "legs": [
            {
                "dex": "univ3",
                "venue": "0xrouter",
                "token_in": "0x" + "11" * 20,
                "token_out": "0x" + "22" * 20,
                "amount_in": "1000",
                "quoted_amount_out": "1200",
                "min_out": "1180",
                "data": "0x000000",
                "edge_params": {"fee": 500, "pool": "0x" + "33" * 20},
                "quote_meta": {"fee": 500},
            },
            {
                "dex": "univ3",
                "venue": "0xrouter",
                "token_in": "0x" + "22" * 20,
                "token_out": "0x" + "11" * 20,
                "amount_in": "1200",
                "quoted_amount_out": "995",
                "min_out": "970",
                "data": "0x000bb8",
                "edge_params": {"fee": 3000, "pool": "0x" + "44" * 20},
                "quote_meta": {"fee": 3000},
            },
        ],
    }]
    candidates = _diagnostic_size_probe_candidates(
        evidence,
        chain_name="ethereum",
        excluded_route_ids=set(),
        max_candidates=1,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.route_id == route_id
    assert candidate.can_execute is False
    assert candidate.meta["diagnostic_only"] is True
    assert candidate.meta["size_probe_diagnostic_only"] is True
    assert candidate.meta["route_edge_params"] == [
        {"fee": 500, "pool": "0x" + "33" * 20},
        {"fee": 3000, "pool": "0x" + "44" * 20},
    ]
    assert [leg.data for leg in candidate.route.legs] == ["0x000000", "0x000bb8"]

    # Old/incomplete diagnostic rows are not reconstructed with guessed venue
    # parameters or empty encoded calldata.
    incomplete = {
        **evidence[0],
        "route_id": "incomplete-route",
        "legs": [{**evidence[0]["legs"][0]}, {**evidence[0]["legs"][1]}],
    }
    incomplete["legs"][1].pop("edge_params")
    assert _diagnostic_size_probe_candidates(
        [incomplete],
        chain_name="ethereum",
        excluded_route_ids=set(),
        max_candidates=1,
    ) == []


def test_positive_size_matrix_selection_requires_all_profitability_gates():
    base = {
        "route_id": "route-trusted-positive",
        "after_cost_profit_wei": "10",
        "economic_after_cost_profit_wei": "10",
        "revalidated": True,
        "authoritative": True,
        "valid": True,
        "repayment_valid": True,
        "gas_cost_conversion_available": True,
    }
    selected, _economic = _size_matrix_selection([base])
    assert selected is base

    for field, invalid_value in (
        ("revalidated", False),
        ("authoritative", False),
        ("valid", False),
        ("repayment_valid", False),
        ("gas_cost_conversion_available", False),
    ):
        rejected = {**base, field: invalid_value}
        selected, _economic = _size_matrix_selection([rejected])
        assert selected is None, field
