from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


def _entropy(dist: Dict[str, float]) -> float:
    e = 0.0
    for p in dist.values():
        p = float(p)
        if p > 1e-12:
            e -= p * math.log(p)
    return float(e)


def _kl(p: Dict[str, float], q: Dict[str, float]) -> float:
    # KL(p||q)
    s = 0.0
    for k, pv in p.items():
        pv = float(pv)
        if pv <= 1e-12:
            continue
        qv = float(q.get(k, 1e-12))
        qv = max(qv, 1e-12)
        s += pv * math.log(pv / qv)
    return float(s)


def _js_divergence(dists: List[Dict[str, float]]) -> float:
    """Mean Jensen–Shannon divergence across a set of distributions.

    Used as a lightweight coordination consistency metric.
    Returns 0 (perfect agreement) .. ~log(K) (high disagreement).
    """
    if not dists:
        return 0.0
    keys = set()
    for d in dists:
        keys |= set(d.keys())
    if not keys:
        return 0.0
    # mean distribution
    m: Dict[str, float] = {k: 0.0 for k in keys}
    for d in dists:
        for k in keys:
            m[k] += float(d.get(k, 0.0))
    n = float(len(dists))
    for k in keys:
        m[k] /= n
    # JS = H(m) - mean(H(d))
    hm = _entropy(m)
    hd = sum(_entropy(d) for d in dists) / n
    return float(max(0.0, hm - hd))


@dataclass
class AdaptiveExplorationConfig:
    """Phase 3: adaptive exploration controller configuration."""

    # Rolling windows
    window: int = 64

    # Instability thresholds
    kl_thresh: float = 0.55
    td_var_thresh: float = 0.20
    entropy_floor: float = 0.55  # in nats; compared to joint entropy

    # α update rates
    alpha_increase: float = 0.020
    alpha_decay: float = 0.010

    # Coordination collapse threshold (higher JS => less coordinated)
    js_thresh: float = 0.25


class _Rolling:
    def __init__(self, n: int):
        self.n = int(max(8, n))
        self.x: List[float] = []

    def add(self, v: float) -> None:
        self.x.append(float(v))
        if len(self.x) > self.n:
            self.x = self.x[-self.n :]

    def mean(self) -> float:
        if not self.x:
            return 0.0
        return float(sum(self.x) / float(len(self.x)))

    def var(self) -> float:
        if len(self.x) < 2:
            return 0.0
        m = self.mean()
        return float(sum((v - m) ** 2 for v in self.x) / float(len(self.x) - 1))


class AdaptiveExplorationController:
    """Adaptive exploration controller (Phase 3).

    Computes stability metrics and adjusts α_i within [min_alpha, max_alpha].

    Metrics (approximate; cheap + robust in production):
      - J_t: variance of joint Q-values (action-value spread)
      - ΔQ: moving average of Q change for chosen action
      - C: coordination consistency (1 - JS divergence proxy)
      - KL: KL divergence between successive joint policies
      - TD_var: rolling variance of TD error

    Behavior:
      - If instability detected OR entropy collapse => increase α_i
      - Else => decay α_i

    This is additive and safe: α only affects the mixture of π_self vs π_team,
    and the system defaults to conservative α bounds.
    """

    def __init__(self, *, cfg: Optional[AdaptiveExplorationConfig] = None):
        self.cfg = cfg or AdaptiveExplorationConfig()
        self._last_joint_pi: Optional[Dict[str, float]] = None
        self._last_q_for_action: Optional[float] = None

        # Rolling stats
        self._kl = _Rolling(self.cfg.window)
        self._entropy = _Rolling(self.cfg.window)
        self._js = _Rolling(self.cfg.window)
        self._j_var = _Rolling(self.cfg.window)
        self._dq = _Rolling(self.cfg.window)
        self._td = _Rolling(self.cfg.window)

        # Last computed flags
        self._unstable_flag: bool = False
        self.last_metrics: Dict[str, Any] = {}

    def observe_policy(
        self,
        *,
        joint_pi: Dict[str, float],
        joint_q: Dict[str, float],
        agent_pis: List[Dict[str, float]],
        chosen_action: str,
    ) -> Dict[str, Any]:
        ent = _entropy(joint_pi)
        self._entropy.add(ent)

        # KL to previous joint policy
        klv = 0.0
        if self._last_joint_pi is not None:
            klv = _kl(joint_pi, self._last_joint_pi)
        self._kl.add(klv)

        # Coordination metric via JS divergence
        js = _js_divergence(agent_pis)
        self._js.add(js)

        # Joint Q-value spread
        qvals = [float(v) for v in (joint_q or {}).values()]
        if len(qvals) >= 2:
            m = sum(qvals) / float(len(qvals))
            jv = sum((v - m) ** 2 for v in qvals) / float(len(qvals) - 1)
        else:
            jv = 0.0
        self._j_var.add(jv)

        # ΔQ for chosen action
        q_chosen = float(joint_q.get(chosen_action, 0.0))
        if self._last_q_for_action is not None:
            self._dq.add(abs(q_chosen - float(self._last_q_for_action)))
        self._last_q_for_action = q_chosen

        # entropy collapse proxy
        entropy_collapse = ent < float(self.cfg.entropy_floor)
        # policy instability proxy
        policy_unstable = klv > float(self.cfg.kl_thresh)
        # coordination collapse proxy
        coord_collapse = js > float(self.cfg.js_thresh)

        self._unstable_flag = bool(entropy_collapse or policy_unstable or coord_collapse)
        self._last_joint_pi = dict(joint_pi)

        metrics = {
            "ts": int(time.time()),
            "joint_entropy": float(ent),
            "KL": float(klv),
            "J_t": float(jv),
            "dQ": float(self._dq.mean()),
            "JS": float(js),
            "coordination_consistency": float(max(0.0, 1.0 - js)),
            "unstable_policy": bool(policy_unstable),
            "entropy_collapse": bool(entropy_collapse),
            "coordination_collapse": bool(coord_collapse),
        }
        self.last_metrics = metrics
        return metrics

    def observe_td_error(self, *, td_error: float) -> Dict[str, Any]:
        self._td.add(float(td_error))
        td_var = float(self._td.var())
        unstable_td = td_var > float(self.cfg.td_var_thresh)
        self._unstable_flag = bool(self._unstable_flag or unstable_td)
        out = dict(self.last_metrics or {})
        out.update({"TD_var": float(td_var), "unstable_td": bool(unstable_td)})
        self.last_metrics = out
        return out

    def update_alphas(
        self,
        *,
        alphas: Dict[str, float],
        min_alpha: float,
        max_alpha: float,
        per_agent_caps: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, float], Dict[str, Any]]:
        """Return new alpha map + metrics."""
        new_a: Dict[str, float] = {}
        inc = float(self.cfg.alpha_increase)
        dec = float(self.cfg.alpha_decay)
        for name, a in (alphas or {}).items():
            a = float(a)
            if self._unstable_flag:
                a = a + inc
            else:
                a = a - dec
            cap = float(max_alpha)
            if per_agent_caps and name in per_agent_caps:
                cap = float(min(cap, float(per_agent_caps[name])))
            a = max(float(min_alpha), min(float(cap), a))
            new_a[name] = float(a)

        metrics = dict(self.last_metrics or {})
        metrics.update({
            "unstable": bool(self._unstable_flag),
            "alpha_update": "increase" if self._unstable_flag else "decay",
            "TD_var": float(self._td.var()),
        })
        return new_a, metrics
