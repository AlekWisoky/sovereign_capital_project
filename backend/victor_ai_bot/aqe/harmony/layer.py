from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _stable_hash(s: str, *, nbytes: int = 16) -> bytes:
    h = hashlib.blake2b(s.encode("utf-8"), digest_size=nbytes)
    return h.digest()


def _compress_embedding(state_key: str) -> str:
    # deterministic, cheap, privacy-preserving embedding representation
    return _stable_hash(state_key, nbytes=16).hex()


def _softmax(x: Dict[str, float], *, temp: float = 1.0) -> Dict[str, float]:
    if not x:
        return {}
    mx = max(float(v) for v in x.values())
    exps = {k: math.exp((float(v) - mx) / max(1e-9, float(temp))) for k, v in x.items()}
    s = sum(exps.values())
    if s <= 1e-12:
        n = len(exps)
        return {k: 1.0 / n for k in exps}
    return {k: float(v) / float(s) for k, v in exps.items()}


@dataclass
class HarmonyConfig:
    """Phase 4: Harmony layer configuration."""

    global_exploration_budget: float = 1.0
    min_budget_per_agent: float = 0.03
    max_budget_per_agent: float = 0.25

    # novelty scoring
    novelty_decay: float = 0.985
    novelty_floor: float = 0.02

    # stable-state memory
    max_novel_states: int = 20_000

    # credit assignment weights
    use_difference_rewards: bool = True
    use_coma_proxy: bool = True


class InterAgentStabilityMonitor:
    """Tracks joint entropy + coordination collapse indicators."""

    def __init__(self):
        self.last_signal: Dict[str, Any] = {}

    def update(self, *, joint_entropy: float, KL: float, JS: float) -> Dict[str, Any]:
        # cheap stability score: higher is better
        # entropy too low => collapse
        collapse = joint_entropy < 0.55
        unstable = KL > 0.55 or JS > 0.25
        score = float(max(0.0, min(1.0, 0.6 * joint_entropy - 0.25 * KL - 0.25 * JS)))
        sig = {
            "ts": int(time.time()),
            "collapse": bool(collapse),
            "unstable": bool(unstable),
            "stability_score": float(score),
        }
        self.last_signal = sig
        return sig


class ExplorationBudgetAllocator:
    """Global exploration budget allocator.

    Prevents simultaneous over-exploration by capping per-agent α via budgets.
    """

    def __init__(self, *, cfg: HarmonyConfig):
        self.cfg = cfg
        self.last_alloc: Dict[str, float] = {}

    def allocate(self, *, novelty_scores: Dict[str, float]) -> Dict[str, float]:
        names = list(novelty_scores.keys())
        if not names:
            self.last_alloc = {}
            return {}

        # Normalize novelty into weights
        w = {n: max(0.0, float(novelty_scores.get(n, 0.0))) for n in names}
        s = sum(w.values())
        if s <= 1e-12:
            w = {n: 1.0 for n in names}
            s = float(len(names))
        w = {n: float(v) / float(s) for n, v in w.items()}

        B = float(self.cfg.global_exploration_budget)
        lo = float(self.cfg.min_budget_per_agent)
        hi = float(self.cfg.max_budget_per_agent)

        alloc: Dict[str, float] = {}
        # base allocation
        for n in names:
            alloc[n] = lo
        remaining = max(0.0, B - lo * float(len(names)))
        for n in names:
            alloc[n] += remaining * float(w[n])

        # clamp
        for n in names:
            alloc[n] = float(max(lo, min(hi, alloc[n])))

        self.last_alloc = alloc
        return alloc


class CrossAgentCuriositySharing:
    """Shares compressed embeddings of novel states and de-duplicates exploration."""

    def __init__(self, *, cfg: HarmonyConfig):
        self.cfg = cfg
        self._novel: Dict[str, float] = {}  # embedding -> score
        self.last_shared: List[str] = []

    def update(self, *, state_key: str, novelty: float) -> Tuple[float, Dict[str, Any]]:
        emb = _compress_embedding(state_key)
        # decay all
        if self._novel:
            dec = float(self.cfg.novelty_decay)
            for k in list(self._novel.keys()):
                self._novel[k] = float(self._novel[k]) * dec
                if self._novel[k] < float(self.cfg.novelty_floor):
                    self._novel.pop(k, None)
        # update
        existing = float(self._novel.get(emb, 0.0))
        # If already explored, damp novelty so agents don't duplicate.
        damp = 1.0 / (1.0 + 3.0 * existing)
        novelty_adj = float(max(0.0, novelty)) * damp
        self._novel[emb] = float(existing + novelty_adj)

        # cap memory
        if len(self._novel) > int(self.cfg.max_novel_states):
            # drop lowest scores
            items = sorted(self._novel.items(), key=lambda kv: kv[1])
            for k, _ in items[: max(0, len(items) - int(self.cfg.max_novel_states))]:
                self._novel.pop(k, None)

        # share top-k
        top = sorted(self._novel.items(), key=lambda kv: kv[1], reverse=True)[:16]
        self.last_shared = [k for k, _ in top]

        info = {
            "embedding": emb,
            "damp": float(damp),
            "novelty_adj": float(novelty_adj),
            "known_states": int(len(self._novel)),
            "shared_top": list(self.last_shared),
        }
        return novelty_adj, info


