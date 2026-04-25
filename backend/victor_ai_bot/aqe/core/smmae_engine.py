from __future__ import annotations

import math
from victor_ai_bot.determinism import stable_index_weighted, stable_uniform_0_1
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .actions import ActionSpec, actions_from_rl, normalize_dist, to_action_spec
from ..agents.base import Agent, AgentOutput
from ..agents.investment_agents import default_agent_set
from ..coordination.qmix_vdn import VDN, QMIX
from ..intrinsic.intrinsic_reward import IntrinsicReward, IntrinsicConfig
from ..adaptive import AdaptiveExplorationController, AdaptiveExplorationConfig
from ..harmony import HarmonyLayer, HarmonyConfig
from ..portfolio import PortfolioManager, PortfolioManagerConfig
from victor_ai_bot.caq_kds.multimodal import ENGINE as FUSION_ENGINE
from victor_ai_bot.caq_kds.bus import BUS
from victor_ai_bot.caq_kds.rag_context import RagStrategyContextEngine
from victor_ai_bot.caq_kds.self_evolution import engine as kds_engine


_SAFE_AQE_OPTIONAL_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_NUMERIC_EXCEPTIONS = (TypeError, ValueError)
_SAFE_AGENT_METADATA_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _entropy(dist: Dict[str, float]) -> float:
    e = 0.0
    for p in dist.values():
        p = float(p)
        if p > 1e-12:
            e -= p * math.log(p)
    return float(e)


def _sample(dist: Dict[str, float], *, seed: str) -> str:
    """Deterministic sampling from a distribution.

    The same (dist, seed) will always yield the same sample.
    """

    if not dist:
        return ""
    keys = list(dist.keys())
    weights = [max(0.0, float(dist.get(k, 0.0))) for k in keys]
    idx = stable_index_weighted(weights, f"smmae:sample:{seed}")
    return str(keys[int(idx)])


@dataclass
class SMMAEConfig:
    """SMMAE engine config (Phase 1 baseline)."""

    mixer: str = "vdn"  # vdn|qmix
    explore_prob: float = 0.06  # budgeted exploration probability (global)
    min_alpha: float = 0.01
    max_alpha: float = 0.25

    # Phase 2: intrinsic curiosity
    intrinsic_enabled: bool = True
    intrinsic_beta: float = 0.15

    # Phase 3: adaptive exploration controller
    adaptive_enabled: bool = True

    # Phase 4: harmony layer
    harmony_enabled: bool = True


