from __future__ import annotations

from typing import Any, Dict

from .degraded_state_contract import decision_contract
from .profitability_state import profitability_state_view, post_mutation_revalidation_view


def profitability_summary_projection(opp: Any) -> Dict[str, Any]:
    state = profitability_state_view(opp)
    stale = bool(state["stale"])
    post_mutation = post_mutation_revalidation_view(opp)
    reason_code = str(
        post_mutation.get("reason_code") or post_mutation.get("reason") or state["reason"] or "ok"
    )
    valid = bool(post_mutation.get("valid", state["valid"]))
    authoritative = bool(post_mutation.get("authoritative", state["authoritative"]))
    degraded = bool(post_mutation.get("degraded", False) or stale or not valid)
    blocked = bool(authoritative and not valid)
    state_contract = decision_contract(
        phase="candidate_trade_reporting",
        reason_code=reason_code,
        degraded=degraded,
        blocked=blocked,
        sticky_cycle=True,
        details={
            "stage": str(post_mutation.get("stage") or state["stage"]),
            "authoritative": authoritative,
            "valid": valid,
        },
    )
    return {
        "continuity": dict(state["continuity"]),
        "continuityPresent": bool(state["continuityPresent"]),
        "continuityValid": bool(state["continuityValid"]),
        "revalidated": bool(state["revalidated"]),
        "stale": stale,
        "displayExpectedProfitRaw": str(state["grossProfitWeiInt"] if not stale else 0),
        "displayExpectedProfitRawInt": int(state["grossProfitWeiInt"] if not stale else 0),
        "displayProfitAfterCostsWei": str(state["profitAfterCostsWeiInt"] if not stale else 0),
        "displayProfitAfterCostsWeiInt": int(state["profitAfterCostsWeiInt"] if not stale else 0),
        "displayExpectedProfitUsd": float(state["expectedProfitUsd"] if not stale else 0.0),
        "displayExpectedProfitUsdMicro": (
            int(round(float(state["expectedProfitUsd"]) * 1_000_000.0)) if not stale else 0
        ),
        "displayExpectedProfitAfterCostsUsdMicro": int(
            state["profitAfterCostsUsdMicroInt"] if not stale else 0
        ),
        "reason": str(state["reason"]),
        "stage": str(state["stage"]),
        "valid": bool(state["valid"]),
        "authoritative": bool(state["authoritative"]),
        "postMutationRevalidation": dict(post_mutation),
        "stateContract": state_contract,
    }
