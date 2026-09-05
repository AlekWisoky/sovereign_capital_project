from __future__ import annotations

from typing import Any, Mapping


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _bucket(value: float, edges: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def build_goal_objective_context(goal: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize the existing wealth-goal state for OMAR learning."""
    goal = dict(goal or {})
    state = goal.get("state") if isinstance(goal.get("state"), Mapping) else goal
    recommendation = goal.get("recommendation") if isinstance(goal.get("recommendation"), Mapping) else {}
    target = float(state.get("targetReturnPct") or state.get("target_return_pct") or 0.0)
    current = float(state.get("currentReturnPct") or state.get("current_return_pct") or 0.0)
    progress = float(state.get("progressPct") or 0.0)
    horizon = float(state.get("goalHorizonDays") or state.get("timeframeDays") or state.get("timeframe_days") or 30.0)
    compatibility = float(state.get("goalHorizonCompatibility") or state.get("goal_horizon_compatibility") or 1.0)
    urgency = str(state.get("goalUrgency") or recommendation.get("urgency") or "steady")
    pacing = str(state.get("pacing") or "steady")
    aggressiveness_cap = float(state.get("aggressivenessCap") or recommendation.get("aggressiveness_hint") or 1.0)
    achieved = bool(state.get("goalAchieved", False))
    blocked = str(state.get("goalStatus") or "active") == "blocked"
    gap = max(0.0, target - current)
    gap_ratio = gap / max(abs(target), 1.0) if target > 0.0 else 0.0
    return {
        "goal_target_return_pct": target,
        "goal_current_return_pct": current,
        "goal_progress_pct": _clip(progress, 0.0, 200.0),
        "goal_gap_pct": gap,
        "goal_gap_ratio": _clip(gap_ratio, 0.0, 2.0),
        "goal_horizon_days": max(1.0, horizon),
        "goal_horizon_compatibility": _clip(compatibility, 0.0, 2.0),
        "goal_urgency": urgency,
        "goal_pacing": pacing,
        "goal_aggressiveness_cap": _clip(aggressiveness_cap, 0.25, 1.25),
        "goal_achieved": achieved,
        "goal_blocked": blocked,
    }


def goal_state_bucket(context: Mapping[str, Any]) -> str:
    """Stable categorical representation for the contextual learner."""
    gap = float(context.get("goal_gap_pct") or 0.0)
    progress = float(context.get("goal_progress_pct") or 0.0)
    compatibility = float(context.get("goal_horizon_compatibility") or 1.0)
    cap = float(context.get("goal_aggressiveness_cap") or 1.0)
    urgency = str(context.get("goal_urgency") or "steady").lower()
    pacing = str(context.get("goal_pacing") or "steady").lower()
    return ":".join(
        (
            _bucket(progress, (25.0, 50.0, 75.0, 100.0), ("p0", "p25", "p50", "p75", "p100")),
            _bucket(gap, (0.0, 2.0, 5.0, 10.0), ("gap0", "gap2", "gap5", "gap10", "gap_hi")),
            _bucket(compatibility, (0.50, 0.75, 1.00), ("vel_low", "vel_watch", "vel_ok", "vel_ahead")),
            _bucket(cap, (0.60, 0.80, 1.00), ("cap_def", "cap_measured", "cap_normal", "cap_expand")),
            urgency,
            pacing,
        )
    )


def goal_advancement_reward(
    *,
    context: Mapping[str, Any],
    realized_net_usd: float,
    expected_net_usd: float,
    amount_in_wei: int,
    drawdown_pct: float = 0.0,
    truth_verified: bool = True,
) -> float:
    """Add bounded goal advancement shaping to the canonical settled reward."""
    del amount_in_wei  # canonical reward is already expressed in settled USD economics
    realized = float(realized_net_usd)
    expected = float(expected_net_usd)
    gap_ratio = _clip(float(context.get("goal_gap_ratio") or 0.0), 0.0, 2.0)
    velocity = _clip(float(context.get("goal_horizon_compatibility") or 1.0), 0.0, 2.0)
    urgency = str(context.get("goal_urgency") or "steady").lower()
    cap = _clip(float(context.get("goal_aggressiveness_cap") or 1.0), 0.25, 1.25)
    economics = _clip(realized - expected, -5.0, 5.0)
    realized_direction = 1.0 if realized > 0.0 else (-1.0 if realized < 0.0 else 0.0)
    advancement = realized_direction * (0.20 + 0.35 * gap_ratio)
    velocity_adjustment = _clip(velocity - 1.0, -1.0, 1.0) * 0.15
    urgency_adjustment = 0.08 if urgency == "catch_up" and realized > 0.0 else 0.0
    risk_penalty = max(0.0, float(drawdown_pct)) * 0.03
    cap_penalty = max(0.0, cap - 1.0) * 0.10 if realized <= 0.0 else 0.0
    reward = economics + advancement + velocity_adjustment + urgency_adjustment
    reward -= risk_penalty + cap_penalty
    if not truth_verified:
        reward -= 1.0
    return float(_clip(reward, -7.5, 7.5))