class CooperativeCreditAssignment:
    """Cooperative credit assignment using difference rewards + COMA-like proxy.

    We implement a light proxy suitable for production logging:
      - Difference reward: credit_i = r_total * w_i, where w_i is normalized confidence.
      - COMA proxy: advantage_i = Q_i(a_i) - E_{a'_i}[Q_i(a'_i)] using softmax over q_values.

    These values are used for analytics + future training; they do not change trade execution.
    """

    def __init__(self, *, cfg: HarmonyConfig):
        self.cfg = cfg
        self.last_credit: Dict[str, Any] = {}

    def assign(
        self,
        *,
        r_total: float,
        agent_conf: Dict[str, float],
        agent_q: Dict[str, Dict[str, float]],
        chosen_action: str,
    ) -> Dict[str, Any]:
        names = list(agent_conf.keys())
        if not names:
            self.last_credit = {}
            return {}

        # Difference-reward proxy
        conf = {n: max(0.0, float(agent_conf.get(n, 0.0))) for n in names}
        s = sum(conf.values())
        if s <= 1e-12:
            conf = {n: 1.0 for n in names}
            s = float(len(names))
        w = {n: float(v) / float(s) for n, v in conf.items()}

        diff_credit = {n: float(r_total) * float(w[n]) for n in names}

        coma_adv: Dict[str, float] = {}
        if bool(self.cfg.use_coma_proxy):
            for n in names:
                q = dict(agent_q.get(n, {}) or {})
                if not q:
                    coma_adv[n] = 0.0
                    continue
                pi = _softmax(q, temp=1.0)
                exp = 0.0
                for a, p in pi.items():
                    exp += float(p) * float(q.get(a, 0.0))
                coma_adv[n] = float(q.get(chosen_action, 0.0)) - float(exp)

        out = {
            "ts": int(time.time()),
            "r_total": float(r_total),
            "diff_credit": diff_credit,
            "coma_adv": coma_adv,
        }
        self.last_credit = out
        return out


class HarmonyLayer:
    """Phase 4: Multi-agent harmony layer.

    Provides:
      1) Inter-Agent Stability Monitor
      2) Exploration Budget Allocator
      3) Cross-Agent Curiosity Sharing
      4) Cooperative Credit Assignment

    Fully additive; does not mutate the core runtime.
    """

    def __init__(self, *, cfg: Optional[HarmonyConfig] = None):
        self.cfg = cfg or HarmonyConfig()
        self.stability = InterAgentStabilityMonitor()
        self.budget = ExplorationBudgetAllocator(cfg=self.cfg)
        self.curiosity = CrossAgentCuriositySharing(cfg=self.cfg)
        self.credit = CooperativeCreditAssignment(cfg=self.cfg)
        self.last_info: Dict[str, Any] = {}

    def step(
        self,
        *,
        state_key: str,
        novelty: float,
        joint_entropy: float,
        KL: float,
        JS: float,
        agent_conf: Dict[str, float],
        agent_q: Dict[str, Dict[str, float]],
        chosen_action: str,
        r_total: Optional[float] = None,
    ) -> Dict[str, Any]:
        # 1) Stability
        stab = self.stability.update(joint_entropy=float(joint_entropy), KL=float(KL), JS=float(JS))

        # 2) Curiosity sharing
        novelty_adj, cur = self.curiosity.update(state_key=str(state_key), novelty=float(novelty))

        # 3) Budget allocation (novelty per agent weighted by confidence)
        novelty_scores = {n: float(novelty_adj) * float(agent_conf.get(n, 0.0)) for n in agent_conf}
        alloc = self.budget.allocate(novelty_scores=novelty_scores)

        # 4) Credit assignment if reward observed
        credit = {}
        if r_total is not None:
            credit = self.credit.assign(r_total=float(r_total), agent_conf=agent_conf, agent_q=agent_q, chosen_action=str(chosen_action))

        info = {
            "ts": int(time.time()),
            "stability": stab,
            "curiosity": cur,
            "budget": alloc,
            "credit": credit,
        }
        self.last_info = info
        return info
