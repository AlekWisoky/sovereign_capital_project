from __future__ import annotations

from typing import Any, Dict


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def reward_function(
    *,
    realized_net_pnl: float | None = None,
    deployed_notional: float = 1.0,
    gas_cost: float = 0.0,
    slippage_bias: float = 0.0,
    interference_penalty: float = 0.0,
    drawdown_contribution: float = 0.0,
    concentration_penalty: float = 0.0,
    capital_lock_penalty: float = 0.0,
    stability_bonus: float = 0.0,
    calibration_bonus: float = 0.0,
    **legacy_kwargs: Any,
) -> Dict[str, Any]:
    if realized_net_pnl is None:
        realized_net_pnl = _safe_float(legacy_kwargs.get("realized_pnl"), 0.0)
    if "capital_efficiency" in legacy_kwargs and float(deployed_notional or 1.0) == 1.0:
        deployed_notional = max(1.0, 100.0 * float(legacy_kwargs.get("capital_efficiency") or 0.0))
    if "gas_efficiency" in legacy_kwargs and not gas_cost:
        gas_cost = max(0.0, 1.0 - float(legacy_kwargs.get("gas_efficiency") or 0.0))
    if "failure_rate" in legacy_kwargs and not interference_penalty:
        interference_penalty = max(0.0, float(legacy_kwargs.get("failure_rate") or 0.0))
    if "stability" in legacy_kwargs and not stability_bonus:
        stability_bonus = max(0.0, float(legacy_kwargs.get("stability") or 0.0))
    denom = max(1.0, abs(_safe_float(deployed_notional, 1.0)))
    normalized_realized = _safe_float(realized_net_pnl) / denom
    components = {
        "realizedNetPnl": round(normalized_realized, 6),
        "gasCost": round(_safe_float(gas_cost) / denom, 6),
        "slippageBias": round(_safe_float(slippage_bias) / denom, 6),
        "interferencePenalty": round(_safe_float(interference_penalty) / denom, 6),
        "drawdownContribution": round(_safe_float(drawdown_contribution) / denom, 6),
        "concentrationPenalty": round(_safe_float(concentration_penalty) / denom, 6),
        "capitalLockPenalty": round(_safe_float(capital_lock_penalty) / denom, 6),
        "stabilityBonus": round(_safe_float(stability_bonus), 6),
        "calibrationBonus": round(_safe_float(calibration_bonus), 6),
    }
    reward = (
        normalized_realized
        - components["gasCost"]
        - components["slippageBias"]
        - components["interferencePenalty"]
        - components["drawdownContribution"]
        - components["concentrationPenalty"]
        - components["capitalLockPenalty"]
        + components["stabilityBonus"]
        + components["calibrationBonus"]
    )
    return {
        "reward": round(float(reward), 6),
        "components": components,
        "normalizationDenom": round(denom, 6),
    }
