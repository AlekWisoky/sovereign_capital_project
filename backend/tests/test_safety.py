
from victor_ai_bot.safety import check_profit_and_repay

def test_safety_repay_fail():
    r = check_profit_and_repay(
        amount_in_wei=100000,
        amount_out_wei=100000,
        min_profit_abs_wei=1,
        min_profit_bps=0,
        flashloan_fee_bps=9,
        gas_cost_wei=0,
    )
    assert not r.ok
    assert r.reason == "does_not_repay_flashloan"

def test_safety_profit_after_costs():
    r = check_profit_and_repay(
        amount_in_wei=1000,
        amount_out_wei=1200,
        min_profit_abs_wei=50,
        min_profit_bps=0,
        flashloan_fee_bps=0,
        gas_cost_wei=100,
    )
    assert r.ok
    assert r.profit_after_costs_wei == 100
