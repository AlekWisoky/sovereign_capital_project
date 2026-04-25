
from victor_ai_bot.bankroll import BankrollManager, BankrollConfig

def test_bankroll_no_reinvest():
    m = BankrollManager(BankrollConfig(auto_reinvest_enabled=False, reinvest_rate_pct=50, base_borrow_amount_wei=1000, max_borrow_amount_wei=0))
    assert m.next_amount_in() == 1000
    m.record_trade(success=True, realized_profit_after_gas_wei=500)
    assert m.next_amount_in() == 1000

def test_bankroll_with_reinvest_and_cap():
    m = BankrollManager(BankrollConfig(auto_reinvest_enabled=True, reinvest_rate_pct=50, base_borrow_amount_wei=1000, max_borrow_amount_wei=1200))
    m.record_trade(success=True, realized_profit_after_gas_wei=1000)
    assert m.next_amount_in() == 1200

def test_bankroll_derisk_on_fail_streak():
    m = BankrollManager(BankrollConfig(auto_reinvest_enabled=True, reinvest_rate_pct=100, base_borrow_amount_wei=1000, max_borrow_amount_wei=0))
    m.record_trade(success=True, realized_profit_after_gas_wei=1000)
    assert m.next_amount_in() == 2000
    m.record_trade(success=False, realized_profit_after_gas_wei=0)
    m.record_trade(success=False, realized_profit_after_gas_wei=0)
    assert m.next_amount_in() >= 1000
