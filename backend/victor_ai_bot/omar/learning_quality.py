from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

from .real_learning import ACTIONS


@dataclass(frozen=True)
class LearningQualityThresholds:
    min_observations: int = 50
    min_action_coverage: float = 0.50
    min_state_count: int = 10
    min_truth_rate: float = 0.995
    max_missing_lineage_rate: float = 0.0
    max_duplicate_rate: float = 0.0


@dataclass(frozen=True)
class LearningQualityResult:
    ready: bool
    reason: str
    observations: int
    unique_states: int
    action_coverage: float
    truth_rate: float
    missing_lineage_rate: float
    duplicate_rate: float
    invalid_reward_count: int
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _valid_event(row: Mapping[str, Any]) -> bool:
    return _text(row.get("state_key")) != "" and _text(row.get("action")) in ACTIONS


def evaluate_learning_quality(
    events: Iterable[Mapping[str, Any]],
    thresholds: LearningQualityThresholds | None = None,
) -> LearningQualityResult:
    """Evaluate whether settled learning data is sufficiently trustworthy for live influence.

    This gate measures data quality, not profitability. It deliberately does not
    promote a policy because its rewards are positive; performance promotion
    requires a separate out-of-sample/baseline evaluation.
    """
    cfg = thresholds or LearningQualityThresholds()
    rows = [dict(row) for row in events if isinstance(row, Mapping)]
    observations = len(rows)
    states = {_text(row.get("state_key")) for row in rows if _text(row.get("state_key"))}
    actions = {_text(row.get("action")) for row in rows if _text(row.get("action")) in ACTIONS}
    action_coverage = len(actions) / len(ACTIONS)

    truth_count = sum(
        bool(row.get("outcome_truth_verified", row.get("truth_verified", False))) for row in rows
    )
    truth_rate = truth_count / observations if observations else 0.0

    missing_lineage = 0
    invalid_rewards = 0
    identities: list[str] = []
    for row in rows:
        decision_id = _text(row.get("decision_id"))
        correlation_id = _text(row.get("correlation_id"))
        if not decision_id or not correlation_id:
            missing_lineage += 1
        identity = decision_id or _text(row.get("tx_hash"))
        if identity:
            identities.append(identity)
        reward = row.get("reward")
        try:
            if reward is None or not isfinite(float(reward)):
                invalid_rewards += 1
        except (TypeError, ValueError):
            invalid_rewards += 1

    duplicate_count = len(identities) - len(set(identities))
    duplicate_rate = duplicate_count / len(identities) if identities else 0.0
    missing_lineage_rate = missing_lineage / observations if observations else 0.0

    failures: list[str] = []
    if observations < max(1, int(cfg.min_observations)):
        failures.append("insufficient_observations")
    if action_coverage < max(0.0, min(1.0, float(cfg.min_action_coverage))):
        failures.append("insufficient_action_coverage")
    if len(states) < max(1, int(cfg.min_state_count)):
        failures.append("insufficient_state_coverage")
    if truth_rate < max(0.0, min(1.0, float(cfg.min_truth_rate))):
        failures.append("insufficient_truth_verification")
    if missing_lineage_rate > max(0.0, float(cfg.max_missing_lineage_rate)):
        failures.append("missing_lineage")
    if duplicate_rate > max(0.0, float(cfg.max_duplicate_rate)):
        failures.append("duplicate_learning_identity")
    if invalid_rewards:
        failures.append("invalid_reward")

    ready = not failures
    return LearningQualityResult(
        ready=ready,
        reason="quality_verified" if ready else failures[0],
        observations=observations,
        unique_states=len(states),
        action_coverage=float(action_coverage),
        truth_rate=float(truth_rate),
        missing_lineage_rate=float(missing_lineage_rate),
        duplicate_rate=float(duplicate_rate),
        invalid_reward_count=invalid_rewards,
        failures=tuple(failures),
    )
