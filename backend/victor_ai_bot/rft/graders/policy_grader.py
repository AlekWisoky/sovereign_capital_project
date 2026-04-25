from __future__ import annotations

from ._common import ensure_proposal, make_component


def grade_policy(ctx, proposal):
    p = ensure_proposal(proposal)
    if str(ctx.v1_focus or "flashloan_atomic") != "flashloan_atomic":
        return make_component("policy", -400, False, "v1_scope_mismatch", v1_focus=ctx.v1_focus)
    controls = dict(ctx.controls or {})
    sandbox_active = bool(controls.get("sandbox_only") or p.mode.sandbox_only)
    if sandbox_active and p.send_mode not in {"txdata", "protected_rpc"}:
        return make_component(
            "policy", -400, False, "sandbox_requires_non_public_send", send_mode=p.send_mode
        )
    if bool(controls.get("paused", False)) and not bool(
        controls.get("allow_proposal_scoring_when_paused", True)
    ):
        return make_component("policy", -400, False, "paused_policy")
    return make_component("policy", +100, True, "policy_pass")
