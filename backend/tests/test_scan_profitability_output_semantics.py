from types import SimpleNamespace

from victor_ai_bot.profitability_state import revalidate_profitability_state


class _Leg:
    def __init__(self):
        self.amount_in = "1000"
        self.min_out = "995"


def _cfg():
    return SimpleNamespace(
        safety=SimpleNamespace(minProfitAbs=0, minProfitBps=0),
        execution=SimpleNamespace(flashloan_fee_bps=9),
    )


def _opp():
    return SimpleNamespace(
        route=SimpleNamespace(legs=[_Leg(), _Leg()]),
        min_outs=["995", "995"],
        expected_profit_raw="10",
        expected_profit_usd="0",
        route_id="route-slippage-separation",
        meta={
            "out1": "1005",
            "out2": "1010",
            "gas_cost_estimate_wei": "1",
        },
    )


def test_scan_revalidation_uses_quoted_terminal_output_not_min_out_floor():
    opp = _opp()

    state = revalidate_profitability_state(
        opp,
        _cfg(),
        stage="scan_after_fee_revalidation",
        source="test",
        gas_cost_wei=1,
        quoted_amount_out_wei=1010,
    )

    assert state["revalidated"] is True
    assert state["valid"] is True
    assert state["authoritative"] is True
    assert state["amount_out_wei"] == "1010"
    assert state["gross_profit_wei"] == "10"
    assert state["profit_after_costs_wei"] == "9"


def test_revalidation_without_fresh_quote_keeps_min_out_fallback():
    state = revalidate_profitability_state(
        _opp(),
        _cfg(),
        stage="execution_preflight_gate",
        source="test",
        gas_cost_wei=1,
    )

    assert state["revalidated"] is True
    assert state["valid"] is False
    assert state["reason"] == "does_not_repay_flashloan"
    assert state["amount_out_wei"] == "995"



def test_scan_quoted_amount_ignores_zero_final_leg_and_uses_second_leg():
    from victor_ai_bot.runtime_services.runtime_primary_scan_facade import _resolve_scan_quoted_amount

    assert _resolve_scan_quoted_amount({"out3": "0", "out2": "1010"}) == 1010
    assert _resolve_scan_quoted_amount({"out3": "1015", "out2": "1010"}) == 1015
    assert _resolve_scan_quoted_amount({"out3": "0", "out2": "0"}) is None
