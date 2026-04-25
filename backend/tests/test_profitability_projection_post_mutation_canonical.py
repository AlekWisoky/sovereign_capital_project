from types import SimpleNamespace

from victor_ai_bot.profitability_projection import profitability_summary_projection


def test_projection_prefers_canonical_post_mutation_profitability_state_over_legacy_safety():
    opp = SimpleNamespace(
        expected_profit_raw="250",
        expected_profit_usd="12.5",
        meta={
            "profitability_continuity": {"valid": True, "reason": "ok"},
            "safety": {
                "revalidated": True,
                "profit_after_costs_wei": "999",
                "reason": "ok",
            },
            "profitability": {
                "stage": "route_mutation_pending_revalidation",
                "source": "execution_route_plan",
                "reason": "route_mutation_revalidation_required",
                "revalidated": False,
                "stale": True,
                "valid": True,
                "gross_profit_wei": "150",
                "profit_after_costs_wei": "0",
                "continuity": {"valid": True, "reason": "ok"},
            },
        },
    )

    view = profitability_summary_projection(opp)

    assert view["stale"] is True
    assert view["revalidated"] is False
    assert view["displayExpectedProfitRaw"] == "0"
    assert view["displayProfitAfterCostsWei"] == "0"
    assert view["reason"] == "route_mutation_revalidation_required"
    assert view["stage"] == "route_mutation_pending_revalidation"
