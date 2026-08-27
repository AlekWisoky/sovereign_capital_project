from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Tuple

ACTIONS: Tuple[str, ...] = (
    "WAIT",
    "DEFEND",
    "SEEK_OPP",
    "INCREASE_RISK",
    "DECREASE_RISK",
    "EXECUTE",
)
_SAFE = (OSError, TypeError, ValueError, json.JSONDecodeError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _bucket(value: float, edges: Tuple[float, ...], labels: Tuple[str, ...]) -> str:
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def _text(context: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = context.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _prime_context(context: Mapping[str, Any]) -> str:
    """Return a stable economic bucket, never a raw prime identifier.

    Correlation IDs and prime IDs are trace identifiers and must not fragment
    the learning state. Prime *economics* can influence the state through
    stable buckets such as source, availability, capacity, and cost.
    """
    source = _text(context, "capital_source", "prime_source", "internal_prime_source").lower()
    available = bool(context.get("internal_prime_available", context.get("prime_available", False)))
    capacity = float(context.get("prime_capacity_ratio") or context.get("internal_prime_capacity_ratio") or 0.0)
    cost_bps = float(context.get("prime_cost_bps") or context.get("internal_prime_cost_bps") or 0.0)
    source_bucket = "internal" if "internal" in source or "prime" in source else (source or "unknown")
    availability = "avail" if available else "unavailable"
    capacity_bucket = _bucket(capacity, (0.10, 0.50, 0.90), ("cap_low", "cap_mid", "cap_high", "cap_full"))
    cost_bucket = _bucket(cost_bps, (0.0, 5.0, 15.0), ("cost_free", "cost_low", "cost_mid", "cost_high"))
    return f"{source_bucket}:{availability}:{capacity_bucket}:{cost_bucket}"


@dataclass(frozen=True)
class OmarRecommendation:
    state_key: str
    action: str
    confidence: float
    veto: bool
    size_mult: float
    gas_mode: str
    trained: bool
    observations: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OmarRealLearner:
    """Persistent contextual bandit trained from settled real trade outcomes.

    OMAR never executes or signs transactions. Live influence is bounded to a
    veto, downsizing, or gas-mode recommendation; governance remains authoritative.

    Correlation IDs are retained as lineage metadata, not learning features.
    Internal-prime identifiers are likewise lineage-only; prime economics are
    represented by stable buckets so learning generalizes across transactions.
    """

    def __init__(self, *, path: str, alpha: float = 0.12, epsilon: float = 0.0, min_observations: int = 20) -> None:
        self.path = path
        self.alpha = _clip(alpha, 0.001, 1.0)
        self.epsilon = _clip(epsilon, 0.0, 0.25)
        self.min_observations = max(1, int(min_observations))
        self.q: Dict[str, Dict[str, float]] = {}
        self.n: Dict[str, int] = {}
        self.total_observations = 0
        self.last_recommendation: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()

    @staticmethod
    def state_key(context: Mapping[str, Any]) -> str:
        margin = float(context.get("margin_ratio") or 0.0)
        gas = float(context.get("gas_ratio") or 0.0)
        p = float(context.get("p_success") or 0.0)
        dd = float(context.get("drawdown_pct") or 0.0)
        realism = float(context.get("execution_realism") or 0.0)
        stability = float(context.get("stability") or 0.0)
        goal_gap = float(context.get("goal_gap_pct") or 0.0)
        vol = float(context.get("volatility") or 0.0)
        legs = int(context.get("legs") or 2)
        return "|".join(
            (
                _bucket(margin, (0.0, .0005, .001, .002), ("m_neg", "m_tiny", "m_low", "m_mid", "m_hi")),
                _bucket(gas, (.0002, .0005, .001), ("g_vlow", "g_low", "g_mid", "g_hi")),
                _bucket(p, (.70, .80, .90), ("p_low", "p_mid", "p_high", "p_very_high")),
                _bucket(dd, (2.0, 5.0, 8.0), ("dd_low", "dd_mid", "dd_high", "dd_critical")),
                _bucket(realism, (.55, .70, .85), ("r_low", "r_mid", "r_high", "r_strong")),
                _bucket(stability, (.55, .70, .85), ("s_low", "s_mid", "s_high", "s_strong")),
                _bucket(goal_gap, (0.0, 2.0, 5.0), ("goal_on_track", "goal_gap_small", "goal_gap_large", "goal_gap_extreme")),
                _bucket(vol, (.10, .20, .35), ("v_low", "v_mid", "v_high", "v_extreme")),
                _prime_context(context),
                "l3" if legs > 2 else "l2",
            )
        )

    def _ensure(self, key: str) -> None:
        if key not in self.q:
            self.q[key] = {a: 0.0 for a in ACTIONS}
            self.n[key] = 0

    def recommend(self, context: Mapping[str, Any]) -> OmarRecommendation:
        with self._lock:
            key = self.state_key(context)
            self._ensure(key)
            obs = int(self.total_observations)
            if obs < self.min_observations:
                rec = OmarRecommendation(
                    key,
                    "UNTRAINED",
                    0.0,
                    False,
                    1.0,
                    "standard",
                    False,
                    obs,
                    "insufficient_real_outcomes",
                )
                self.last_recommendation = rec.to_dict()
                return rec
            ranked = sorted(self.q[key].items(), key=lambda item: (-float(item[1]), item[0]))
            action, top = ranked[0]
            second = float(ranked[1][1]) if len(ranked) > 1 else 0.0
            confidence = _clip(0.5 + abs(float(top) - second) * 0.05, 0.5, 0.99)
            if action in {"WAIT", "DEFEND"}:
                rec = OmarRecommendation(key, action, confidence, True, 0.0, "standard", True, obs, "learned_defensive_action")
            elif action == "DECREASE_RISK":
                rec = OmarRecommendation(key, action, confidence, False, 0.75, "standard", True, obs, "learned_size_reduction")
            elif action == "SEEK_OPP":
                rec = OmarRecommendation(key, action, confidence, False, 1.0, "fast", True, obs, "learned_opportunity_action")
            elif action == "INCREASE_RISK":
                rec = OmarRecommendation(key, action, confidence, False, 1.0, "standard", True, obs, "learned_risk_action_bounded")
            else:
                rec = OmarRecommendation(key, action, confidence, False, 1.0, "standard", True, obs, "learned_execution_action")
            self.last_recommendation = rec.to_dict()
            return rec

    def observe(self, *, state_key: str, action: str, reward: float, outcome: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not state_key or action not in ACTIONS:
                return {"ok": False, "reason": "invalid_real_learning_transition"}
            self._ensure(state_key)
            reward = _clip(reward, -50.0, 50.0)
            old = float(self.q[state_key].get(action, 0.0))
            self.q[state_key][action] = old + self.alpha * (reward - old)
            self.n[state_key] = int(self.n.get(state_key, 0)) + 1
            self.total_observations += 1
            payload = {
                "event": "omar_real_outcome",
                "ts_ms": int(time.time() * 1000),
                "state_key": state_key,
                "action": action,
                "reward": reward,
                "observations": self.total_observations,
                "outcome": dict(outcome or {}),
            }
            self._append_event(payload)
            if self.total_observations % 5 == 0:
                self.save()
            return {"ok": True, "state_key": state_key, "action": action, "reward": reward, "observations": self.total_observations}

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": True,
                "states": len(self.q),
                "total_observations": self.total_observations,
                "min_observations": self.min_observations,
                "alpha": self.alpha,
                "epsilon": self.epsilon,
                "last_recommendation": dict(self.last_recommendation),
            }

    def save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(
                        {
                            "v": 1,
                            "ts": int(time.time()),
                            "alpha": self.alpha,
                            "epsilon": self.epsilon,
                            "min_observations": self.min_observations,
                            "total_observations": self.total_observations,
                            "q": self.q,
                            "n": self.n,
                        },
                        handle,
                        sort_keys=True,
                    )
                os.replace(tmp, self.path)
            except _SAFE:
                return

    def _append_event(self, payload: Mapping[str, Any]) -> None:
        try:
            path = self.path + ".jsonl"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")
        except _SAFE:
            return

    def _load(self) -> None:
        with self._lock:
            try:
                if not os.path.exists(self.path):
                    return
                with open(self.path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if not isinstance(payload, dict) or int(payload.get("v", 0)) != 1:
                    return
                self.alpha = _clip(payload.get("alpha", self.alpha), 0.001, 1.0)
                self.epsilon = _clip(payload.get("epsilon", self.epsilon), 0.0, 0.25)
                self.min_observations = max(1, int(payload.get("min_observations", self.min_observations)))
                self.total_observations = max(0, int(payload.get("total_observations", 0)))
                raw_q = payload.get("q")
                if isinstance(raw_q, dict):
                    self.q = {
                        str(state): {a: float(values.get(a, 0.0)) for a in ACTIONS}
                        for state, values in raw_q.items()
                        if isinstance(values, dict)
                    }
                raw_n = payload.get("n")
                if isinstance(raw_n, dict):
                    self.n = {str(k): int(v) for k, v in raw_n.items()}
            except _SAFE:
                return
