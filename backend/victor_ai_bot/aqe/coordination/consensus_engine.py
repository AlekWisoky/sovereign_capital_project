from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from victor_ai_bot.determinism import stable_hash_int


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class AgentPerformance:
    agent: str
    weight: float = 1.0
    n: int = 0
    wins: int = 0
    mean_reward: float = 0.0
    var_reward: float = 0.0


class AgentPerformanceTracker:
    """Tracks per-agent performance for weighting.

    Deterministic update: Welford variance with no randomness.
    """

    def __init__(self, *, path: str):
        self.path = str(path)
        self.agents: Dict[str, AgentPerformance] = {}
        self._load()

    def _blank(self) -> Dict[str, AgentPerformance]:
        return {}

    def _coerce_agent(self, agent: Any, payload: Any) -> Optional[AgentPerformance]:
        if not isinstance(payload, dict):
            return None
        name = str(agent).strip()
        if not name:
            return None

        def _float(value: Any, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return float(default)

        def _int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return int(default)

        weight = _float(payload.get("weight", 1.0), 1.0)
        n = max(0, _int(payload.get("n", 0), 0))
        wins = max(0, _int(payload.get("wins", 0), 0))
        wins = min(wins, n)
        return AgentPerformance(
            agent=name,
            weight=_clip(weight, 0.25, 2.50),
            n=n,
            wins=wins,
            mean_reward=_float(payload.get("mean_reward", 0.0), 0.0),
            var_reward=max(0.0, _float(payload.get("var_reward", 0.0), 0.0)),
        )

    def _load(self) -> None:
        if not os.path.exists(self.path):
            self.agents = self._blank()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, JSONDecodeError, ValueError):
            self.agents = self._blank()
            return
        if not isinstance(payload, dict):
            self.agents = self._blank()
            return
        agents_payload = payload.get("agents")
        if not isinstance(agents_payload, dict):
            self.agents = self._blank()
            return
        agents: Dict[str, AgentPerformance] = {}
        for k, v in agents_payload.items():
            coerced = self._coerce_agent(k, v)
            if coerced is not None:
                agents[coerced.agent] = coerced
        self.agents = agents

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {
                "ts": int(time.time()),
                "agents": {k: vars(v) for k, v in self.agents.items()},
            }
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except (OSError, TypeError, ValueError):
            return

    def observe(self, *, agent: str, ok: bool, reward: float) -> None:
        a = str(agent)
        if a not in self.agents:
            self.agents[a] = AgentPerformance(agent=a)
        p = self.agents[a]
        p.n = int(p.n) + 1
        if ok:
            p.wins = int(p.wins) + 1
        # Welford update for mean/variance
        x = float(reward)
        delta = x - float(p.mean_reward)
        p.mean_reward = float(p.mean_reward) + delta / float(p.n)
        delta2 = x - float(p.mean_reward)
        p.var_reward = float(p.var_reward) + delta * delta2
        # periodic persist
        if p.n % 25 == 0:
            self.save()

    def win_rate(self, agent: str) -> float:
        p = self.agents.get(str(agent))
        if not p or p.n <= 0:
            return 0.0
        return float(p.wins) / float(max(1, p.n))

    def snapshot(self) -> Dict[str, Any]:
        return {"ts": int(time.time()), "agents": {k: vars(v) for k, v in self.agents.items()}}


@dataclass
class ConsensusConfig:
    enabled: bool = False
    base_threshold: float = 0.55
    # multiplies threshold in stress (1.0 == no change)
    stress_threshold_mult: float = 1.30
    conflict_penalty: float = 0.25
    weight_lr: float = 0.06
    enforce_on_auto: bool = True
    enforce_on_manual: bool = False


class AgentWeightOptimizer:
    """Light deterministic weight optimizer.

    Reward = risk_adjusted_profit_contribution.
    Underperformers weight down; strong weight up.
    """

    def __init__(self, *, tracker: AgentPerformanceTracker, cfg: ConsensusConfig):
        self.tracker = tracker
        self.cfg = cfg

    def update_weight(self, *, agent: str) -> None:
        p = self.tracker.agents.get(str(agent))
        if not p:
            return
        wr = self.tracker.win_rate(agent)
        # expected reward proxy
        mu = float(p.mean_reward)
        # variance proxy
        var = float(p.var_reward) / float(max(1, p.n))
        score = mu * (0.5 + 0.5 * wr) / max(1e-9, (1.0 + var) ** 0.5)
        # map to [-1,1] using tanh-like clamp
        score = float(_clip(score, -2.0, 2.0)) / 2.0
        lr = float(self.cfg.weight_lr)
        # update with soft floor/ceiling
        new_w = float(p.weight) * (1.0 - lr) + lr * (1.0 + score)
        p.weight = float(_clip(new_w, 0.25, 2.50))


