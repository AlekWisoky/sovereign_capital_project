from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SafetyResult:
    ok: bool
    reason: str
    profit_after_costs_wei: int
    flashloan_fee_wei: int
    gas_cost_wei: int


def compute_flashloan_fee(amount_in_wei: int, fee_bps: int) -> int:
    return (amount_in_wei * fee_bps) // 10_000


def check_profit_and_repay(
    *,
    amount_in_wei: int,
    amount_out_wei: int,
    min_profit_abs_wei: int,
    min_profit_bps: int,
    flashloan_fee_bps: int,
    gas_cost_wei: int,
) -> SafetyResult:
    flash_fee = compute_flashloan_fee(amount_in_wei, flashloan_fee_bps)
    repay = amount_in_wei + flash_fee
    if amount_out_wei < repay:
        return SafetyResult(False, "does_not_repay_flashloan", -1, flash_fee, gas_cost_wei)

    gross_profit = amount_out_wei - amount_in_wei
    profit_after = gross_profit - flash_fee - gas_cost_wei
    if profit_after <= 0:
        return SafetyResult(
            False, "profit_after_costs_not_positive", profit_after, flash_fee, gas_cost_wei
        )
    if profit_after < min_profit_abs_wei:
        return SafetyResult(False, "minProfitAbs_not_met", profit_after, flash_fee, gas_cost_wei)
    # bps threshold based on amount_in
    if min_profit_bps > 0:
        if profit_after * 10_000 < amount_in_wei * min_profit_bps:
            return SafetyResult(
                False, "minProfitBps_not_met", profit_after, flash_fee, gas_cost_wei
            )
    return SafetyResult(True, "ok", profit_after, flash_fee, gas_cost_wei)
