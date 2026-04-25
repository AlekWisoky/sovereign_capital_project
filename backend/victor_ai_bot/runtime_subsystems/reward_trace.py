from __future__ import annotations

from typing import Any, Dict

from ..rl_training.reward import reward_function


def build_reward_trace(
    *,
    amount_in_wei: int,
    expected_after_costs_wei: int,
    realized_after_gas_wei: int,
    ok: bool,
    submit_to_receipt_ms: int = 0,
    gas_cost_wei: int = 0,
    slippage_bias_wei: int = 0,
    interference_penalty_wei: int = 0,
    drawdown_contribution_wei: int = 0,
    concentration_penalty_wei: int = 0,
    capital_lock_penalty_wei: int = 0,
    stability_bonus: float = 0.0,
    calibration_bonus: float = 0.0,
) -> Dict[str, Any]:
    denom_i = int(max(1, int(amount_in_wei or 0)))
    realized_i = (
        int(realized_after_gas_wei or 0)
        if bool(ok)
        else int(min(0, int(realized_after_gas_wei or 0)))
    )
    expected_i = int(expected_after_costs_wei or 0)
    penalty_i = int(abs(expected_i)) if not bool(ok) else 0
    reward = reward_function(
        realized_net_pnl=float(realized_i - penalty_i),
        deployed_notional=float(denom_i),
        gas_cost=float(gas_cost_wei or 0),
        slippage_bias=float(slippage_bias_wei or 0),
        interference_penalty=float(interference_penalty_wei or 0),
        drawdown_contribution=float(drawdown_contribution_wei or 0),
        concentration_penalty=float(concentration_penalty_wei or 0),
        capital_lock_penalty=float(capital_lock_penalty_wei or 0),
        stability_bonus=float(stability_bonus or 0.0),
        calibration_bonus=float(calibration_bonus or 0.0),
    )
    reward_scaled_ppm = int(float(reward["reward"]) * 1_000_000)
    return {
        "ok": bool(ok),
        "amount_in_wei": str(int(amount_in_wei or 0)),
        "expected_after_costs_wei": str(int(expected_i)),
        "realized_after_gas_wei": str(int(realized_i)),
        "reward_scaled_ppm": int(reward_scaled_ppm),
        "submit_to_receipt_ms": int(submit_to_receipt_ms or 0),
        "reward": float(reward["reward"]),
        "components": dict(reward["components"]),
        "normalizationDenom": reward["normalizationDenom"],
    }
