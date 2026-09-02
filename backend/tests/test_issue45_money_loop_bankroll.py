from victor_ai_bot.bankroll import BankrollConfig, BankrollManager


def test_signed_loss_reduces_net_pnl_and_never_creates_reinvestable_profit():
    manager = BankrollManager(
        BankrollConfig(
            auto_reinvest_enabled=True,
            reinvest_rate_pct=50,
            base_borrow_amount_wei=1_000,
            max_borrow_amount_wei=10_000,
        )
    )

    manager.record_trade(
        success=True,
        realized_profit_after_gas_wei=500,
        signed_net_pnl_wei=500,
        amount_in_wei=1_000,
        flashloan_principal_wei=50_000,
    )
    assert manager.state.realized_net_pnl_wei == 500
    assert manager.state.reinvestable_profit_wei == 500
    assert manager.state.last_flashloan_principal_wei == 50_000

    manager.record_trade(
        success=False,
        realized_profit_after_gas_wei=0,
        signed_net_pnl_wei=-700,
        amount_in_wei=1_000,
        flashloan_principal_wei=60_000,
    )

    assert manager.state.realized_net_pnl_wei == -200
    assert manager.state.realized_profit_wei == -200
    assert manager.state.bankroll_loss_wei == 700
    assert manager.state.reinvestable_profit_wei == 500
    assert manager.state.last_flashloan_principal_wei == 60_000
    assert manager.state.last_flashloan_principal_wei != manager.state.reinvestable_profit_wei


def test_reinvestment_consumes_profit_pool_not_borrowed_principal():
    manager = BankrollManager(
        BankrollConfig(auto_reinvest_enabled=True, reinvest_rate_pct=100, base_borrow_amount_wei=1_000)
    )
    manager.record_trade(
        success=True,
        realized_profit_after_gas_wei=400,
        signed_net_pnl_wei=400,
        amount_in_wei=1_000,
        flashloan_principal_wei=100_000,
    )

    assert manager.record_reinvestment(250) == 250
    assert manager.state.reinvestable_profit_wei == 150
    assert manager.state.reinvested_profit_wei == 250
    assert manager.next_amount_in() == 1_150


def test_legacy_positive_record_trade_remains_compatible():
    manager = BankrollManager(BankrollConfig(base_borrow_amount_wei=1_000))
    manager.record_trade(success=True, realized_profit_after_gas_wei=250, amount_in_wei=1_000)
    assert manager.state.realized_net_pnl_wei == 250
    assert manager.state.reinvestable_profit_wei == 250
