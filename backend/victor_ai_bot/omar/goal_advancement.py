from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Mapping


@dataclass(frozen=True)
class GoalAdvancementResult:
    allowed: bool
    reason: str
    current_target_pct: float
    next_target_pct: float
    goal_achieved: bool
    performance_verified: bool
    oos_observations: int
    unique_states: int
    mean_advantage_usd: float
    lower_confidence_advantage_usd: float
    stability_score: float
    execution_realism_score: float
    risk_score: float
    horizon_compatibility: float
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if isfinite(result) else default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def evaluate_goal_advancement(
    goal_state: Mapping[str, Any] | None,
    performance: Mapping[str, Any] | None,
    *,
    min_stability_score: float = 0.60,
    min_execution_realism_score: float = 0.60,
    max_risk_score: float = 0.75,
    min_horizon_compatibility: float = 0.90,
) -> GoalAdvancementResult:
    """Fail-closed gate for moving from one wealth goal to the next.

    Goal completion alone is not sufficient. Advancement requires the same
    evidence discipline used for live OMAR promotion: canonical OOS evidence,
    verified performance, and healthy execution/risk economics.
    """
    goal = dict(goal_state or {})
    perf = dict(performance or {})

    current = _number(goal.get("targetReturnPct") or goal.get("target_return_pct"))
    next_target = _number(
        goal.get("suggestedNextTargetPct") or goal.get("suggested_next_target_pct"),
        current,
    )
    achieved = bool(goal.get("goalAchieved", goal.get("goal_achieved", False)))
    requested = bool(goal.get("nextGoalAllowed", goal.get("next_goal_allowed", True)))
    stability = _number(goal.get("stabilityScore") or goal.get("stability_score"))
    realism = _number(goal.get("executionRealismScore") or goal.get("execution_realism_score"))
    risk = _number(goal.get("riskScore") or goal.get("risk_score"))
    horizon = _number(
        goal.get("goalHorizonCompatibility")
        or goal.get("goal_horizon_compatibility"),
        1.0,
    )

    promotion_allowed = bool(perf.get("promotion_allowed", perf.get("ready", False)))
    observations = _integer(perf.get("observations") or perf.get("oos_evidence_rows"))
    unique_states = _integer(perf.get("unique_states"))
    mean_advantage = _number(perf.get("mean_advantage_usd"))
    lower_bound = _number(perf.get("lower_confidence_advantage_usd"), float("-inf"))

    failures: list[str] = []
    if not achieved:
        failures.append("active_goal_not_achieved")
    if not requested:
        failures.append("goal_progression_blocked")
    if not promotion_allowed:
        failures.append("performance_promotion_not_verified")
    if next_target <= current:
        failures.append("next_goal_does_not_advance")
    if stability < min_stability_score:
        failures.append("stability_below_advancement_threshold")
    if realism < min_execution_realism_score:
        failures.append("execution_realism_below_advancement_threshold")
    if risk > max_risk_score:
        failures.append("risk_above_advancement_threshold")
    if horizon < min_horizon_compatibility:
        failures.append("goal_horizon_incompatible")
    if observations <= 0:
        failures.append("missing_oos_observations")
    if not isfinite(lower_bound) or lower_bound < 0.0:
        failures.append("oos_confidence_bound_not_positive")

    return GoalAdvancementResult(
        allowed=not failures,
        reason="goal_advancement_verified" if not failures else failures[0],
        current_target_pct=current,
        next_target_pct=next_target,
        goal_achieved=achieved,
        performance_verified=promotion_allowed,
        oos_observations=observations,
        unique_states=unique_states,
        mean_advantage_usd=mean_advantage,
        lower_confidence_advantage_usd=lower_bound,
        stability_score=stability,
        execution_realism_score=realism,
        risk_score=risk,
        horizon_compatibility=horizon,
        failures=tuple(failures),
    )
