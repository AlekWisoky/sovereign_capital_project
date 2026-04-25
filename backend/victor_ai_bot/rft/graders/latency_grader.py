from __future__ import annotations

from ._common import ensure_proposal, get_primary_opportunity, make_component


def grade_latency(ctx, proposal):
    p = ensure_proposal(proposal)
    opp = get_primary_opportunity(ctx, p.opportunity_id)
    p90 = int(ctx.latency.exec_ms_p90 or ctx.latency.loop_ms_p90 or 0)
    p99 = int(ctx.latency.exec_ms_p99 or ctx.latency.loop_ms_p99 or 0)
    competition = str(opp.get("competition") or "medium")
    if competition == "high" and p.send_mode == "public":
        return make_component("latency", -120, False, "high_competition_public_send")
    if p99 > 1200 and p.constraints.deadline_seconds <= 15:
        return make_component(
            "latency", -80, False, "deadline_too_tight_for_observed_p99", exec_ms_p99=p99
        )
    if p90 > 800 and p.send_mode == "protected_rpc":
        return make_component("latency", +80, True, "protected_send_matches_high_latency")
    return make_component("latency", +60, True, "latency_pass", exec_ms_p90=p90, exec_ms_p99=p99)
