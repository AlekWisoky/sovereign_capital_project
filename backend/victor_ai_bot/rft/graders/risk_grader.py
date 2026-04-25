from __future__ import annotations

from ._common import ensure_proposal, make_component


def grade_risk(ctx, proposal):
    p = ensure_proposal(proposal)
    penalty = 0
    reasons = []
    if ctx.breakers.drawdown_breaker:
        penalty -= 250
        reasons.append("drawdown_breaker")
    if ctx.breakers.gas_anomaly_breaker and p.constraints.max_slippage_bps > 120:
        penalty -= 120
        reasons.append("gas_anomaly_with_loose_slippage")
    if ctx.breakers.rpc_degraded and p.send_mode == "public":
        penalty -= 90
        reasons.append("rpc_degraded_public_send")
    if (
        str(ctx.risk_state or "normal") in {"volatile", "defensive"}
        and p.constraints.max_slippage_bps > 80
    ):
        penalty -= 120
        reasons.append("volatile_regime_high_slippage")
    if p.mode.probation and int(p.notional_usd_micro) > 250_000_000:
        penalty -= 80
        reasons.append("probation_notional_too_large")
    if penalty < 0:
        return make_component("risk", penalty, False, ",".join(reasons), reasons=reasons)
    return make_component("risk", +120, True, "risk_pass")
