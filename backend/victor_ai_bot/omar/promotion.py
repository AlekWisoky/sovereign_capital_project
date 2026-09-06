from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class PromotionThresholds:
    min_oos_observations: int = 50
    min_unique_states: int = 10
    min_mean_advantage_usd: float = 0.0
    min_mean_advantage_bps: float = 5.0
    min_win_rate: float = 0.55
    min_lower_confidence_advantage_usd: float = 0.0


@dataclass(frozen=True)
class PromotionDecision:
    ready: bool
    reason: str
    candidate_version: str
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


@dataclass(frozen=True)
class PolicyVersion:
    version: str
    status: str
    created_at_ms: int
    promoted_at_ms: int | None
    source_observations: int
    oos_observations: int
    evaluation_fingerprint: str

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


def _fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    canonical = []
    for row in rows:
        canonical.append(
            {
                "decision_id": _text(row.get("decision_id")),
                "outcome_id": _text(row.get("outcome_id")),
                "state_key": _text(row.get("state_key")),
                "candidate_reward_usd": _number(row.get("candidate_reward_usd")),
                "baseline_reward_usd": _number(row.get("baseline_reward_usd")),
            }
        )
    payload = json.dumps(sorted(canonical, key=lambda x: (x["decision_id"], x["outcome_id"])), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def evaluate_oos(
    candidate_version: str,
    events: Iterable[Mapping[str, Any]],
    thresholds: PromotionThresholds | None = None,
) -> PromotionDecision:
    """Evaluate an immutable candidate strictly on explicit OOS observations.

    Promotion cannot be inferred from training reward or live reward alone.
    Each observation must carry a stable decision/outcome lineage and explicit
    candidate-vs-baseline realized reward from an OOS evaluation dataset.
    """
    cfg = thresholds or PromotionThresholds()
    rows: list[Mapping[str, Any]] = []
    seen_identity: set[tuple[str, str]] = set()
    for row in events:
        if not isinstance(row, Mapping):
            continue
        split = _text(row.get("evaluation_split") or row.get("split")).lower()
        decision_id = _text(row.get("decision_id"))
        outcome_id = _text(row.get("outcome_id"))
        candidate = _number(row.get("candidate_reward_usd"))
        baseline = _number(row.get("baseline_reward_usd"))
        if split not in {"oos", "out_of_sample"}:
            continue
        if not decision_id or not outcome_id or candidate is None or baseline is None:
            continue
        identity = (decision_id, outcome_id)
        if identity in seen_identity:
            continue
        seen_identity.add(identity)
        rows.append(row)

    observations = len(rows)
    states = {_text(row.get("state_key")) for row in rows if _text(row.get("state_key"))}
    advantages: list[float] = []
    advantage_bps: list[float] = []
    wins = 0
    for row in rows:
        candidate = float(row["candidate_reward_usd"])
        baseline = float(row["baseline_reward_usd"])
        advantage = candidate - baseline
        advantages.append(advantage)
        advantage_bps.append(advantage / max(abs(baseline), 1e-9) * 10_000.0)
        wins += int(advantage > 0.0)

    mean_advantage = sum(advantages) / observations if observations else 0.0
    mean_bps = sum(advantage_bps) / observations if observations else 0.0
    win_rate = wins / observations if observations else 0.0
    if observations > 1:
        variance = sum((x - mean_advantage) ** 2 for x in advantages) / (observations - 1)
        lower_bound = mean_advantage - 1.96 * sqrt(max(0.0, variance) / observations)
    else:
        lower_bound = float("-inf")

    failures: list[str] = []
    if observations < max(1, int(cfg.min_oos_observations)):
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

    return PromotionDecision(
        ready=not failures,
        reason="performance_verified" if not failures else failures[0],
        candidate_version=_text(candidate_version),
        observations=observations,
        unique_states=len(states),
        mean_advantage_usd=float(mean_advantage),
        mean_advantage_bps=float(mean_bps),
        win_rate=float(win_rate),
        lower_confidence_advantage_usd=float(lower_bound),
        candidate_reward_usd=float(sum(float(row["candidate_reward_usd"]) for row in rows)),
        baseline_reward_usd=float(sum(float(row["baseline_reward_usd"]) for row in rows)),
        failures=tuple(failures),
    )


class PromotionBoundary:
    """Persistent OOS promotion registry.

    The registry is the only component allowed to turn a candidate policy into
    the production-active policy version. It stores candidate metadata and the
    immutable OOS evaluation fingerprint, but never grants execution/capital
    authority.
    """

    def __init__(self, path: str, thresholds: PromotionThresholds | None = None) -> None:
        self.path = path
        self.thresholds = thresholds or PromotionThresholds()
        self.active_version = "baseline-v0"
        self.versions: dict[str, PolicyVersion] = {}
        self._load()

    def candidate_version(self, policy_snapshot: Mapping[str, Any]) -> str:
        payload = json.dumps(policy_snapshot, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"candidate-{digest}"

    def evaluate(self, candidate_version: str, events: Iterable[Mapping[str, Any]]) -> PromotionDecision:
        return evaluate_oos(candidate_version, events, self.thresholds)

    def promote(
        self,
        decision: PromotionDecision,
        *,
        source_observations: int,
    ) -> PolicyVersion:
        if not decision.ready:
            raise ValueError(f"candidate_not_promotable:{decision.reason}")
        version = _text(decision.candidate_version)
        if not version or version == "baseline-v0":
            raise ValueError("invalid_candidate_version")
        now = int(time.time() * 1000)
        policy = PolicyVersion(
            version=version,
            status="promoted",
            created_at_ms=now,
            promoted_at_ms=now,
            source_observations=max(0, int(source_observations)),
            oos_observations=decision.observations,
            evaluation_fingerprint=_fingerprint([]),
        )
        self.active_version = version
        self.versions[version] = policy
        self._save()
        return policy

    def state(self) -> dict[str, Any]:
        return {
            "active_version": self.active_version,
            "versions": {key: value.to_dict() for key, value in self.versions.items()},
        }

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                return
            active = _text(payload.get("active_version"))
            if active:
                self.active_version = active
            versions = payload.get("versions")
            if isinstance(versions, dict):
                for key, row in versions.items():
                    if isinstance(row, dict):
                        try:
                            self.versions[str(key)] = PolicyVersion(**row)
                        except TypeError:
                            continue
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self.state(), handle, sort_keys=True)
            os.replace(tmp, self.path)
        except (OSError, TypeError, ValueError):
            return
