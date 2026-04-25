from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from victor_ai_bot.determinism import stable_dict_hash

from .config import BehaveAgentConfig
from .calibration import CalibrationTracker
from .learning import RegimeStrategyMemory
from .logger import ImmutableReasoningLogger
from .regime import PersistentRegimeLibrary, RegimeLibrary, detect_regime
from .workflow import generate_strategy_priority

_SAFE_PATH_EXCEPTIONS = (TypeError, ValueError, AttributeError)
_SAFE_RUNTIME_EXCEPTIONS = (TypeError, ValueError, KeyError, AttributeError)
_SAFE_STORAGE_EXCEPTIONS = (OSError, UnicodeDecodeError, TypeError, ValueError)
_SAFE_META_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _component_state(component: Any) -> Dict[str, Any]:
    if component is None or not hasattr(component, "state"):
        return {"enabled": False, "degraded": False}
    try:
        return dict(component.state() or {})
    except _SAFE_RUNTIME_EXCEPTIONS as exc:
        return {"ok": False, "reasonCode": "state_unavailable", "detail": str(exc), "degraded": True}


def _resolve_rel_path(path: str, *, data_dir: str) -> str:
    """Resolve a possibly-relative path against the runtime data_dir.

    Rules:
      - absolute paths are returned as-is
      - paths already under data_dir are returned as-is
      - otherwise, join data_dir/path

    This keeps configs backwards compatible while avoiding accidental
    double-prefixing like backend/data/backend/data/...
    """
    p = str(path or "")
    if not p:
        return p
    dd = str(data_dir or "")
    if os.path.isabs(p):
        return p
    np = os.path.normpath(p)
    ndd = os.path.normpath(dd)
    if ndd and np.startswith(ndd):
        return np
    return os.path.join(dd or "", np)


