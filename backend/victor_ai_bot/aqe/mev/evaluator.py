from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class MEVEvaluation:
    ok: bool
    expected_value_wei: int
    gas_cost_wei: int
    slippage_cost_wei: int
    risk_penalty_wei: int
    score: float
    meta: Dict[str, Any]


def evaluate_bundle(*, ev_wei: int, gas_cost_wei: int, slippage_cost_wei: int, mev_risk: float) -> MEVEvaluation:
    """Risk-adjusted EV evaluator.

    `score` is a monotonic ranking scalar; higher is better.
    """

    ev = int(ev_wei)
    gas = int(gas_cost_wei)
    slip = int(slippage_cost_wei)
    risk = max(0.0, min(1.0, float(mev_risk)))

    # Penalize EV proportional to risk and total costs.
    base = max(0, ev - gas - slip)
    penalty = int(base * (0.10 + 0.80 * risk))
    net = base - penalty

    # Score: log-ish scaling without math deps.
    score = float(net) / float(max(1, gas + slip + 1))

    return MEVEvaluation(
        ok=net > 0,
        expected_value_wei=ev,
        gas_cost_wei=gas,
        slippage_cost_wei=slip,
        risk_penalty_wei=penalty,
        score=score,
        meta={"net_after_penalty": net, "risk": risk},
    )


def evaluate_adversarial_execution(
    *,
    amount_in_wei: int,
    min_amount_out_wei: int,
    expected_amount_out_wei: int,
    flashloan_fee_wei: int,
    gas_cost_wei: int,
    p_success_base: float,
    mev_risk: float,
    mev_fail_prob_scale: float = 0.55,
    gas_premium_mult: float = 0.35,
) -> MEVEvaluation:
    """Adversarial MEV-aware execution EV.

    This is a deterministic, conservative evaluator intended for preflight
    gating. It estimates a risk-adjusted EV under:

    - reduced success probability as MEV risk rises
    - a gas premium under contention

    NOTE: This does *not* replace on-chain profit assertion. It is a planning
    guardrail to reduce unprofitable / low-quality attempts.
    """

    ain = int(amount_in_wei)
    out_min = int(min_amount_out_wei)
    out_exp = int(expected_amount_out_wei)
    flash_fee = int(flashloan_fee_wei)
    gas = int(gas_cost_wei)

    p0 = max(0.0, min(1.0, float(p_success_base)))
    risk = max(0.0, min(1.0, float(mev_risk)))
    scale = max(0.0, min(1.0, float(mev_fail_prob_scale)))
    gas_mult = max(0.0, float(gas_premium_mult))

    # Conservative profit (before gas) uses min out (enforced by calldata).
    profit_success = (out_min - ain) - flash_fee

    # Adversarial success probability decays with MEV risk.
    p_success_adj = max(0.0, min(1.0, p0 * (1.0 - risk * scale)))

    # Gas premium under contention.
    gas_eff = int(round(float(gas) * (1.0 + gas_mult * risk)))

    # Slippage "cost" is just diagnostic here (buffer between expected and min).
    slip_cost = max(0, out_exp - out_min) if out_exp > 0 else 0

    # Expected value under adversarial conditions.
    ev_after = int(round(float(profit_success) * float(p_success_adj))) - int(gas_eff)

    score = float(ev_after) / float(max(1, gas_eff + 1))

    return MEVEvaluation(
        ok=ev_after > 0,
        expected_value_wei=int(ev_after),
        gas_cost_wei=int(gas_eff),
        slippage_cost_wei=int(slip_cost),
        risk_penalty_wei=0,
        score=score,
        meta={
            "p_success_base": float(p0),
            "p_success_adj": float(p_success_adj),
            "mev_risk": float(risk),
            "mev_fail_prob_scale": float(scale),
            "gas_premium_mult": float(gas_mult),
            "profit_success_wei": int(profit_success),
            "gas_cost_eff_wei": int(gas_eff),
            "slippage_buffer_wei": int(slip_cost),
        },
    )