class SMMAEEngine:
    """Self-Motivated Multi-Agent Engine (SMMAE) — baseline coordination.

    This engine is an *additive* decision layer. It does not change core runtime.

    Phase 1 implements:
      - per-agent π_team and π_self
      - α_i mixture: π_i = α_i*π_self + (1-α_i)*π_team
      - joint coordination baseline: VDN/QMIX style mixing over per-action Q proxies

    Later phases add intrinsic rewards, adaptive α, harmony layer, arbitrage/MEV engines,
    and meta-strategy generation. The interfaces are stable from Phase 1 onward.
    """

    def __init__(self, *, cfg: Optional[SMMAEConfig] = None, agents: Optional[List[Agent]] = None, data_dir: str = ""):
        self.cfg = cfg or SMMAEConfig()
        self.actions: List[ActionSpec] = actions_from_rl()
        self.data_dir = str(data_dir or "")
        self.agents: List[Agent] = agents or list(default_agent_set(data_dir=self.data_dir))
        if self.cfg.mixer == "qmix":
            self.mixer = QMIX(n_agents=len(self.agents))
        else:
            self.mixer = VDN()

        # Phase 10: RAG Strategy Context (CAQ-KDS Layer 3)
        self.rag_ctx = RagStrategyContextEngine(data_dir=self.data_dir)

        # Phase 2: intrinsic curiosity (safe default: enabled, only nudges exploration)
        self.intrinsic = (
            IntrinsicReward(cfg=IntrinsicConfig(beta=float(self.cfg.intrinsic_beta)))
            if bool(getattr(self.cfg, "intrinsic_enabled", True))
            else None
        )

        # Phase 3: adaptive α controller
        self.adaptive = AdaptiveExplorationController(cfg=AdaptiveExplorationConfig()) if bool(getattr(self.cfg, "adaptive_enabled", True)) else None

        # Phase 4: harmony layer
        self.harmony = HarmonyLayer(cfg=HarmonyConfig()) if bool(getattr(self.cfg, "harmony_enabled", True)) else None

        # Portfolio consensus layer (additive)
        self.portfolio = PortfolioManager(cfg=PortfolioManagerConfig())

        # Last agent outputs for learning / XAI
        self._last_agent_outputs = []

        # Per-agent α overrides (Phase 3). Keyed by agent name.
        self._alpha_overrides: Dict[str, float] = {}

        # Bookkeeping for TD error and α updates
        self._last_joint_q: Dict[str, float] = {}
        self._last_chosen_action: str = ""
        self._last_state_key: str = ""
        self._last_agent_alpha: Dict[str, float] = {}
        self._last_agent_conf: Dict[str, float] = {}
        self._last_agent_q: Dict[str, Dict[str, float]] = {}

        # Observability
        self.last_info: Dict[str, Any] = {}
        self.last_reward: Dict[str, Any] = {}

        # Phase 13 (CAQ-KDS Layer 6): Self-evolving knowledge discovery
        # Lazily instantiated per chain (disabled by default).
        self._kds_by_chain: Dict[str, Any] = {}
        self._kds_last_hypothesis_id: str = ""
        self._kds_last_explore: bool = False

        # Superstructure / human command integration (add-only).
        # exploration_cap in [0,1] caps alpha (exploration weight).
        # risk_multiplier is applied later in DecisionEngine (never upsizes).
        self._exploration_cap_current: float = 1.0
        self._risk_multiplier_current: float = 1.0

    def _kds(self, *, chain: str) -> Any:
        c = str(chain or "global")
        if c not in self._kds_by_chain:
            self._kds_by_chain[c] = kds_engine(data_dir=self.data_dir, chain=c)
        return self._kds_by_chain[c]

    def _mix_policy(self, out: AgentOutput) -> Dict[str, float]:
        # Phase 3: allow engine-level α override per agent.
        name = str((out.info or {}).get("name") or "")
        alpha_raw = float(out.alpha)
        if name and name in self._alpha_overrides:
            alpha_raw = float(self._alpha_overrides[name])
        # Human/organizational exploration cap (Phase 17/18).
        cap = float(max(0.0, min(1.0, float(getattr(self, "_exploration_cap_current", 1.0) or 1.0))))
        alpha_cap = float(self.cfg.min_alpha + cap * (self.cfg.max_alpha - self.cfg.min_alpha))
        alpha = float(max(self.cfg.min_alpha, min(alpha_cap, alpha_raw)))
        pi_team = normalize_dist(dict(out.pi_team))
        pi_self = normalize_dist(dict(out.pi_self))
        merged: Dict[str, float] = {}
        for k in set(list(pi_team.keys()) + list(pi_self.keys())):
            merged[k] = alpha * float(pi_self.get(k, 0.0)) + (1.0 - alpha) * float(pi_team.get(k, 0.0))
        return normalize_dist(merged)

    def choose_action(self, *, state: Dict[str, Any], state_key: str) -> Tuple[ActionSpec, Dict[str, Any]]:
        # CAQ-KDS multimodal fusion (safe; enriches agent input)
        try:
            if not isinstance(state.get("S_global"), dict):
                gs = FUSION_ENGINE.fuse(local_state=state)
                global_state = gs.as_dict()
                state["S_global"] = global_state
                # Expose context vector C_t for downstream modules
                try:
                    state["C_t"] = dict((global_state or {}).get("context") or {})
                except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                    pass
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # CAQ-KDS Layer 3: Retrieval-Augmented Strategy Context
        try:
            if not isinstance(state.get("Historical_Context"), dict):
                self.rag_ctx.attach_context(state=state)
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # Human command center (superstructure) — best effort.
        try:
            snap = BUS.snapshot()
            cmd = (snap.get("command") or {}).get("data") or {}
            if isinstance(cmd, dict) and cmd:
                cap = float(cmd.get("exploration_cap", 1.0) or 1.0)
                rm = float(cmd.get("risk_multiplier", 1.0) or 1.0)
                self._exploration_cap_current = float(max(0.0, min(1.0, cap)))
                # keep for debug; sizing uses a safe clamp later
                self._risk_multiplier_current = float(max(0.10, min(2.0, rm)))
                state["Command"] = {
                    "exploration_cap": self._exploration_cap_current,
                    "risk_multiplier": self._risk_multiplier_current,
                    "directive": cmd.get("directive") or {},
                }
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # Phase 13: Self-evolving knowledge discovery tick (add-only)
        # Assumption: hypothesis trials are credited only when an exploratory action is taken.
        kds_info: Dict[str, Any] = {}
        try:
            chain = str(state.get("chain") or state.get("chain_name") or "global")
            kds = self._kds(chain=chain)
            hid = kds.tick(state=state)  # may be None
            if hid:
                self._kds_last_hypothesis_id = str(hid)
            # best-effort: expose kds state to agents via state and debug
            st = kds.state() if hasattr(kds, "state") else {}
            kds_info = {
                "enabled": bool(getattr(kds, "enabled", False)),
                "active_count": int((st or {}).get("active_count", 0) or 0),
                "last_hypothesis_id": str(
                    (st or {}).get("last_hypothesis_id", "") or self._kds_last_hypothesis_id
                ),
            }
            state["KDS"] = kds_info
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            kds_info = {}

        """Return (ActionSpec, debug_info)."""
        agent_outputs: List[AgentOutput] = []

        novelty = 0.0
        intrinsic_components: Dict[str, Any] = {}
        if self.intrinsic is not None:
            try:
                intr = self.intrinsic.intrinsic(state_key=state_key)
                novelty = float(intr.get("r_intrinsic", 0.0) or 0.0)
                intrinsic_components = dict(intr.get("components") or {})
            except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                novelty = 0.0
                intrinsic_components = {}
        # PHASE 9: contextual novelty from GraphRAG
        try:
            ct = state.get("C_t") or {}
            if isinstance(ct, dict):
                ctx_novelty = float(ct.get("novelty", 0.0) or 0.0)
                novelty = float(novelty) + 0.15 * float(ctx_novelty)
                intrinsic_components.setdefault("graph_context_novelty", float(ctx_novelty))
        except _SAFE_NUMERIC_EXCEPTIONS:
            pass
        mixed_pis: List[Dict[str, float]] = []
        agent_qs: List[Dict[str, float]] = []

        agent_alpha_map: Dict[str, float] = {}
        agent_conf: Dict[str, float] = {}
        agent_q_map: Dict[str, Dict[str, float]] = {}
        for ag in self.agents:
            out = ag.act(state=state)
            try:
                out.info = dict(out.info or {})
                out.info.setdefault("name", getattr(ag, "name", ag.__class__.__name__))
            except _SAFE_AGENT_METADATA_EXCEPTIONS:
                pass
            agent_outputs.append(out)
            pi = self._mix_policy(out)
            mixed_pis.append(pi)

            # Convert per-agent Q into action-keyed dict. If missing, use expected EV proxy.
            q = dict(out.q_values or {})
            agent_qs.append(q)

            nm = str(getattr(ag, "name", ag.__class__.__name__))
            agent_alpha_map[nm] = float(out.alpha)
            agent_conf[nm] = float(out.confidence)
            agent_q_map[nm] = q

        # Joint Q via mixer
        if isinstance(self.mixer, QMIX):
            joint_q = self.mixer.mix(agent_qs, state_key=state_key)
        else:
            joint_q = self.mixer.mix(agent_qs)

        # Convert joint Q into a joint policy (softmax with temperature)
        # We do not want unstable argmax-only; keep a little stochasticity.
        temp = 1.0
        # Risk manager can suggest lower temperature
        if float(state.get("risk_level", 0.0) or 0.0) > 0.7:
            temp = 0.7

        # Build logits on the action space.
        keys = [a.key() for a in self.actions]
        # Default missing Q to 0.
        mx = max([float(joint_q.get(k, 0.0)) for k in keys] + [0.0])
        expv: Dict[str, float] = {}
        for k in keys:
            v = float(joint_q.get(k, 0.0))
            # stabilized softmax
            expv[k] = math.exp((v - mx) / max(1e-9, temp))
        joint_pi = normalize_dist(expv)

        # Budgeted exploration: with small probability, sample from a high-entropy mix of agents.
        # Curiosity slightly increases exploration probability.
        explore_p = min(0.25, max(0.0, float(self.cfg.explore_prob) + 0.05 * float(novelty)))
        # Phase 13: apply bounded self-evolution exploration allowance (if enabled)
        try:
            snap = ((state.get("S_global") or {}).get("raw") or {}).get("bus") if isinstance(state.get("S_global"), dict) else None
            if isinstance(snap, dict):
                b = (snap.get("kds") or {}).get("data") or {}
                eb = float(b.get("explore_budget", 0.0) or 0.0)
                explore_p = min(0.25, float(explore_p) + min(0.03, 0.10 * max(0.0, eb)))
        except _SAFE_NUMERIC_EXCEPTIONS:
            pass
        explore = stable_uniform_0_1(f"smmae:explore:{state_key}:{float(explore_p)}") < float(explore_p)
        self._kds_last_explore = bool(explore)
        if explore:
            # average per-agent mixed policies, weighted by confidence
            agg: Dict[str, float] = {k: 0.0 for k in keys}
            wsum = 0.0
            for out, pi in zip(agent_outputs, mixed_pis):
                w = float(max(0.0, min(1.0, out.confidence)))
                wsum += w
                for k in keys:
                    agg[k] += w * float(pi.get(k, 0.0))
            if wsum > 1e-12:
                agg = {k: v / wsum for k, v in agg.items()}
            joint_pi = normalize_dist(agg)

        # Portfolio consensus (weighted signals) — additive bias
        portfolio_info = {}
        try:
            portfolio_info = self.portfolio.aggregate(agent_outputs)
            ps = float(portfolio_info.get("portfolio_signal", 0.0) or 0.0)
            joint_pi = self.portfolio.bias_policy(joint_pi=joint_pi, actions=self.actions, portfolio_signal=ps)
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            portfolio_info = {}

        chosen_key = _sample(joint_pi, seed=str(state_key))
        chosen = to_action_spec(chosen_key, self.actions)

        # Phase 3: observe stability metrics and adapt α over time.
        adaptive_metrics: Dict[str, Any] = {}
        if self.adaptive is not None:
            try:
                adaptive_metrics = self.adaptive.observe_policy(
                    joint_pi=joint_pi,
                    joint_q=joint_q,
                    agent_pis=mixed_pis,
                    chosen_action=str(chosen_key),
                )
            except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                adaptive_metrics = {}

        # Phase 4: harmony step (budget allocation + curiosity sharing)
        harmony_info: Dict[str, Any] = {}
        if self.harmony is not None:
            try:
                harmony_info = self.harmony.step(
                    state_key=str(state_key),
                    novelty=float(novelty),
                    joint_entropy=float(adaptive_metrics.get("joint_entropy", _entropy(joint_pi))),
                    KL=float(adaptive_metrics.get("KL", 0.0)),
                    JS=float(adaptive_metrics.get("JS", 0.0)),
                    agent_conf=agent_conf,
                    agent_q=agent_q_map,
                    chosen_action=str(chosen_key),
                    r_total=None,
                )
            except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                harmony_info = {}

        # stash outputs for learning / XAI
        self._last_agent_outputs = list(agent_outputs)

        debug = {
            "mixer": self.cfg.mixer,
            "explore": bool(explore),
            "explore_p": float(explore_p),
            "novelty": float(novelty),
            "intrinsic": intrinsic_components,
            "portfolio": portfolio_info,
            "agent_signals": {str((o.info or {}).get('name') or i): float(getattr(o, 'signal', 0.0) or 0.0) for i,o in enumerate(agent_outputs)},
            "agent_confidence": {str((o.info or {}).get('name') or i): float(getattr(o, 'confidence', 0.0) or 0.0) for i,o in enumerate(agent_outputs)},
            "agent_features_used": {str((o.info or {}).get('name') or i): dict(getattr(o, 'features_used', {}) or {}) for i,o in enumerate(agent_outputs)},
            "agent_reasoning": {str((o.info or {}).get('name') or i): dict(getattr(o, 'reasoning', {}) or {}) for i,o in enumerate(agent_outputs)},
            "joint_entropy": _entropy(joint_pi),
            "adaptive": adaptive_metrics,
            "harmony": harmony_info,
            "kds": kds_info,
            "agents": [
                {
                    "name": getattr(ag, "name", ag.__class__.__name__),
                    "alpha": float(self._alpha_overrides.get(getattr(ag, "name", ag.__class__.__name__), agent_outputs[i].alpha)),
                    "confidence": float(agent_outputs[i].confidence),
                    "info": dict(agent_outputs[i].info or {}),
                }
                for i, ag in enumerate(self.agents)
            ],
            "chosen_action": chosen_key,
        }
        self.last_info = debug

        # Save for TD-error based updates on receipt.
        self._last_joint_q = dict(joint_q)
        self._last_chosen_action = str(chosen_key)
        self._last_state_key = str(state_key)
        self._last_agent_alpha = dict(agent_alpha_map)
        self._last_agent_conf = dict(agent_conf)
        self._last_agent_q = dict(agent_q_map)
        return chosen, debug


    def observe_trade_result(self, *, state_key: str, action_key: str, r_team: float, ok: bool) -> Dict[str, Any]:
        """Phase 2: observe finalized trade outcome and compute combined reward."""
        info: Dict[str, Any] = {
            "state_key": str(state_key),
            "action_key": str(action_key),
            "r_team": float(r_team),
            "ok": bool(ok),
        }
        if self.intrinsic is None:
            info["r_intrinsic"] = 0.0
            info["r_total"] = float(r_team)
            self.last_reward = info
            return info
        r_total = float(r_team)
        try:
            intr = self.intrinsic.intrinsic(state_key=str(state_key), action_key=str(action_key), ok=bool(ok))
            r_intr = float(intr.get("r_intrinsic", 0.0) or 0.0)
            info["intrinsic_components"] = dict(intr.get("components") or {})
            info["r_intrinsic"] = float(r_intr)
            r_total = float(self.intrinsic.combine(r_team=float(r_team), r_intrinsic=float(r_intr)))
            info["r_total"] = float(r_total)
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            info["r_intrinsic"] = 0.0
            info["r_total"] = float(r_team)
            r_total = float(r_team)

        # Phase 10: persist regime memory for context retrieval
        try:
            rid = ""
            strat = ""
            try:
                # best-effort from last state snapshot
                rid = str((self.rag_ctx._last_state or {}).get("route_id") or "")
                strat = str((self.rag_ctx._last_state or {}).get("strategy") or "")
            except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                rid = ""
                strat = ""
            self.rag_ctx.record_outcome(route_id=rid, strategy=strat, ok=bool(ok), r_team=float(r_team), r_total=float(r_total), meta={"action": str(action_key)})
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # Phase 13: credit hypothesis outcome (only for exploratory actions)
        try:
            if self._kds_last_explore and self._kds_last_hypothesis_id:
                chain = "global"
                try:
                    if isinstance(getattr(self.rag_ctx, "_last_state", None), dict):
                        chain = str((self.rag_ctx._last_state or {}).get("chain") or chain)
                except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
                    pass
                kds = self._kds(chain=chain)
                kds.observe(hypothesis_id=str(self._kds_last_hypothesis_id), ok=bool(ok), r_total=float(r_total))
                info["kds"] = {"hypothesis_id": str(self._kds_last_hypothesis_id), "credited": True}
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # Phase 3: TD error + adaptive α updates
        try:
            if self.adaptive is not None and self._last_chosen_action:
                q_pred = float(self._last_joint_q.get(str(self._last_chosen_action), 0.0))
                td = float(r_total) - float(q_pred)
                self.adaptive.observe_td_error(td_error=float(td))

                # build current alpha map
                cur: Dict[str, float] = {}
                for ag in self.agents:
                    name = str(getattr(ag, "name", ag.__class__.__name__))
                    if name in self._alpha_overrides:
                        cur[name] = float(self._alpha_overrides[name])
                    else:
                        base = float(self._last_agent_alpha.get(name, 0.07))
                        cur[name] = float(max(self.cfg.min_alpha, min(self.cfg.max_alpha, base)))
                # Phase 4: budget caps -> per-agent α caps
                caps: Dict[str, float] = {}
                if self.harmony is not None:
                    b = (self.harmony.budget.last_alloc or {})
                    max_b = float(self.harmony.cfg.max_budget_per_agent)
                    for n, bi in b.items():
                        frac = 0.0 if max_b <= 1e-12 else float(bi) / max_b
                        caps[n] = float(self.cfg.min_alpha + (self.cfg.max_alpha - self.cfg.min_alpha) * max(0.0, min(1.0, frac)))

                new_a, metrics = self.adaptive.update_alphas(alphas=cur, min_alpha=float(self.cfg.min_alpha), max_alpha=float(self.cfg.max_alpha), per_agent_caps=caps or None)
                self._alpha_overrides = dict(new_a)
                info["adaptive_metrics"] = metrics
                info["alpha_overrides"] = dict(self._alpha_overrides)
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass

        # Phase 4: credit assignment (post-receipt)
        try:
            if self.harmony is not None:
                last = dict(getattr(self.adaptive, "last_metrics", {}) or {}) if self.adaptive is not None else {}
                h = self.harmony.step(
                    state_key=str(state_key),
                    novelty=float(info.get("r_intrinsic", 0.0) or 0.0),
                    joint_entropy=float(last.get("joint_entropy", 0.0)),
                    KL=float(last.get("KL", 0.0)),
                    JS=float(last.get("JS", 0.0)),
                    agent_conf=dict(self._last_agent_conf or {}),
                    agent_q=dict(self._last_agent_q or {}),
                    chosen_action=str(self._last_chosen_action or action_key),
                    r_total=float(r_total),
                )
                info["harmony"] = h
        except _SAFE_AQE_OPTIONAL_EXCEPTIONS:
            pass
        # Optional per-agent adaptation updates (opt-in)
        for out in (self._last_agent_outputs or []):
            agname = str((out.info or {}).get('name') or '')
            # only update agents that implement update()
            for ag in self.agents:
                if str(getattr(ag, 'name', '')) == agname and hasattr(ag, 'update'):
                    ag.update(
                        reward=float(r_total),
                        features_used=dict(getattr(out, 'features_used', {}) or {}),
                    )

        self.last_reward = info
        return info