class AgentConsensusEngine:
    """Consensus engine.

    Steps:
      1) Normalize signals
      2) Weight signals dynamically by historical accuracy + regime
      3) Penalize conflicting signals
      4) Reward convergence

    ConsensusScore = weighted_signal_sum - conflict_penalty
    """

    def __init__(self, *, cfg: Optional[ConsensusConfig] = None, tracker: Optional[AgentPerformanceTracker] = None):
        self.cfg = cfg or ConsensusConfig()
        self.tracker = tracker
        self.optimizer = AgentWeightOptimizer(tracker=tracker, cfg=self.cfg) if tracker else None
        self.last: Dict[str, Any] = {}

    def compute(
        self,
        *,
        signals: Dict[str, float],
        confidences: Dict[str, float],
        stress_signals: Optional[Dict[str, float]] = None,
        regime: str = "unknown",
        strategy_type: str = "dex_flash_2leg",
    ) -> Dict[str, Any]:
        if not bool(self.cfg.enabled):
            self.last = {"ts": int(time.time()), "enabled": False}
            return dict(self.last)

        # normalize signals to [-1,1]
        sig = {k: float(_clip(v, -1.0, 1.0)) for k, v in (signals or {}).items()}
        conf = {k: float(_clip(confidences.get(k, 0.5), 0.0, 1.0)) for k in sig.keys()}

        # base weights
        w: Dict[str, float] = {}
        for k in sig.keys():
            base = 1.0
            if self.tracker and k in self.tracker.agents:
                base = float(self.tracker.agents[k].weight)
            # modest regime adjustment
            if str(regime).lower() in {"mev_stress", "gas_spike"} and "Risk" in k:
                base *= 1.10
            w[k] = float(base) * float(0.4 + 0.6 * conf.get(k, 0.5))

        # weighted sum
        wsum = sum(w.values())
        if wsum <= 1e-12:
            wsum = 1.0
        weighted = sum(float(w[k]) * float(sig[k]) for k in sig.keys()) / float(wsum)

        # conflict penalty based on dispersion
        vals = list(sig.values())
        if vals:
            mx = max(vals)
            mn = min(vals)
            dispersion = float(mx - mn)
        else:
            dispersion = 0.0
        conflict_pen = float(self.cfg.conflict_penalty) * float(_clip(dispersion, 0.0, 2.0)) / 2.0
        score = float(_clip(weighted - conflict_pen, -1.0, 1.0))

        # dynamic threshold based on stress signals (deterministic)
        # Optional external stress feed (e.g. gas spikes / mempool stress). Kept optional
        # and deterministic to preserve backwards compatibility.
        stress = float(_clip(float(((stress_signals or {}) or {}).get("stress", 0.0) or 0.0), 0.0, 1.0))
        mult = 1.0 + (float(self.cfg.stress_threshold_mult) - 1.0) * stress
        thr = float(_clip(float(self.cfg.base_threshold) * float(mult), 0.05, 0.95))
        allow = score > (thr - 0.5)  # map threshold into score space

        self.last = {
            "ts": int(time.time()),
            "enabled": True,
            "regime": str(regime),
            "strategy_type": str(strategy_type),
            "signals": sig,
            "weights": w,
            "confidences": conf,
            "weighted_sum": float(weighted),
            "conflict_penalty": float(conflict_pen),
            "consensus_score": float(score),
            "allow": bool(allow),
            "dynamic_threshold": float(thr),
        }
        return dict(self.last)

    def observe_trade_result(self, *, agent_contributions: Dict[str, float], ok: bool, reward: float) -> None:
        """Update tracker and weights post-trade."""
        if not self.tracker:
            return
        for agent, contrib in (agent_contributions or {}).items():
            # risk-adjust reward contribution
            r = float(reward) * float(contrib)
            self.tracker.observe(agent=str(agent), ok=bool(ok), reward=float(r))
            if self.optimizer:
                self.optimizer.update_weight(agent=str(agent))
