from victor_ai_bot.money_loop_accounting import (
    classify_settlement,
    signed_net_pnl_from_metadata,
)


def test_loss_is_signed_and_counted_as_bankroll_loss():
    result = classify_settlement(
        signed_net_pnl_wei=-125,
        flashloan_principal_wei=10_000,
        flashloan_fee_wei=5,
    )

    assert result.signed_net_pnl_wei == -125
    assert result.bankroll_loss_wei == 125
    assert result.positive_profit_wei == 0
    assert result.owned_capital_delta_wei == -125
    assert result.reinvestable_profit_wei == 0
    assert result.flashloan_principal_wei == 10_000
    assert result.flashloan_fee_wei == 5
    assert result.loss is True


def test_profit_never_includes_flashloan_principal():
    result = classify_settlement(
        signed_net_pnl_wei=300,
        flashloan_principal_wei=100_000,
        flashloan_fee_wei=25,
    )

    assert result.signed_net_pnl_wei == 300
    assert result.positive_profit_wei == 300
    assert result.reinvestable_profit_wei == 300
    assert result.owned_capital_delta_wei == 300
    assert result.flashloan_principal_wei == 100_000
    assert result.loss is False


def test_signed_pnl_resolution_is_explicit_and_fail_closed():
    assert signed_net_pnl_from_metadata({"signed_net_pnl_wei": "-7"}) == -7
    assert signed_net_pnl_from_metadata({"signedNetPnlWei": "19"}) == 19
    assert signed_net_pnl_from_metadata({"success": False, "realized_profit_after_gas_wei": 0}) is None
