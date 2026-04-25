from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from ..schema import EpisodeContext, ProposalOutput, ScoreComponent


def ensure_proposal(proposal: ProposalOutput | Dict[str, Any]) -> ProposalOutput:
    if isinstance(proposal, ProposalOutput):
        return proposal
    return ProposalOutput.model_validate(proposal)


def get_primary_opportunity(ctx: EpisodeContext, opportunity_id: str) -> Dict[str, Any]:
    for item in list(ctx.top_opportunities or []):
        if str(item.opportunity_id) == str(opportunity_id):
            return item.model_dump() if hasattr(item, "model_dump") else dict(item)
    return {}


def make_component(
    name: str, reward_ppm: int, passed: bool, reason: str = "", **details: Any
) -> ScoreComponent:
    return ScoreComponent(
        name=name,
        reward_ppm=int(reward_ppm),
        passed=bool(passed),
        reason=str(reason or ""),
        details=dict(details or {}),
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def opportunity_after_costs_wei(opp: Dict[str, Any]) -> int:
    return _safe_int(opp.get("expected_profit_after_costs_wei"), 0)


def opportunity_after_gas_usd_micro(opp: Dict[str, Any]) -> int:
    return max(0, _safe_int(opp.get("expected_profit_after_gas_usd_micro") or opp.get("expected_profit_usd_micro"), 0))
