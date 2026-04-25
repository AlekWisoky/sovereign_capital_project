from __future__ import annotations

from typing import Any, Dict, Iterable

from ..schema import EpisodeContext, ProposalOutput, ScoreResult
from .capital_grader import grade_capital
from .latency_grader import grade_latency
from .policy_grader import grade_policy
from .profit_grader import grade_profit
from .risk_grader import grade_risk
from .schema_grader import grade_schema


_SAFE_WEIGHT_EXCEPTIONS = (TypeError, ValueError, OverflowError)


def _coerce_weights(weights: Dict[str, Any] | None) -> Dict[str, int]:
    defaults = {
        "schema": 100,
        "policy": 100,
        "capital": 250,
        "profit": 100,
        "risk": 100,
        "latency": 100,
    }
    out = dict(defaults)
    for k, v in dict(weights or {}).items():
        try:
            out[str(k)] = int(v)
        except _SAFE_WEIGHT_EXCEPTIONS:
            continue
    return out


def score_proposal(
    ctx: EpisodeContext,
    proposal: Dict[str, Any] | ProposalOutput,
    *,
    weights: Dict[str, Any] | None = None,
) -> ScoreResult:
    parsed, schema_component = grade_schema(ctx, proposal)
    if parsed is None:
        return ScoreResult(
            episode_id=ctx.episode_id,
            proposal_valid=False,
            total_reward_ppm=schema_component.reward_ppm,
            components=[schema_component],
            proposal=None,
        )

    comps = [
        schema_component,
        grade_policy(ctx, parsed),
        grade_capital(ctx, parsed),
        grade_profit(ctx, parsed),
        grade_risk(ctx, parsed),
        grade_latency(ctx, parsed),
    ]
    total = 0
    applied = _coerce_weights(weights)
    for c in comps:
        weight = int(applied.get(c.name, 100))
        total += int(c.reward_ppm * weight // 100)
    total = max(-1_000_000, min(1_000_000, int(total)))
    return ScoreResult(
        episode_id=ctx.episode_id,
        proposal_valid=True,
        total_reward_ppm=int(total),
        components=comps,
        proposal=parsed,
    )
