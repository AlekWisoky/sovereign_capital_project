from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Tuple

ACTIONS: Tuple[str, ...] = ("WAIT", "DEFEND", "SEEK_OPP", "INCREASE_RISK", "DECREASE_RISK", "EXECUTE")


def _bucket(value: float, edges: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


def _text(context: Mapping[str, Any], key: str) -> str:
    value = context.get(key)
    return str(value) if value not in (None, "") else ""

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
    """Persistent contextual bandit trained only from the canonical OMAR gate."""
    def __init__(self, *, path: str, alpha: float = 0.12, epsilon: float = 0.0, min_observations: int = 20) -> None:
        self.path = path; self.alpha = max(0.001, min(1.0, float(alpha))); self.epsilon = max(0.0, min(0.25, float(epsilon)))
        self.min_observations = max(1, int(min_observations)); self.q: Dict[str, Dict[str, float]] = {}; self.n: Dict[str, int] = {}; self.total_observations = 0
        self.last_recommendation: Dict[str, Any] = {}; self._lock = threading.RLock(); self._load()

    @staticmethod
    def state_key(context: Mapping[str, Any]) -> str:
        intent = context.get("operator_intent") if isinstance(context.get("operator_intent"), Mapping) else {}
        aggression = str(context.get("aggression_mode") or intent.get("aggression_mode") or "balanced").lower()
        risk = float(context.get("risk_multiplier") or intent.get("risk_multiplier") or 1.0)
        cap = str(context.get("capital_authority_status") or "unknown").lower()
        fresh = str(context.get("capital_authority_freshness") or "unknown").lower()
        return "|".join((
            _bucket(float(context.get("margin_ratio") or 0.0), (0.0, .0005, .001, .002), ("m_neg", "m_tiny", "m_low", "m_mid", "m_hi")),
            _bucket(float(context.get("gas_ratio") or 0.0), (.0002, .0005, .001), ("g_vlow", "g_low", "g_mid", "g_hi")),
            _bucket(float(context.get("p_success") or 0.0), (.70, .80, .90), ("p_low", "p_mid", "p_high", "p_very_high")),
            _bucket(float(context.get("drawdown_pct") or 0.0), (2.0, 5.0, 8.0), ("dd_low", "dd_mid", "dd_high", "dd_critical")),
            aggression, _bucket(risk, (.34, .67, .99), ("risk_min", "risk_low", "risk_mid", "risk_full")), cap, fresh,
        ))

    def _ensure(self, key: str) -> None:
        if key not in self.q: self.q[key] = {a: 0.0 for a in ACTIONS}; self.n[key] = 0

    def recommend(self, context: Mapping[str, Any]) -> OmarRecommendation:
        with self._lock:
            key = self.state_key(context); self._ensure(key); obs = self.total_observations
            if obs < self.min_observations:
                rec = OmarRecommendation(key, "EXECUTE", 0.0, False, 1.0, "standard", False, obs, "insufficient_real_outcomes")
            else:
                action, value = sorted(self.q[key].items(), key=lambda item: (-item[1], item[0]))[0]
                confidence = max(0.5, min(0.99, 0.5 + abs(value) * 0.05))
                if action in {"WAIT", "DEFEND"}: rec = OmarRecommendation(key, action, confidence, True, 0.0, "standard", True, obs, "learned_defensive_action")
                elif action == "DECREASE_RISK": rec = OmarRecommendation(key, action, confidence, False, 0.75, "standard", True, obs, "learned_size_reduction")
                elif action == "SEEK_OPP": rec = OmarRecommendation(key, action, confidence, False, 1.0, "fast", True, obs, "learned_opportunity_action")
                else: rec = OmarRecommendation(key, action, confidence, False, 1.0, "standard", True, obs, "learned_execution_action")
            self.last_recommendation = rec.to_dict(); return rec

    def observe(self, *, state_key: str, action: str, reward: float, outcome: Mapping[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not state_key or action not in ACTIONS: return {"ok": False, "reason": "invalid_real_learning_transition"}
            self._ensure(state_key); old = float(self.q[state_key].get(action, 0.0)); reward = max(-50.0, min(50.0, float(reward)))
            self.q[state_key][action] = old + self.alpha * (reward - old); self.n[state_key] += 1; self.total_observations += 1
            self._append_event({"event": "omar_real_outcome", "ts_ms": int(time.time() * 1000), "state_key": state_key, "action": action, "reward": reward, "observations": self.total_observations, "outcome": dict(outcome or {})})
            self.save()
            return {"ok": True, "state_key": state_key, "action": action, "reward": reward, "observations": self.total_observations}

    def summary(self) -> Dict[str, Any]:
        return {"enabled": True, "states": len(self.q), "total_observations": self.total_observations, "min_observations": self.min_observations, "alpha": self.alpha, "epsilon": self.epsilon, "last_recommendation": dict(self.last_recommendation)}

    def save(self) -> None:
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self.path), exist_ok=True); tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as handle: json.dump({"v": 1, "alpha": self.alpha, "epsilon": self.epsilon, "min_observations": self.min_observations, "total_observations": self.total_observations, "q": self.q, "n": self.n}, handle, sort_keys=True)
                os.replace(tmp, self.path)
            except (OSError, TypeError, ValueError): pass

    def _append_event(self, payload: Mapping[str, Any]) -> None:
        try:
            path = self.path + ".jsonl"; os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle: handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")
        except (OSError, TypeError, ValueError): pass

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path): return
            with open(self.path, "r", encoding="utf-8") as handle: payload = json.load(handle)
            if not isinstance(payload, dict) or int(payload.get("v", 0)) != 1: return
            self.total_observations = max(0, int(payload.get("total_observations", 0))); raw_q = payload.get("q")
            if isinstance(raw_q, dict): self.q = {str(k): {a: float(v.get(a, 0.0)) for a in ACTIONS} for k, v in raw_q.items() if isinstance(v, dict)}
            raw_n = payload.get("n")
            if isinstance(raw_n, dict): self.n = {str(k): int(v) for k, v in raw_n.items()}
        except (OSError, TypeError, ValueError, json.JSONDecodeError): pass
