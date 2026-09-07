from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PerformancePromotionThresholds:
    min_evaluation_observations: int = 50
    min_unique_states: int = 10
    min_mean_advantage_usd: float = 0.0
    min_mean_advantage_bps: float = 5.0
    min_win_rate: float = 0.55
    min_lower_confidence_advantage_usd: float = 0.0


@dataclass(frozen=True)
class PerformancePromotionResult:
    ready: bool
    reason: str
    observations: int
    unique_states: int
    mean_advantage_usd: float
    mean_advantage_bps: float
    win_rate: float
    lower_confidence_advantage_usd: float
    candidate_reward_usd: float
    baseline_reward_usd: float
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def evaluate_performance_promotion(
    events: Iterable[Mapping[str, Any]],
    thresholds: PerformancePromotionThresholds | None = None,
) -> PerformancePromotionResult:
    """Evaluate whether a learned policy has demonstrated OOS advantage.

    This gate is intentionally independent from learning-data quality. Records
    must contain an explicit out-of-sample split and both candidate and baseline
    realized rewards. No promotion is inferred from training reward alone.
    """
    cfg = thresholds or PerformancePromotionThresholds()
    rows: list[Mapping[str, Any]] = []
    for row in events:
        if not isinstance(row, Mapping):
            continue
        split = _text(row.get("evaluation_split") or row.get("split"))
        candidate = _number(row.get("candidate_reward_usd"))
        baseline = _number(row.get("baseline_reward_usd"))
        if split not in {"out_of_sample", "oos"} or candidate is None or baseline is None:
            continue
        rows.append(row)

    observations = len(rows)
    states = {_text(row.get("state_key")) for row in rows if _text(row.get("state_key"))}
    advantages = []
    advantage_bps = []
    wins = 0
    for row in rows:
        candidate = float(row["candidate_reward_usd"])
        baseline = float(row["baseline_reward_usd"])
        advantage = candidate - baseline
        advantages.append(advantage)
        denom = max(abs(baseline), 1e-9)
        advantage_bps.append(advantage / denom * 10_000.0)
        if advantage > 0:
            wins += 1

    mean_advantage = sum(advantages) / observations if observations else 0.0
    mean_bps = sum(advantage_bps) / observations if observations else 0.0
    win_rate = wins / observations if observations else 0.0

    if observations > 1:
        variance = sum((x - mean_advantage) ** 2 for x in advantages) / (observations - 1)
        standard_error = sqrt(max(0.0, variance) / observations)
        lower_bound = mean_advantage - 1.96 * standard_error
    else:
        lower_bound = float("-inf")

    candidate_total = sum(float(row["candidate_reward_usd"]) for row in rows)
    baseline_total = sum(float(row["baseline_reward_usd"]) for row in rows)

    failures: list[str] = []
    if observations < max(1, int(cfg.min_evaluation_observations)):
        failures.append("insufficient_oos_observations")
    if len(states) < max(1, int(cfg.min_unique_states)):
        failures.append("insufficient_oos_state_coverage")
    if mean_advantage < float(cfg.min_mean_advantage_usd):
        failures.append("insufficient_mean_advantage")
    if mean_bps < float(cfg.min_mean_advantage_bps):
        failures.append("insufficient_mean_advantage_bps")
    if win_rate < max(0.0, min(1.0, float(cfg.min_win_rate))):
        failures.append("insufficient_win_rate")
    if lower_bound < float(cfg.min_lower_confidence_advantage_usd):
        failures.append("insufficient_confidence_bound")

    ready = not failures
    return PerformancePromotionResult(
        ready=ready,
        reason="performance_verified" if ready else failures[0],
        observations=observations,
        unique_states=len(states),
        mean_advantage_usd=float(mean_advantage),
        mean_advantage_bps=float(mean_bps),
        win_rate=float(win_rate),
        lower_confidence_advantage_usd=float(lower_bound),
        candidate_reward_usd=float(candidate_total),
        baseline_reward_usd=float(baseline_total),
        failures=tuple(failures),
    )
