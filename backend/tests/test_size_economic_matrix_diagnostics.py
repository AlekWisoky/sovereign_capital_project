from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    _build_size_economic_matrix,
)


def test_size_economic_matrix_preserves_gross_rejected_diagnostics():
    rejected = {
        "route_id": "route-near-miss",
        "gross_profit_wei": "1786893695962",
        "flashloan_fee_wei": "16082043263",
        "gas_cost_wei": "900000000000",
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
        "diagnostic_only": True,
    }]
    assert matrix[0]["selected_route_id"] == ""
    assert matrix[0]["selected_after_cost_profit_wei"] == "0"
