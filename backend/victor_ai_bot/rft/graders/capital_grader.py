from __future__ import annotations

from ._common import ensure_proposal, get_primary_opportunity, make_component, opportunity_after_costs_wei, opportunity_after_gas_usd_micro


def _estimated_cap_usd_micro(opp: dict) -> int:
    exp_profit = opportunity_after_gas_usd_micro(opp)
    # Conservative heuristic until a direct NAV/notional feed is available.
    return max(50_000_000, min(5_000_000_000, int(exp_profit) * 250))


def grade_capital(ctx, proposal):
    p = ensure_proposal(proposal)
    if ctx.breakers.drawdown_breaker or ctx.breakers.gas_anomaly_breaker:
        if not p.mode.defensive:
            return make_component("capital", -250, False, "breakers_require_defensive_mode")
    opp = get_primary_opportunity(ctx, p.opportunity_id)
    net_after_costs_wei = opportunity_after_costs_wei(opp)
    if net_after_costs_wei <= 0:
        return make_component(
            "capital",
            -250,
            False,
            "capital_deny_non_positive_after_costs",
            net_after_costs_wei=net_after_costs_wei,
            limit_usd_micro=0,
        )
    cap = _estimated_cap_usd_micro(opp)
    sandbox_cap = int(cap * max(0.05, min(1.0, ctx.risk_caps.sandbox_cap_pct_bps / 10_000.0)))
    probation_cap = int(cap * max(0.02, min(1.0, ctx.risk_caps.probation_cap_pct_bps / 10_000.0)))
    limit = cap
    if p.mode.sandbox_only:
        limit = min(limit, sandbox_cap)
    if p.mode.probation:
        limit = min(limit, probation_cap)
    if int(p.notional_usd_micro) > int(limit):
        return make_component(
            "capital", -250, False, "capital_deny_notional_above_cap", limit_usd_micro=int(limit), net_after_costs_wei=net_after_costs_wei
        )
    return make_component(
        "capital", +250, True, "capital_would_approve", limit_usd_micro=int(limit), net_after_costs_wei=net_after_costs_wei
    )