class BehaveAgentRuntime:
    """BehaveAgent Layer (non-destructive overlay).

    Responsibilities:
      - Context detection engine (regime label + confidence + feature map)
      - Zero-shot workflow generator (strategy priority matrix + intent vector)
      - Interpretable reasoning logs (append-only JSONL)
      - Governance augmentation hooks (transparency + threat escalation hints)

    Hard constraints:
      - Cannot execute trades
      - Cannot override risk limits
      - Must remain deterministic for identical input state
    """

    def __init__(self, cfg: BehaveAgentConfig, *, data_dir: str = "backend/data"):
        self.cfg = cfg
        self.data_dir = str(data_dir)

        # Keep last and previous regime states for drift detection.
        self.prev: Dict[str, Any] = {}
        self.last: Dict[str, Any] = {}
        self.last_overlay: Dict[str, Any] = {}
        self.threat: Dict[str, Any] = {}

        # Persistent regime memory (deterministic; local-only)
        mem_path = _resolve_rel_path(
            str(getattr(cfg, "regime_memory_path", "") or "backend/data/behaveagent/regime_memory.json"),
            data_dir=str(self.data_dir),
        )
        self.library: RegimeLibrary = PersistentRegimeLibrary(
            path=mem_path,
            max_prototypes=int(getattr(cfg, "regime_memory_max", 200) or 200),
            enabled=bool(getattr(cfg, "enable_regime_memory", True)),
        )

        # Deterministic learning memory (strategy outcome per regime)
        strat_mem_path = _resolve_rel_path(
            str(getattr(cfg, "strategy_memory_path", "") or "backend/data/behaveagent/strategy_memory.json"),
            data_dir=str(self.data_dir),
        )
        self.memory = RegimeStrategyMemory(
            path=strat_mem_path,
            enabled=bool(getattr(cfg, "enable_learning_loop", True)),
            min_samples_for_boost=int(getattr(cfg, "min_samples_for_boost", 8) or 8),
            max_weight_boost=float(getattr(cfg, "max_weight_boost", 1.15) or 1.15),
            max_weight_penalty=float(getattr(cfg, "max_weight_penalty", 0.85) or 0.85),
        )

        # Immutable reasoning log
        log_dir = _resolve_rel_path(
            str(getattr(cfg, "reasoning_log_dir", "backend/data/behaveagent") or "backend/data/behaveagent"),
            data_dir=str(self.data_dir),
        )
        log_path = os.path.join(log_dir, "reasoning.jsonl")
        self.logger = ImmutableReasoningLogger(path=log_path)

        # Deterministic calibration tracker (confidence → realized outcome)
        calib_path = _resolve_rel_path(
            str(getattr(cfg, "calibration_path", "backend/data/behaveagent/calibration.json") or "backend/data/behaveagent/calibration.json"),
            data_dir=str(self.data_dir),
        )
        self.calibration = CalibrationTracker(
            path=str(calib_path),
            enabled=bool(getattr(cfg, "enable_learning_loop", True)),
        )

    # -----------------------------
    # Phase B1: Context detection
    # -----------------------------
    def analyze_market(self, *, features: Dict[str, Any], seed: str = "") -> Dict[str, Any]:
        """ANALYZE_MARKET pre-hook.

        Returns:
          - regime_label
          - confidence
          - feature_map

        Deterministic for same (features + library state + seed).
        """

        if not bool(self.cfg.enabled):
            self.prev = dict(self.last)
            self.last = {"ts": int(time.time()), "enabled": False}
            return {"ok": False, "enabled": False}

        f = dict(features or {})
        # Keep previous snapshot for drift detection.
        self.prev = dict(self.last)

        label, conf, info, vec = detect_regime(
            features=f,
            library=self.library,
            similarity_threshold=float(getattr(self.cfg, "similarity_threshold", 0.72) or 0.72),
        )

        # Optional conservative fallback: if similarity clustering is disabled, enforce unknown
        # when similarity is below threshold.
        if (not bool(getattr(self.cfg, "enable_similarity_clustering", True))) and float(conf) < float(getattr(self.cfg, "similarity_threshold", 0.72) or 0.72):
            label = "unknown"

        # Deterministic feature map: include only safe, non-object inputs
        feature_map = {k: f.get(k) for k in sorted(list(f.keys()))}

        self.last = {
            "ts": int(time.time()),
            "enabled": True,
            "regime_label": str(label),
            "confidence": float(_clip(conf, 0.0, 1.0)),
            "description": str((info or {}).get("description") or ""),
            "features": feature_map,
            "mme_vector": list(vec),
        }

        # Touch persistent regime memory (last_seen / n_seen)
        if isinstance(self.library, PersistentRegimeLibrary):
            try:
                self.library.touch(label=str(label))
            except _SAFE_STORAGE_EXCEPTIONS:
                pass

        # Lightweight default priority matrix (LOW aggressiveness) so callers always have one.
        try:
            overlay = generate_strategy_priority(
                regime=str(label),
                confidence=float(conf),
                aggressiveness="LOW",
                profit_goal={"exploration_cap_fraction": float(getattr(self.cfg, "exploration_capital_fraction", 0.10) or 0.10)},
                seed=str(seed),
            )
            self.last_overlay = {
                "ts": int(time.time()),
                "strategy_priority_matrix": dict(overlay.priority),
                "intent_vector": dict(overlay.intent_vector),
                "objectives": dict(overlay.objectives),
            }
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass

        out = {
            "ok": True,
            "enabled": True,
            # aliases to match runtime/api expectations
            "regime_label": str(label),
            "regime": str(label),  # legacy key
            "confidence": float(_clip(conf, 0.0, 1.0)),
            "features": feature_map,
            "feature_map": feature_map,
            "mme_vector": list(vec),
        }
        # include default matrix so downstream multipliers don't silently noop
        out["strategy_priority_matrix"] = dict(self.last_overlay.get("strategy_priority_matrix") or {})
        return out

    # -----------------------------
    # Phase B1: Strategy overlay
    # -----------------------------
    def select_strategy_overlay(
        self,
        *,
        opps: List[Any],
        profit_goal: Optional[Dict[str, Any]] = None,
        aggressiveness: str = "LOW",
        seed: str = "",
    ) -> Dict[str, Any]:
        """SELECT_STRATEGY pre-hook.

        - Generates objectives + strategy priority matrix + intent vector
        - Influences scoring only by annotating opportunities with advisory metadata
        """

        if not bool(self.cfg.enabled):
            return {"ok": False, "enabled": False}

        regime = str(self.last.get("regime_label") or self.last.get("regime") or "unknown")
        conf = float(self.last.get("confidence") or 0.0)
        goal = dict(profit_goal or {})
        goal.setdefault("exploration_cap_fraction", float(getattr(self.cfg, "exploration_capital_fraction", 0.10) or 0.10))

        overlay = generate_strategy_priority(
            regime=regime,
            confidence=float(conf),
            aggressiveness=str(aggressiveness),
            profit_goal=goal,
            seed=seed,
        )

        # Learning loop: adjust weights based on historical outcomes (regime × strategy).
        boosts = self.memory.boost_map(regime=regime) if bool(getattr(self.cfg, "enable_learning_loop", True)) else {}
        pri = dict(overlay.priority)
        if boosts:
            # Apply multiplicative boosts and renormalize
            try:
                w = {k: float(pri.get(k, 0.0)) * float(boosts.get(k, 1.0)) for k in pri.keys()}
                mx = max(w.values()) if w else 1.0
                pri = {k: float(_clip(v / float(mx), 0.0, 1.0)) for k, v in w.items()}
            except (ZeroDivisionError,) + _SAFE_RUNTIME_EXCEPTIONS:
                pass

        # Context graph + interpretable feature weights (deterministic)
        ctx = self._build_context_graph(features=dict(self.last.get("features") or {}), opps=opps)
        feat_weights = ctx.get("feature_weights") or {}
        top_feats = sorted(feat_weights.items(), key=lambda kv: float(kv[1]), reverse=True)[:8]

        # Influence scoring only by annotating opportunities.
        annotation_stats = {"annotated": 0, "skipped": 0}
        for o in (opps or [])[:100]:
            if not isinstance(getattr(o, "meta", None), dict):
                try:
                    o.meta = {}
                except _SAFE_META_EXCEPTIONS:
                    annotation_stats["skipped"] += 1
                    continue
            try:
                o.meta.setdefault("behaveagent", {})
                o.meta["behaveagent"].update(
                    {
                        "regime_label": overlay.regime,
                        "confidence": float(overlay.confidence),
                        "strategy_priority_matrix": dict(pri),
                        "intent_vector": dict(overlay.intent_vector),
                        "objectives": dict(overlay.objectives),
                        "context_graph": dict(ctx),
                    }
                )
                annotation_stats["annotated"] += 1
            except _SAFE_META_EXCEPTIONS:
                annotation_stats["skipped"] += 1

        # Append interpretable reasoning snapshot (immutable best-effort)
        intent_id = stable_dict_hash(
            {
                "seed": str(seed),
                "regime": str(regime),
                "confidence": float(conf),
                "aggressiveness": str(aggressiveness),
                "goal": goal,
                "top_features": top_feats,
                "boosts": boosts,
            }
        )
        self.logger.append(
            {
                "kind": "select_strategy",
                "intent_id": str(intent_id),
                "regime_label": str(regime),
                "confidence": float(conf),
                "aggressiveness": str(aggressiveness),
                "key_signals": {k: (self.last.get("features") or {}).get(k) for k in ["basefee_gwei", "mev_risk", "pending_rate", "volatility_proxy", "avg_margin_ratio", "route_fail_rate", "opp_count"] if k in (self.last.get("features") or {})},
                "feature_weight_ranking": [{"feature": k, "weight": float(v)} for k, v in top_feats],
                "expected_edge": float(ctx.get("expected_edge", 0.0) or 0.0),
                "risk_justification": str(ctx.get("risk_justification") or ""),
                "priority_matrix": dict(pri),
                "intent_vector": dict(overlay.intent_vector),
                "ts": int(time.time()),
            }
        )

        out = {
            "ok": True,
            "enabled": True,
            "regime_label": overlay.regime,
            "regime": overlay.regime,
            "confidence": float(overlay.confidence),
            "strategy_priority_matrix": dict(pri),
            "priority": dict(pri),  # alias
            "intent_vector": dict(overlay.intent_vector),
            "objectives": dict(overlay.objectives),
            "learning_boosts": dict(boosts),
            "context_graph": dict(ctx),
            "annotation_stats": dict(annotation_stats),
        }
        self.last_overlay = {"ts": int(time.time()), **out}
        return out

    # -----------------------------
    # Phase B1: Risk augmentation
    # -----------------------------
    def monitor_risk(self, *, features: Optional[Dict[str, Any]] = None, seed: str = "") -> Dict[str, Any]:
        """MONITOR_RISK augment.

        Detects regime drift and low-confidence states.

        Returns:
          - drift: bool
          - from_regime, to_regime
          - escalate: bool
        """
        if not bool(self.cfg.enabled):
            self.threat = {"ts": int(time.time()), "enabled": False}
            return dict(self.threat)

        cur = dict(self.last or {})
        prev = dict(self.prev or {})

        from_reg = str(prev.get("regime_label") or prev.get("regime") or "unknown")
        to_reg = str(cur.get("regime_label") or cur.get("regime") or "unknown")
        conf = float(cur.get("confidence") or 0.0)

        drift = (from_reg != "" and from_reg != to_reg) and (prev != {})
        low_conf = conf < float(getattr(self.cfg, "regime_confidence_floor", 0.45) or 0.45)

        # Optional auxiliary check (deterministic); never overwrites the current regime.
        aux = None
        try:
            if isinstance(features, dict) and features:
                lbl2, conf2, _, _ = detect_regime(
                    features=dict(features),
                    library=self.library,
                    similarity_threshold=float(getattr(self.cfg, "similarity_threshold", 0.72) or 0.72),
                )
                aux = {"regime_label": str(lbl2), "confidence": float(conf2)}
        except _SAFE_RUNTIME_EXCEPTIONS:
            aux = None

        escalate = bool(low_conf)

        self.threat = {
            "ts": int(time.time()),
            "enabled": True,
            "drift": bool(drift),
            "from_regime": str(from_reg),
            "to_regime": str(to_reg),
            "confidence": float(conf),
            "escalate": bool(escalate),
            "reason": ("unknown_or_low_confidence" if low_conf else ("regime_drift" if drift else "ok")),
            "aux": dict(aux) if isinstance(aux, dict) else None,
            "seed": str(seed),
        }
        return dict(self.threat)

    # -----------------------------
    # Phase B1: Governance augmentation
    # -----------------------------
    def governance_check(
        self,
        *,
        intent_id: str,
        tier: str,
        risk_profile: str,
        decision_factors: Optional[Dict[str, Any]] = None,
        simulation_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GOVERNANCE_CHECK augment.

        - validates reasoning log completeness (basic)
        - enforces transparency minimum score
        - can recommend escalation (never executes)
        """
        if not bool(self.cfg.enabled):
            return {"ok": True, "outcome": "approved", "reason": "disabled"}

        thr = self.monitor_risk(seed=str(intent_id))
        if bool(thr.get("escalate")):
            outcome = "escalated"
            reason = str(thr.get("reason") or "threat_escalation")
        else:
            outcome = "approved"
            reason = "ok"

        # Transparency score: requires reasoning factors and a stable structure.
        transparency = 1.0
        if self.cfg.require_reasoning_log:
            if not isinstance(decision_factors, dict) or len(decision_factors) < 2:
                transparency = 0.0
        transparency = float(_clip(transparency, 0.0, 1.0))

        if transparency < float(self.cfg.transparency_min_score):
            outcome = "rejected"
            reason = "transparency_insufficient"

        row = {
            "intent_id": str(intent_id),
            "regime_label": str(self.last.get("regime_label") or "unknown"),
            "decision_factors": dict(decision_factors or {}),
            "workflow_tier": str(tier),
            "risk_assessment": {"risk_profile": str(risk_profile)},
            "simulation_result": dict(simulation_result or {}),
            "governance_outcome": str(outcome),
            "reviewer": "agent",
            "timestamp": int(time.time()),
            "transparency": float(transparency),
        }
        self.logger.append(row)

        return {"ok": True, "outcome": str(outcome), "reason": str(reason), "transparency": float(transparency)}

    # -----------------------------
    # Learning loop hook (optional)
    # -----------------------------
    def observe_outcome(
        self,
        *,
        regime_label: Optional[str] = None,
        strategy_type: str,
        reward: float,
        ok: bool,
    ) -> None:
        """Update deterministic learning memory.

        Called by runtime after an epoch/trade completion (best-effort).
        """
        if not bool(getattr(self.cfg, "enable_learning_loop", True)):
            return
        r = str(regime_label or self.last.get("regime_label") or "unknown")
        self.memory.update(regime=r, strategy_type=str(strategy_type), reward=float(reward), ok=bool(ok))

        # Calibration loop logging (deterministic)
        conf = float(self.last.get("confidence") or 0.0)
        self.calibration.observe(
            regime=str(r),
            confidence=float(conf),
            reward=float(reward),
            ok=bool(ok),
            strategy_type=str(strategy_type or ""),
        )

    # -----------------------------
    # Reporting / snapshots
    # -----------------------------
    def _build_context_graph(self, *, features: Dict[str, Any], opps: List[Any]) -> Dict[str, Any]:
        """Build a small deterministic context graph + attention weights.

        Output is intentionally lightweight JSON.
        """
        f = dict(features or {})
        # Cheap interpretable signal nodes
        nodes = {
            "Price": float(f.get("avg_margin_ratio", 0.0) or 0.0),
            "Flow": float(f.get("pending_rate", 0.0) or 0.0),
            "Volatility": float(f.get("volatility_proxy", 0.0) or 0.0),
            "Liquidity": float(1.0 - float(_clip(float(f.get("route_fail_rate", 0.0) or 0.0), 0.0, 1.0))),
            "GovernanceRisk": float(f.get("mev_risk", 0.0) or 0.0),
            "Gas": float(_clip(float(f.get("basefee_gwei", 0.0) or 0.0) / 100.0, 0.0, 1.0)),
        }
        # Deterministic attention weights (simple normalized absolute scores)
        abs_scores = {k: abs(float(v)) for k, v in nodes.items()}
        s = sum(abs_scores.values()) or 1.0
        attn = {k: float(_clip(v / s, 0.0, 1.0)) for k, v in abs_scores.items()}

        # Expected edge proxy: avg margin - gas penalty - mev penalty
        edge = float(nodes.get("Price", 0.0)) - float(nodes.get("Gas", 0.0)) * 0.002 - float(nodes.get("GovernanceRisk", 0.0)) * 0.002
        edge = float(edge)

        # Risk justification (interpretable)
        risk_note = ""
        if float(nodes.get("Gas", 0.0)) > 0.6:
            risk_note += "gas_high; "
        if float(nodes.get("GovernanceRisk", 0.0)) > 0.7:
            risk_note += "mev_risk_high; "
        if float(nodes.get("Liquidity", 0.0)) < 0.5:
            risk_note += "liquidity_low; "
        if not risk_note:
            risk_note = "ok"

        return {
            "nodes": nodes,
            "feature_weights": attn,
            "expected_edge": float(edge),
            "risk_justification": str(risk_note).strip(),
        }

    def _storage_state(self) -> Dict[str, Any]:
        storage = {
            "regime_memory": _component_state(self.library),
            "strategy_memory": _component_state(self.memory),
            "reasoning_log": _component_state(self.logger),
            "calibration": _component_state(self.calibration),
        }
        storage["degraded"] = bool(
            any(bool((part or {}).get("degraded", False)) for part in storage.values() if isinstance(part, dict))
        )
        return storage

    def report_state(self) -> Dict[str, Any]:
        return {
            "ts": int(time.time()),
            "cfg": {
                "enabled": bool(self.cfg.enabled),
                "mode": str(self.cfg.mode),
                "regime_confidence_floor": float(self.cfg.regime_confidence_floor),
                "similarity_threshold": float(getattr(self.cfg, "similarity_threshold", 0.72) or 0.72),
                "learning": bool(getattr(self.cfg, "enable_learning_loop", True)),
            },
            "last": dict(self.last),
            "last_overlay": dict(self.last_overlay),
            "threat": dict(self.threat),
            "storage": self._storage_state(),
            "memory": dict(self.memory.summary() or {}),
            "calibration": dict(self.calibration.summary() or {}),
            "recent_reasoning": self.logger.tail(25),
        }

    def snapshot(self) -> Dict[str, Any]:
        """API-friendly alias."""
        return self.report_state()
