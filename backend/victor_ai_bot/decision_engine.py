from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from .features import build_features, FeatureVector
from .rl_policy import RlPolicy
from .portfolio_optimizer import candidates_from_opps, opportunity_route_ready, select_portfolio
from .runtime_services.profitability_truth import inspect_profit_after_costs_truth
from .caq_kds.xai import engine as xai_engine
from .caq_kds.reliability import tracker as reliability_tracker
from .caq_kds.bus import BUS


_SAFE_NUMERIC_EXCEPTIONS = (TypeError, ValueError)
_SAFE_METADATA_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)
_SAFE_OPTIONAL_EXCEPTIONS = (
    AttributeError,
    ImportError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)
_SAFE_PERSIST_EXCEPTIONS = (json.JSONDecodeError, OSError, OverflowError, TypeError, ValueError)


def _int(x: Any) -> int:
    if x in (None, ""):
        return 0
    try:
        amount = Decimal(str(x))
    except (InvalidOperation, TypeError, ValueError):
        return 0
    if not amount.is_finite():
        return 0
    try:
        return int(amount)
    except (OverflowError, ValueError):
        return 0


def _exec_ready(o: Any) -> bool:
    """Whether an opportunity is *execution-ready* (deployment/signing).

    Runtime sets meta.safety.exec_ready. If missing, we conservatively return False
    to avoid accidental auto-trade attempts in partially configured deployments.
    When explicit route-plan/runtime metadata exists, it must also confirm the
    opportunity is still executable; signing readiness alone is insufficient.
    """
    try:
        meta = getattr(o, "meta", None)
        if isinstance(meta, dict):
            safety = meta.get("safety")
            if isinstance(safety, dict) and bool(safety.get("exec_ready", False)):
                route_ready, _reason, _reason_codes = opportunity_route_ready(o)
                if not bool(route_ready):
                    return False
                truth = inspect_profit_after_costs_truth(meta)
                return bool(truth.verified and truth.positive)
    except _SAFE_METADATA_EXCEPTIONS:
        return False
    return False


@dataclass
class TradeDecision:
    action: str  # trade|skip
    opp_id: str = ""
    route_id: str = ""
    size_mult: float = 1.0
    borrow_mult: float = 1.0
    gas_mode: str = "standard"
    p_success: float = 0.0
    ev_wei: int = 0
    reason: str = ""
    rl_state: str = ""
    rl_action_index: int = -1
    portfolio: List[str] = field(default_factory=list)


