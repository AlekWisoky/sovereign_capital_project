from __future__ import annotations

from ._common import (
    ensure_proposal,
    get_primary_opportunity,
    make_component,
    opportunity_after_costs_wei,
    opportunity_after_gas_usd_micro,
)


def grade_profit(ctx, proposal):
    p = ensure_proposal(proposal)
    opp = get_primary_opportunity(ctx, p.opportunity_id)
    net_after_costs_wei = opportunity_after_costs_wei(opp)
    net_usd_micro = opportunity_after_gas_usd_micro(opp)
    if net_after_costs_wei <= 0:
        return make_component(
            "profit",
            -300,
            False,
            "negative_or_missing_net_after_costs",
            net_after_costs_wei=net_after_costs_wei,
            net_after_gas_usd_micro=net_usd_micro,
        )
    # Scale conservatively with the best available USD proxy while gating on positive after-costs truth.
    reward = 25 if net_usd_micro <= 0 else max(25, min(400, int(net_usd_micro // 1_000_000)))
    return make_component(
        "profit",
        int(reward),
        True,
        "positive_expected_net_after_costs",
        net_after_costs_wei=net_after_costs_wei,
        net_after_gas_usd_micro=net_usd_micro,
    )