class DecisionEngine:
    """EV-driven decision layer with efficient online RL sizing.

    Brain modes:
    - off: no annotations, no effect
    - shadow: annotate + log, never trade
    - suggest: annotate + log, never auto trade
    - auto: decision chooses trade/skip; runtime executes chosen opp

    Notes:
    - We do NOT upsize beyond the scanned amount without re-quoting. RL actions only downsize.
    - p_success is computed conservatively using recent realized stats + guardrails.
    - RL reward uses realized net profit after gas (when available).
    """

    def __init__(self, *, chain_name: str, data_dir: str, brain_mode: str = "off"):
        self.chain = chain_name
        self.data_dir = str(data_dir or "")
        self.brain_mode = brain_mode

        rl_path = os.path.join(data_dir, "rl", f"rl_{chain_name}.json")
        self.rl = RlPolicy(
            path=rl_path,
            alpha=float(os.environ.get("VICTOR_RL_ALPHA", "0.12")),
            epsilon=float(os.environ.get("VICTOR_RL_EPSILON", "0.08")),
            epsilon_min=float(os.environ.get("VICTOR_RL_EPSILON_MIN", "0.02")),
            epsilon_decay_per_1k=float(os.environ.get("VICTOR_RL_EPSILON_DECAY_PER_1K", "0.02")),
        )

        # Route-level rolling stats (cheap, helps p_success).
        self._route_stats: Dict[str, Dict[str, Any]] = {}
        self._route_stats_path = os.path.join(data_dir, "rl", f"route_stats_{chain_name}.json")
        self._load_route_stats()

        # AQE / SMMAE (optional, additive)
        self._smmae = None

        # Trade throttling
        self._last_trade_block_by_route: Dict[str, int] = {}
        self._last_trade_block_global: int = 0

        # Observability
        self._last_portfolio: List[str] = []
        self._last_smmae_reward: Dict[str, Any] = {}
        # Additive: per-trade reward component trace for observability.
        self._last_reward_trace: Dict[str, Any] = {}

        # Persisted training log (bounded).
        self._log_path = os.path.join(data_dir, "training", f"rl_training_{chain_name}.jsonl")
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        self._log_max_bytes = int(
            os.environ.get("VICTOR_TRAINING_LOG_MAX_BYTES", str(25 * 1024 * 1024))
        )

    # -----------------
    # Public API
    # -----------------
    def set_mode(self, mode: str) -> None:
        self.brain_mode = mode

    def annotate_and_decide(
        self,
        opps: List[Any],
        *,
        current_block: int,
        pending_txs: int,
        auto_enabled: bool,
        cfg: Any,
        gas_budget_remaining_wei: int = 10**30,
        capital_budget_remaining_wei: int | None = None,
        family_capital_remaining_wei: Dict[str, int] | None = None,
    ) -> TradeDecision:
        """Annotate opportunities with `meta["brain"]` and return a decision."""
        mode = str(getattr(cfg.execution, "brain_mode", self.brain_mode) or self.brain_mode)
        self.brain_mode = mode

        # SMMAE modes are additive and map to the existing behavior contract.
        # - smmae_shadow: annotate + log, never trade
        # - smmae_suggest: annotate + log, never trade
        # - smmae_auto: decision may trade
        smmae_mode = False
        if mode.startswith("smmae"):
            smmae_mode = True
            if mode == "smmae_shadow":
                mode = "shadow"
            elif mode == "smmae_suggest":
                mode = "suggest"
            elif mode == "smmae_auto":
                mode = "auto"
            else:
                # unknown smmae_* mode => safe fallback
                mode = "shadow"

        if mode == "off":
            return TradeDecision(action="skip", reason="brain_off")

        # Human command center risk multiplier (add-only). Never upsizes.
        risk_mult = 1.0
        try:
            snap = BUS.snapshot()
            cmd = (snap.get("command") or {}).get("data") or {}
            if isinstance(cmd, dict):
                risk_mult = float(cmd.get("risk_multiplier", 1.0) or 1.0)
        except _SAFE_OPTIONAL_EXCEPTIONS:
            risk_mult = 1.0
        risk_mult_safe = float(max(0.10, min(1.0, risk_mult)))

        # Config-driven guardrails
        cooldown_blocks = int(getattr(cfg.execution, "trade_cooldown_blocks", 1) or 1)
        max_pending = int(getattr(cfg.execution, "max_pending_txs", 1) or 1)
        min_p = float(getattr(cfg.execution, "min_p_success", 0.70) or 0.70)

        # Daily gas budget remaining (runtime-tracked). If <=0, we skip trading.
        gas_budget_remaining_wei = max(0, _int(gas_budget_remaining_wei))
        if capital_budget_remaining_wei is None:
            capital_budget_remaining_wei = None
        else:
            capital_budget_remaining_wei = max(0, _int(capital_budget_remaining_wei))
        family_capital_remaining_wei = {
            str(k): max(0, _int(v))
            for k, v in dict(family_capital_remaining_wei or {}).items()
            if str(k or "")
        }

        # If there are too many pending txs, skip trading.
        if pending_txs >= max_pending:
            self._annotate(opps[:20], reason="pending_txs", p_success=0.0, ev_wei=0, action="skip")
            return TradeDecision(action="skip", reason="too_many_pending")

        best: Optional[Tuple[Any, FeatureVector, float, int, str, int]] = None
        # tuple: (opp, feats, p_success, ev_wei, state, action_idx)
        for o in opps[:50]:
            feats = build_features(o)
            meta = getattr(o, "meta", None)

            # If runtime says not safe or not ready, keep as suggestion-only.
            if not bool(getattr(o, "can_execute", False)) or not _exec_ready(o):
                p = 0.0
                ev = 0
                self._set_brain(o, feats, p, ev, action="skip", reason="not_executable")
                continue

            # Conservative base probability derived from route stats.
            rid = str(getattr(o, "route_id", "") or "")
            p_base = self._p_success_from_route(rid)
            # Penalize low margin
            if feats.margin_ratio < 0.0:
                p_base *= 0.2
            elif feats.margin_ratio < 0.0005:
                p_base *= 0.7
            p_base = max(0.05, min(0.95, p_base))

            # Build RL state
            s = self.rl.bucket_state(
                margin_ratio=feats.margin_ratio,
                gas_ratio=feats.gas_ratio,
                has_curve=feats.has_curve,
                has_balancer=feats.has_balancer,
                legs=feats.legs,
            )

            # Force conservative actions when margin is tiny.
            force_cons = feats.margin_ratio < 0.0005
            seed = f"{int(current_block)}:{str(getattr(o, 'id', '') or '')}"
            a_idx, action, _qv = self.rl.select(s, force_conservative=force_cons, seed=seed)

            # Apply action: size_mult is always <=1.0; borrow_mult may be >1.0.
            size_mult = float(action.size_mult)
            borrow_mult = float(getattr(action, "borrow_mult", 1.0) or 1.0)

            # Apply risk multiplier as a pure shrink factor (organizational/human control).
            if risk_mult_safe < 1.0:
                size_mult = float(max(0.10, min(1.0, size_mult * risk_mult_safe)))
                borrow_mult = float(max(0.25, min(borrow_mult, borrow_mult * risk_mult_safe)))

            # Safety gate: only allow upsizing when p_success and margin are strong.
            if borrow_mult > 1.0:
                if p_base < 0.85 or feats.margin_ratio < 0.0010:
                    borrow_mult = 1.0

            # Hard cap: max_borrow_amount
            max_borrow = _int(getattr(cfg.safety, "max_borrow_amount", "0") or "0")
            base_amount = int(max(1, feats.amount_in_wei))
            if max_borrow > 0:
                max_mult = float(max_borrow) / float(base_amount)
                borrow_mult = min(borrow_mult, max(0.25, max_mult))

            # Predicted scaling (approx): profit scales with notional; gas cost scales with gas mode.
            notional_mult = max(0.10, float(size_mult) * float(borrow_mult))
            profit_after = int(feats.profit_after_costs_wei * notional_mult)

            # Approximate gas cost for alternate gas modes using preset max_fee ratios.
            gas_cost: float = float(feats.gas_cost_wei or 0.0)
            try:
                p = getattr(cfg.execution, "gas_presets", None)
                cur = str(getattr(cfg.execution, "gas_mode", "standard") or "standard")

                def _mf(mode: str) -> float:
                    if not p:
                        return 1.0
                    if mode == "fast":
                        return float(getattr(p, "fast_max_fee_gwei", 40))
                    if mode == "instant":
                        return float(getattr(p, "instant_max_fee_gwei", 60))
                    return float(getattr(p, "standard_max_fee_gwei", 25))

                denom = max(1.0, _mf(cur))
                mult = _mf(action.gas_mode) / denom
                gas_cost = int(float(gas_cost) * float(mult))
            except _SAFE_METADATA_EXCEPTIONS:
                gas_cost = feats.gas_cost_wei

            # EV in wei (simple): p*profit - (1-p)*gas_cost
            ev = int(p_base * profit_after - (1.0 - p_base) * gas_cost)

            # Additive overlay scoring: allow external layers (behaveagent/treasury/...)
            # to influence *scoring only* without mutating core execution semantics.
            overlay = meta.get("overlay") if isinstance(meta, dict) else {}
            try:
                score_mult = float((overlay or {}).get("score_multiplier", 1.0) or 1.0)
                score_mult = max(0.25, min(2.0, score_mult))
            except _SAFE_NUMERIC_EXCEPTIONS:
                score_mult = 1.0
            ev_score = int(float(ev) * float(score_mult))

            # Throttle repeated route attempts.
            last_r = self._last_trade_block_by_route.get(rid, 0)
            if rid and (current_block - last_r) < cooldown_blocks:
                self._set_brain(
                    o,
                    feats,
                    p_base,
                    ev,
                    action="skip",
                    reason="cooldown",
                    rl_state=s,
                    rl_action=a_idx,
                )
                continue

            # Respect p_success threshold
            if p_base < min_p:
                self._set_brain(
                    o,
                    feats,
                    p_base,
                    ev,
                    action="skip",
                    reason="p_below_min",
                    rl_state=s,
                    rl_action=a_idx,
                )
                continue

            # EV must be positive
            if ev <= 0:
                self._set_brain(
                    o,
                    feats,
                    p_base,
                    ev,
                    action="skip",
                    reason="ev_nonpositive",
                    rl_state=s,
                    rl_action=a_idx,
                )
                continue

            # Annotate as candidate
            self._set_brain(
                o,
                feats,
                p_base,
                ev,
                action="trade",
                reason="candidate",
                rl_state=s,
                rl_action=a_idx,
                gas_mode=action.gas_mode,
                size_mult=size_mult,
                borrow_mult=borrow_mult,
                ev_score_wei=ev_score,
                score_multiplier=score_mult,
            )

            if best is None or ev_score > best[3]:
                best = (o, feats, p_base, ev_score, s, a_idx)

        if best is None:
            return TradeDecision(action="skip", reason="no_candidates")

        # --- AQE / SMMAE action recommendation (additive) ---
        smmae_debug: Dict[str, Any] = {}
        if smmae_mode:
            try:
                if self._smmae is None:
                    from victor_ai_bot.aqe import SMMAEEngine, SMMAEConfig

                    mix = os.environ.get("VICTOR_SMMAE_MIXER", "vdn").strip() or "vdn"
                    explore_p = float(os.environ.get("VICTOR_SMMAE_EXPLORE_P", "0.06"))
                    self._smmae = SMMAEEngine(
                        cfg=SMMAEConfig(mixer=mix, explore_prob=explore_p), data_dir=self.data_dir
                    )
                o_best, feats_best, p_best, ev_best, s_best, _aidx_best = best
                state = {
                    "margin_ratio": float(feats_best.margin_ratio),
                    "gas_ratio": float(feats_best.gas_ratio),
                    "legs": int(feats_best.legs),
                    "p_success": float(p_best),
                    "ev_wei": int(ev_best),
                    "fail_streak": int(
                        self._route_stats.get(str(getattr(o_best, "route_id", "") or ""), {}).get(
                            "fail_streak", 0
                        )
                        or 0
                    ),
                    "chain": str(self.chain),
                    "route_id": str(getattr(o_best, "route_id", "") or ""),
                }
                action_obj, smmae_debug = self._require_smmae().choose_action(
                    state=state, state_key=str(s_best)
                )
                # Attach debug to the best opp (additive metadata).
                if isinstance(getattr(o_best, "meta", None), dict):
                    o_best.meta.setdefault("aqe", {})
                    o_best.meta["aqe"].update({"action": action_obj.key(), "debug": smmae_debug})
            except _SAFE_OPTIONAL_EXCEPTIONS:
                smmae_debug = {}

        # Portfolio selection among non-conflicting candidates under gas budget.
        # We select up to max_submit_per_block trades; runtime executes at most one at a time.
        max_trades = int(getattr(cfg.execution, "max_submit_per_block", 1) or 1)
        cand = candidates_from_opps(
            [x for x in opps[:50] if bool(getattr(x, "can_execute", False)) and _exec_ready(x)]
        )
        # Filter by candidates marked trade in meta
        cands = []
        for c in cand:
            o = next((x for x in opps if getattr(x, "id", "") == c.opp_id), None)
            if o is None:
                continue
            bm = (o.meta.get("brain") if isinstance(o.meta, dict) else {}) or {}
            if str(bm.get("action") or "") != "trade":
                continue
            cands.append(c)

        picked = select_portfolio(
            cands,
            gas_budget_remaining_wei=gas_budget_remaining_wei,
            max_trades=max_trades,
            capital_budget_remaining_wei=capital_budget_remaining_wei,
            family_capital_remaining_wei=family_capital_remaining_wei,
        )
        portfolio_ids = [p.opp_id for p in picked]
        self._last_portfolio = list(portfolio_ids)

        # Mark portfolio membership in brain meta.
        pidset = set(portfolio_ids)
        portfolio_rank = {opp_id: idx for idx, opp_id in enumerate(portfolio_ids)}
        for o in opps[:50]:
            meta = getattr(o, "meta", None)
            if not isinstance(meta, dict):
                continue
            bm = meta.get("brain") or {}
            if not isinstance(bm, dict):
                continue
            opp_id = str(getattr(o, "id", "") or "")
            bm["in_portfolio"] = bool(opp_id in pidset)
            if opp_id in portfolio_rank:
                bm["portfolio_rank"] = int(portfolio_rank[opp_id])
            meta["brain"] = bm

        if not portfolio_ids:
            return TradeDecision(action="skip", reason="budget_or_conflicts")

        # Choose the first portfolio item for execution.
        chosen_id = portfolio_ids[0]
        o = next((x for x in opps if getattr(x, "id", "") == chosen_id), None)
        if o is None:
            return TradeDecision(action="skip", reason="portfolio_pick_missing")

        feats = build_features(o)
        rid = str(getattr(o, "route_id", "") or "")
        p_base = self._p_success_from_route(rid)
        bm = (o.meta.get("brain") if isinstance(o.meta, dict) else {}) or {}
        ev = _int(bm.get("ev_wei") or 0)
        s = str(((bm.get("rl") or {}) if isinstance(bm, dict) else {}).get("state") or "")
        a_idx = int(
            ((bm.get("rl") or {}) if isinstance(bm, dict) else {}).get("action_index") or -1
        )

        # Final decision respects brain mode + auto_trading flag
        if mode != "auto" or not auto_enabled:
            return TradeDecision(
                action="skip", reason=f"brain_mode_{mode}", portfolio=portfolio_ids
            )

        # Update throttle timestamps
        self._last_trade_block_by_route[rid] = int(current_block)
        self._last_trade_block_global = int(current_block)

        # Use the chosen action from RL recorded in meta
        bm = (o.meta.get("brain") if isinstance(o.meta, dict) else {}) or {}

        # If SMMAE mode is enabled, override execution knobs for this selected trade.
        if smmae_mode:
            try:
                if self._smmae is None:
                    from victor_ai_bot.aqe import SMMAEEngine, SMMAEConfig

                    mix = os.environ.get("VICTOR_SMMAE_MIXER", "vdn").strip() or "vdn"
                    explore_p = float(os.environ.get("VICTOR_SMMAE_EXPLORE_P", "0.06"))
                    self._smmae = SMMAEEngine(
                        cfg=SMMAEConfig(mixer=mix, explore_prob=explore_p), data_dir=self.data_dir
                    )
                # Use RL state bucket (if present) as stable state_key; else derive from features.
                state_key = s or self.rl.bucket_state(
                    margin_ratio=float(feats.margin_ratio),
                    gas_ratio=float(feats.gas_ratio),
                    has_curve=int(feats.has_curve),
                    has_balancer=int(feats.has_balancer),
                    legs=int(feats.legs),
                )
                state = {
                    "margin_ratio": float(feats.margin_ratio),
                    "gas_ratio": float(feats.gas_ratio),
                    "legs": int(feats.legs),
                    "p_success": float(p_base),
                    "ev_wei": int(ev),
                    "fail_streak": int(self._route_stats.get(rid, {}).get("fail_streak", 0) or 0),
                    "route_id": str(rid),
                    "chain": str(self.chain),
                    "opportunity_id": str(getattr(o, "id", "")),
                    "strategy": str(
                        (
                            (o.meta.get("brain") or {})
                            if isinstance(getattr(o, "meta", None), dict)
                            else {}
                        ).get("action")
                        or ""
                    ),
                }
                act, dbg = self._require_smmae().choose_action(
                    state=state, state_key=str(state_key)
                )
                bm["gas_mode"] = str(act.gas_mode)
                bm["size_mult"] = float(act.size_mult)
                bm["borrow_mult"] = float(act.borrow_mult)
                if isinstance(getattr(o, "meta", None), dict):
                    o.meta.setdefault("aqe", {})
                    o.meta["aqe"].update({"action": act.key(), "debug": dbg})
            except _SAFE_OPTIONAL_EXCEPTIONS:
                pass
        gas_mode = str(bm.get("gas_mode") or getattr(cfg.execution, "gas_mode", "standard"))
        size_mult = float(bm.get("size_mult") or 1.0)
        borrow_mult = float(bm.get("borrow_mult") or 1.0)

        # Human/organizational risk multiplier (pure shrink).
        if risk_mult_safe < 1.0:
            size_mult = float(max(0.10, min(1.0, size_mult * risk_mult_safe)))
            borrow_mult = float(max(0.25, min(borrow_mult, borrow_mult * risk_mult_safe)))

        return TradeDecision(
            action="trade",
            opp_id=str(getattr(o, "id", "")),
            route_id=rid,
            size_mult=size_mult,
            borrow_mult=borrow_mult,
            gas_mode=gas_mode,
            p_success=float(p_base),
            ev_wei=int(ev),
            reason="selected",
            rl_state=s,
            rl_action_index=int(a_idx),
            portfolio=portfolio_ids,
        )

    def on_trade_result(
        self,
        *,
        route_id: str,
        rl_state: str,
        rl_action_index: int,
        amount_in_wei: int,
        expected_after_costs_wei: int,
        realized_after_gas_wei: int,
        ok: bool,
        tx_hash: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update RL and route stats from a finalized trade (receipt)."""
        # Normalize reward by amount_in; scale to manageable magnitude.
        denom = float(max(1, amount_in_wei))
        reward = float(realized_after_gas_wei) / denom
        # Penalize failures even when realized=0 by incorporating expected.
        if not ok:
            reward -= float(abs(expected_after_costs_wei)) / denom
        # Scale for Q-table stability.
        reward_scaled = reward * 1_000_000.0

        # Deterministic reward trace (integer ppm), independent of float rounding.
        denom_i = int(max(1, int(amount_in_wei)))
        realized_i = int(realized_after_gas_wei) if bool(ok) else 0
        penalty_i = int(abs(int(expected_after_costs_wei))) if not bool(ok) else 0
        reward_num = int(realized_i) - int(penalty_i)
        reward_scaled_ppm = int(reward_num * 1_000_000 // denom_i)
        self._last_reward_trace = {
            "ok": bool(ok),
            "amount_in_wei": str(int(amount_in_wei)),
            "expected_after_costs_wei": str(int(expected_after_costs_wei)),
            "realized_after_gas_wei": str(int(realized_after_gas_wei)),
            "reward_num": str(int(reward_num)),
            "denom": str(int(denom_i)),
            "reward_scaled_ppm": int(reward_scaled_ppm),
            "reward_scaled_float": float(reward_scaled),
        }

        if rl_state and rl_action_index >= 0:
            self.rl.update(rl_state, int(rl_action_index), reward_scaled)

        # AQE / SMMAE observer (Phase 2): record intrinsic reward signals.
        try:
            if self._smmae is not None and rl_state:
                aqe_action = ""
                if isinstance(extra, dict):
                    aqe_action = str(extra.get("aqe_action") or "")
                if not aqe_action:
                    aqe_action = f"rl_idx:{int(rl_action_index)}"
                r_team = float(realized_after_gas_wei) / float(max(1, amount_in_wei))
                info = self._smmae.observe_trade_result(
                    state_key=str(rl_state),
                    action_key=str(aqe_action),
                    r_team=float(r_team),
                    ok=bool(ok),
                )
                self._last_smmae_reward = info
        except _SAFE_OPTIONAL_EXCEPTIONS:
            pass

        self._update_route_stats(route_id=route_id, ok=ok, reward_scaled=reward_scaled)
        self._log_training(
            {
                "ts": int(time.time()),
                "chain": self.chain,
                "tx_hash": tx_hash,
                "route_id": route_id,
                "ok": bool(ok),
                "amount_in_wei": str(int(amount_in_wei)),
                "expected_after_costs_wei": str(int(expected_after_costs_wei)),
                "realized_after_gas_wei": str(int(realized_after_gas_wei)),
                "rl_state": rl_state,
                "rl_action_index": int(rl_action_index),
                "reward_scaled": float(reward_scaled),
                "reward_trace": dict(self._last_reward_trace or {}),
                "extra": extra or {},
            }
        )

        # CAQ-KDS Layer 5: Reliability metrics (add-only)
        try:
            extra = dict(extra or {})
            row = {
                "ts": int(time.time()),
                "chain": self.chain,
                "tx_hash": tx_hash,
                "route_id": route_id,
                "ok": bool(ok),
                "amount_in_wei": str(int(amount_in_wei)),
                "expected_after_costs_wei": str(int(expected_after_costs_wei)),
                "realized_after_gas_wei": str(int(realized_after_gas_wei)),
                "extra": extra,
            }
            reliability_tracker(data_dir=self.data_dir, chain=self.chain).observe(row=row)
        except _SAFE_OPTIONAL_EXCEPTIONS:
            pass

        # CAQ-KDS Layer 4: XAI decision explanation + audit log (add-only)
        try:
            extra = dict(extra or {})
            brain = extra.get("brain") if isinstance(extra.get("brain"), dict) else {}
            aqe_dbg = extra.get("aqe_debug") if isinstance(extra.get("aqe_debug"), dict) else {}
            mode = str(extra.get("mode") or "auto")
            opp_id = str(extra.get("opportunity_id") or "")
            strategy = str(extra.get("strategy") or "")
            outcome = {
                "expected_after_costs_wei": str(int(expected_after_costs_wei)),
                "realized_after_gas_wei": str(int(realized_after_gas_wei)),
                "amount_in_wei": str(int(amount_in_wei)),
            }
            expl = xai_engine(data_dir=self.data_dir, chain=self.chain).build(
                chain=self.chain,
                kind="trade",
                mode=mode,
                ok=bool(ok),
                tx_hash=str(tx_hash or ""),
                route_id=str(route_id or ""),
                opportunity_id=opp_id,
                strategy=strategy,
                brain=brain,
                aqe_debug=aqe_dbg,
                reward=dict(self._last_smmae_reward or {}),
                outcome=outcome,
            )
            xai_engine(data_dir=self.data_dir, chain=self.chain).audit.log(expl)
        except _SAFE_OPTIONAL_EXCEPTIONS:
            pass

    def brain_state(self) -> Dict[str, Any]:
        aqe: Dict[str, Any] = {}
        try:
            if self._smmae is not None:
                aqe = {
                    "enabled": True,
                    "mixer": str(getattr(self._smmae.cfg, "mixer", "")),
                    "last_info": dict(getattr(self._smmae, "last_info", {}) or {}),
                    "last_reward": dict(getattr(self._smmae, "last_reward", {}) or {}),
                    "last_observed": dict(self._last_smmae_reward or {}),
                }
            else:
                aqe = {"enabled": False}
        except _SAFE_OPTIONAL_EXCEPTIONS:
            aqe = {"enabled": False}

        return {
            "ok": True,
            "chain": self.chain,
            "brain_mode": self.brain_mode,
            "rl": self.rl.summary(),
            "last_portfolio": list(self._last_portfolio or []),
            "aqe": aqe,
            "reward_trace": dict(self._last_reward_trace or {}),
            "route_stats": {
                "routes": int(len(self._route_stats)),
            },
        }

    def _require_smmae(self) -> Any:
        smmae = self._smmae
        if smmae is None:
            raise RuntimeError("SMMAE policy is unavailable")
        return smmae

    def set_brain_mode(self, mode: str) -> None:
        """Additive operator override for brain mode.

        This is intentionally best-effort and will not throw.
        """
        try:
            m = str(mode or "").strip().lower()
        except _SAFE_METADATA_EXCEPTIONS:
            return
        if not m:
            return
        if m not in {"off", "rl", "baseline"}:
            return
        self.brain_mode = m

    # -----------------
    # Internals
    # -----------------
    def _set_brain(
        self,
        opp: Any,
        feats: FeatureVector,
        p_success: float,
        ev_wei: int,
        *,
        action: str,
        reason: str,
        rl_state: str = "",
        rl_action: int = -1,
        gas_mode: Optional[str] = None,
        size_mult: Optional[float] = None,
        borrow_mult: Optional[float] = None,
        ev_score_wei: Optional[int] = None,
        score_multiplier: Optional[float] = None,
    ) -> None:
        if not isinstance(getattr(opp, "meta", None), dict):
            return
        bm = {
            "ts": int(time.time()),
            "action": action,
            "reason": reason,
            "p_success": float(round(p_success, 4)),
            "ev_wei": str(int(ev_wei)),
            "features": {
                "profit_ratio": float(round(feats.profit_ratio, 6)),
                "gas_ratio": float(round(feats.gas_ratio, 6)),
                "margin_ratio": float(round(feats.margin_ratio, 6)),
                "legs": int(feats.legs),
                "has_curve": int(feats.has_curve),
                "has_balancer": int(feats.has_balancer),
            },
            "rl": {
                "state": rl_state,
                "action_index": int(rl_action),
            },
        }
        if gas_mode:
            bm["gas_mode"] = gas_mode
        if size_mult is not None:
            bm["size_mult"] = float(size_mult)
        if borrow_mult is not None:
            bm["borrow_mult"] = float(borrow_mult)
        if ev_score_wei is not None:
            bm["ev_score_wei"] = str(int(ev_score_wei))
        if score_multiplier is not None:
            bm["score_multiplier"] = float(score_multiplier)
        opp.meta["brain"] = bm

    def _annotate(
        self, opps: List[Any], *, reason: str, p_success: float, ev_wei: int, action: str
    ) -> None:
        for o in opps:
            feats = build_features(o)
            self._set_brain(o, feats, p_success, ev_wei, action=action, reason=reason)

    def _p_success_from_route(self, route_id: str) -> float:
        if not route_id:
            return 0.75
        s = self._route_stats.get(route_id)
        if not s:
            return 0.75
        trials = int(s.get("trials", 0))
        succ = int(s.get("success", 0))
        # Laplace smoothing
        return float((succ + 2) / max(1, (trials + 4)))

    def _update_route_stats(self, *, route_id: str, ok: bool, reward_scaled: float) -> None:
        if not route_id:
            return
        s = self._route_stats.get(route_id)
        if not s:
            s = {"trials": 0, "success": 0, "avg_reward": 0.0}
            self._route_stats[route_id] = s
        s["trials"] = int(s.get("trials", 0)) + 1
        if ok:
            s["success"] = int(s.get("success", 0)) + 1
        # EMA-ish update
        old = float(s.get("avg_reward", 0.0))
        s["avg_reward"] = float(old + 0.05 * (float(reward_scaled) - old))
        # persist occasionally
        if int(s["trials"]) % 10 == 0:
            self._save_route_stats()

    def _save_route_stats(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._route_stats_path), exist_ok=True)
            tmp = self._route_stats_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"v": 1, "ts": int(time.time()), "routes": self._route_stats}, f)
            os.replace(tmp, self._route_stats_path)
        except _SAFE_PERSIST_EXCEPTIONS:
            return

    def _load_route_stats(self) -> None:
        try:
            if not os.path.exists(self._route_stats_path):
                return
            with open(self._route_stats_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict) or int(payload.get("v", 0)) != 1:
                return
            routes = payload.get("routes")
            if isinstance(routes, dict):
                self._route_stats = routes
        except _SAFE_PERSIST_EXCEPTIONS:
            return

    def _log_training(self, row: Dict[str, Any]) -> None:
        try:
            # Bound file size.
            if (
                os.path.exists(self._log_path)
                and os.path.getsize(self._log_path) > self._log_max_bytes
            ):
                # rotate
                base = self._log_path
                rot = base + f".{int(time.time())}.bak"
                os.replace(base, rot)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except _SAFE_PERSIST_EXCEPTIONS:
            return
