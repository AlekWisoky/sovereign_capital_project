from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Tuple

from ..pathing import canonical_data_dir
from ..wealth_goals import goal_patch_changes_state, resolve_goal_patch_payload
from .control_state import unavailable_state
from .runtime_context import WealthGoalSignals, build_wealth_goal_signals


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class WealthGoalService:
    """Canonical wealth-goal coordination.

    The service keeps wealth-goal reasoning deterministic and summary-driven. It exposes
    operator-meaningful posture and progression state while keeping heavy policy work off
    the execution hot path.
    """

    def __init__(self, *, data_dir: str, chain: str = "default") -> None:
        self.data_dir = canonical_data_dir(data_dir)
        self.chain = str(chain or "default")
        self._state_path = os.path.join(self.data_dir, "wealth_goals", f"state_{self.chain}.json")
        self._history_path = os.path.join(
            self.data_dir, "wealth_goals", f"history_{self.chain}.json"
        )
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        self._state = self._load_json(self._state_path, {})
        self._history = self._load_json(self._history_path, [])
        if not isinstance(self._history, list):
            self._history = []
        if not isinstance(self._state, dict):
            self._state = {}
        self._cache_key: Tuple[Any, ...] | None = None
        self._cache_state: Dict[str, Any] | None = None

    def _load_json(self, path: str, default: Any) -> Any:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return default

    def _save_json(self, path: str, payload: Any) -> None:
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except (OSError, ValueError, TypeError):
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except OSError:
                pass

    def _goal_dict(self, runtime: Any) -> Dict[str, Any]:
        treasury = getattr(runtime, "_treasury", None)
        if treasury is None:
            return {}
        goal = getattr(getattr(treasury, "cfg", None), "goal", None)
        if goal is None:
            return {}
        return dict(getattr(goal, "__dict__", {}) or {})

    def _goal_meta(self) -> Dict[str, Any]:
        return dict(self._state.get("meta") or {}) if isinstance(self._state, dict) else {}

    def _ensure_meta(self, goal: Dict[str, Any]) -> Dict[str, Any]:
        meta = self._goal_meta()
        if not meta.get("active_goal_id"):
            ts = int(time.time() * 1000)
            meta["active_goal_id"] = f"goal-{self.chain}-{ts}"
            meta["active_since_ms"] = ts
        if not meta.get("goal_revision"):
            meta["goal_revision"] = 1
        self._state["meta"] = meta
        self._state["goal"] = dict(goal)
        return meta

    def _cache_signature(
        self, goal: Dict[str, Any], meta: Dict[str, Any], sig: WealthGoalSignals
    ) -> Tuple[Any, ...]:
        return (
            float(goal.get("target_return_percentage") or goal.get("target_return_pct") or 0.0),
            int(goal.get("time_horizon_seconds") or 0),
            str(goal.get("risk_tolerance") or "moderate"),
            float(goal.get("max_drawdown_pct") or 10.0),
            float(goal.get("capital_commitment_pct") or 25.0),
            sig.current_return_pct,
            sig.drawdown_pct,
            sig.fund_stage,
            sig.risk_posture,
            sig.hard_stop,
            sig.kill_switch,
            sig.capital_base_usd,
            sig.stability_score,
            sig.execution_realism_score,
            sig.risk_score,
            sig.false_admission_rate,
            sig.false_drop_rate,
            int(meta.get("goal_revision") or 1),
            int(meta.get("achieved_at_ms") or 0),
        )

    def _goal_horizon_days(self, goal: Dict[str, Any]) -> int:
        return max(
            1,
            (
                int(round(float(goal.get("time_horizon_seconds") or 0) / 86400.0))
                if goal.get("time_horizon_seconds")
                else int(goal.get("timeframe_days") or 30)
            ),
        )

    def _goal_velocity(
        self,
        *,
        meta: Dict[str, Any],
        current_return_pct: float,
        target_return_pct: float,
        horizon_days: int,
    ) -> Dict[str, float]:
        now_ms = int(time.time() * 1000)
        active_since_ms = int(meta.get("active_since_ms") or now_ms)
        elapsed_days = max(1.0 / 24.0, (now_ms - active_since_ms) / 86400000.0)
        actual_velocity = current_return_pct / max(elapsed_days, 1e-6)
        required_velocity = (
            0.0 if horizon_days <= 0 else target_return_pct / float(max(1, horizon_days))
        )
        compatibility = (
            1.0
            if required_velocity <= 0
            else _clip(actual_velocity / max(required_velocity, 1e-6), 0.0, 2.0)
        )
        return {
            "elapsed_days": round(elapsed_days, 6),
            "actual_velocity_pct_per_day": round(actual_velocity, 6),
            "required_velocity_pct_per_day": round(required_velocity, 6),
            "horizon_compatibility": round(compatibility, 6),
        }

    def _stability_bucket(self, sig: WealthGoalSignals) -> str:
        if sig.stability_score >= 0.82 and sig.execution_realism_score >= 0.82:
            return "strong"
        if sig.stability_score >= 0.62 and sig.execution_realism_score >= 0.60:
            return "stable"
        if sig.stability_score >= 0.45 and sig.execution_realism_score >= 0.45:
            return "watch"
        return "fragile"

    def _next_goal_suggestion(
        self,
        *,
        goal: Dict[str, Any],
        meta: Dict[str, Any],
        sig: WealthGoalSignals,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        current_target_pct = float(
            goal.get("target_return_percentage") or goal.get("target_return_pct") or 0.0
        )
        current_return_pct = sig.current_return_pct
        achieved = current_target_pct > 0.0 and current_return_pct >= current_target_pct
        risk = str(goal.get("risk_tolerance") or "moderate").lower()
        horizon_days = self._goal_horizon_days(goal)
        stage = str(sig.fund_stage or "unknown").lower()
        velocity = self._goal_velocity(
            meta=meta,
            current_return_pct=current_return_pct,
            target_return_pct=current_target_pct,
            horizon_days=horizon_days,
        )
        blocked_reasons: List[str] = []
        reasons: List[str] = []

        if sig.hard_stop:
            blocked_reasons.append("drawdown_hard_stop_active")
        if sig.kill_switch:
            blocked_reasons.append("kill_switch_active")
        if sig.drawdown_pct >= float(goal.get("max_drawdown_pct") or 10.0) * 0.85:
            blocked_reasons.append("drawdown_near_goal_limit")
        if sig.execution_realism_score < 0.55:
            blocked_reasons.append("execution_realism_below_threshold")
        if sig.stability_score < 0.55:
            blocked_reasons.append("stability_below_threshold")
        if sig.risk_score > 0.85:
            blocked_reasons.append("portfolio_risk_too_high")
        if sig.false_admission_rate > 0.18:
            blocked_reasons.append("false_admission_rate_too_high")
        if sig.false_drop_rate > 0.22:
            blocked_reasons.append("false_drop_rate_too_high")
        if not achieved and float(velocity.get("horizon_compatibility") or 0.0) < 0.75:
            blocked_reasons.append("goal_velocity_below_horizon")

        ladder_mult = {"conservative": 1.06, "moderate": 1.12, "aggressive": 1.18}.get(risk, 1.12)
        base_step = {"conservative": 1.0, "moderate": 1.75, "aggressive": 2.5}.get(risk, 1.75)
        capital_scale = _clip(
            (sig.capital_base_usd / 5000.0) ** 0.18 if sig.capital_base_usd > 0 else 1.0, 0.85, 1.25
        )
        realism_scale = _clip(0.75 + sig.execution_realism_score * 0.35, 0.75, 1.10)
        stability_scale = _clip(0.75 + sig.stability_score * 0.35, 0.75, 1.10)
        stage_scale = (
            0.70
            if stage in {"bootstrap", "v1_only"}
            else (0.92 if stage in {"staging", "stage_1", "stage_2"} else 1.05)
        )
        drawdown_scale = (
            0.65 if sig.drawdown_pct >= 8.0 else (0.85 if sig.drawdown_pct >= 5.0 else 1.0)
        )
        recent_achievements = [
            row
            for row in history[-6:]
            if isinstance(row, dict) and str(row.get("status") or "") == "achieved"
        ]
        achievement_scale = 1.0 + min(0.08, max(0, len(recent_achievements) - 1) * 0.02)
        progress_ratio = (
            current_return_pct / max(current_target_pct, 0.001) if current_target_pct > 0 else 0.0
        )
        progress_scale = (
            1.0
            if achieved
            else (0.85 if progress_ratio >= 0.75 else (0.70 if progress_ratio < 0.50 else 0.80))
        )
        urgency = "steady"
        if achieved:
            urgency = "unlock_next_goal"
        elif progress_ratio < 0.40 and horizon_days <= 21:
            urgency = "catch_up"
        elif float(velocity.get("horizon_compatibility") or 1.0) < 0.90:
            urgency = "catch_up"
        elif sig.drawdown_pct >= 5.0 or sig.risk_score > 0.75:
            urgency = "stabilize"
        raw_next = (
            current_target_pct
            if current_target_pct > 0
            else {"conservative": 6.0, "moderate": 9.0, "aggressive": 12.0}.get(risk, 9.0)
        )
        if achieved:
            reasons.append("goal_achieved_allows_progression")
            raw_next = max(current_target_pct + base_step, current_target_pct * ladder_mult)
        else:
            reasons.append("goal_in_progress")
            raw_next = max(raw_next, current_target_pct)
        raw_next *= (
            capital_scale
            * realism_scale
            * stability_scale
            * stage_scale
            * drawdown_scale
            * achievement_scale
            * progress_scale
        )
        if stage in {"bootstrap", "v1_only"} and raw_next > current_target_pct + 3.0:
            raw_next = current_target_pct + 3.0
            reasons.append("fund_stage_caps_next_goal")
        if not achieved and progress_ratio < 0.50:
            raw_next = max(current_target_pct, raw_next * 0.92)
            reasons.append("progress_gap_caps_escalation")
        if not achieved and float(velocity.get("horizon_compatibility") or 1.0) < 0.90:
            raw_next = max(current_target_pct, raw_next * 0.94)
            reasons.append("velocity_gap_caps_escalation")
        if blocked_reasons:
            raw_next = min(raw_next, current_target_pct)
        next_target = round(_clip(raw_next, max(1.0, current_target_pct or 1.0), 175.0), 2)
        next_timeframe_days = max(7, min(90, int(round(horizon_days * (1.0 if achieved else 1.1)))))
        aggressiveness_hint = _clip(
            {"conservative": 0.92, "moderate": 1.0, "aggressive": 1.08}.get(risk, 1.0)
            * (0.80 + sig.execution_realism_score * 0.30)
            * (0.75 + sig.stability_score * 0.25),
            0.55,
            1.15,
        )
        return {
            "allowed": not blocked_reasons,
            "target_return_pct": next_target,
            "timeframe_days": next_timeframe_days,
            "risk_tolerance": risk,
            "urgency": urgency,
            "goal_horizon_days": horizon_days,
            "aggressiveness_hint": round(aggressiveness_hint, 6),
            "reasons": reasons,
            "blocked_reasons": blocked_reasons,
            "goal_ladder": [round(current_target_pct, 2)] if current_target_pct > 0 else [],
            "capital_base_usd": round(sig.capital_base_usd, 2),
            "stability_score": sig.stability_score,
            "execution_realism_score": sig.execution_realism_score,
            "risk_score": sig.risk_score,
            "goal_velocity_pct_per_day": float(velocity.get("actual_velocity_pct_per_day") or 0.0),
            "required_velocity_pct_per_day": float(
                velocity.get("required_velocity_pct_per_day") or 0.0
            ),
            "goal_horizon_compatibility": float(velocity.get("horizon_compatibility") or 1.0),
            "elapsed_goal_days": float(velocity.get("elapsed_days") or 0.0),
        }

    def _posture(
        self, *, goal: Dict[str, Any], sig: WealthGoalSignals, suggestion: Dict[str, Any]
    ) -> Dict[str, Any]:
        target = float(goal.get("target_return_percentage") or goal.get("target_return_pct") or 0.0)
        risk = str(goal.get("risk_tolerance") or "moderate").lower()
        progress = (
            0.0
            if target <= 0
            else _clip((sig.current_return_pct / max(target, 0.001)) * 100.0, 0.0, 200.0)
        )
        aggressiveness_cap = 1.0
        pacing = "steady"
        reasons: List[str] = []
        if sig.hard_stop or sig.kill_switch:
            aggressiveness_cap = 0.45
            pacing = "defensive"
            reasons.append("safety_state_active")
        elif sig.drawdown_pct >= float(goal.get("max_drawdown_pct") or 10.0) * 0.8:
            aggressiveness_cap = 0.65
            pacing = "slow"
            reasons.append("drawdown_near_limit")
        elif (
            sig.stability_score < 0.55
            or sig.execution_realism_score < 0.55
            or sig.risk_score > 0.75
        ):
            aggressiveness_cap = 0.78
            pacing = "measured"
            reasons.append("stability_execution_or_risk_limited")
        elif (
            progress < 50.0
            and risk in {"moderate", "aggressive"}
            and bool(suggestion.get("allowed", True))
        ):
            aggressiveness_cap = 1.08 if risk == "moderate" else 1.18
            pacing = "accelerate"
            reasons.append("goal_gap_requires_catch_up")
        elif progress >= 100.0:
            aggressiveness_cap = 0.90
            pacing = "lock_in"
            reasons.append("goal_achieved_lock_in")
        return {
            "progress_pct": round(progress, 2),
            "aggressiveness_cap": round(aggressiveness_cap, 6),
            "pacing": pacing,
            "reasons": reasons,
        }

    def _goal_status(self, *, achieved: bool, suggestion: Dict[str, Any]) -> str:
        if achieved:
            return "achieved"
        if not bool(suggestion.get("allowed", True)):
            return "blocked"
        return "active"

    def state(self, runtime: Any) -> Dict[str, Any]:
        goal = self._goal_dict(runtime)
        if not goal:
            return unavailable_state(
                "treasury_goal_unavailable",
                include_error=True,
                extra={
                    "goal": None,
                    "state": {},
                    "recommendation": {},
                    "explanation": {},
                    "history": [],
                },
            )
        meta = self._ensure_meta(goal)
        sig = build_wealth_goal_signals(runtime)
        cache_sig = self._cache_signature(goal, meta, sig)
        if self._cache_key == cache_sig and self._cache_state is not None:
            return dict(self._cache_state)

        target_return_pct = float(
            goal.get("target_return_percentage") or goal.get("target_return_pct") or 0.0
        )
        timeframe_days = self._goal_horizon_days(goal)
        achieved = bool(target_return_pct > 0 and sig.current_return_pct >= target_return_pct)
        if achieved and not meta.get("achieved_at_ms"):
            meta["achieved_at_ms"] = int(time.time() * 1000)
            self._history.append(
                {
                    "goal_id": meta.get("active_goal_id"),
                    "target_return_pct": target_return_pct,
                    "achieved_at_ms": meta["achieved_at_ms"],
                    "current_return_pct": sig.current_return_pct,
                    "risk_tolerance": str(goal.get("risk_tolerance") or "moderate"),
                    "status": "achieved",
                }
            )
            self._save_json(self._history_path, self._history)

        suggestion = self._next_goal_suggestion(
            goal=goal, meta=meta, sig=sig, history=self._history
        )
        posture = self._posture(goal=goal, sig=sig, suggestion=suggestion)
        goal_status = self._goal_status(achieved=achieved, suggestion=suggestion)
        explanation = {
            "why_active_goal": f"Active goal targets {target_return_pct:.2f}% over {timeframe_days} days because operator risk tolerance is {str(goal.get('risk_tolerance') or 'moderate')}, fund stage is {sig.fund_stage}, and capital base is about ${sig.capital_base_usd:.2f}.",
            "why_posture": f"System pacing is {posture['pacing']} with aggressiveness cap {posture['aggressiveness_cap']:.2f} because drawdown is {sig.drawdown_pct:.2f}%, stability score is {sig.stability_score:.2f}, execution realism is {sig.execution_realism_score:.2f}, risk posture is {sig.risk_posture}, and goal velocity compatibility is {float(suggestion.get('goal_horizon_compatibility') or 1.0):.2f}.",
            "why_next_goal": f"Next-goal suggestion is {float(suggestion.get('target_return_pct') or target_return_pct):.2f}% because {', '.join(list(suggestion.get('reasons') or [])) or 'goal progression remains bounded by realized performance.'}",
            "why_not_larger": f"A larger next goal is blocked by {', '.join(list(suggestion.get('blocked_reasons') or [])) or 'bounded progression and realism thresholds'}.",
        }
        state = {
            "ok": True,
            "goal": {
                "target_return_percentage": target_return_pct,
                "target_return_pct": target_return_pct,
                "time_horizon_seconds": int(
                    goal.get("time_horizon_seconds") or timeframe_days * 86400
                ),
                "timeframe_days": timeframe_days,
                "risk_tolerance": str(goal.get("risk_tolerance") or "moderate"),
                "max_drawdown_pct": float(goal.get("max_drawdown_pct") or 10.0),
                "capital_commitment_pct": float(goal.get("capital_commitment_pct") or 25.0),
                "goal_status": goal_status,
            },
            "state": {
                "goalId": str(meta.get("active_goal_id") or ""),
                "goalRevision": int(meta.get("goal_revision") or 1),
                "activeSinceMs": int(meta.get("active_since_ms") or 0),
                "achievedAtMs": int(meta.get("achieved_at_ms") or 0) if achieved else 0,
                "currentReturnPct": sig.current_return_pct,
                "progressPct": float(posture["progress_pct"]),
                "goalAchieved": achieved,
                "goalStatus": goal_status,
                "targetReturnPct": target_return_pct,
                "timeframeDays": timeframe_days,
                "goalHorizonDays": int(suggestion.get("goal_horizon_days") or timeframe_days),
                "riskTolerance": str(goal.get("risk_tolerance") or "moderate"),
                "maxDrawdownPct": float(goal.get("max_drawdown_pct") or 10.0),
                "capitalCommitmentPct": float(goal.get("capital_commitment_pct") or 25.0),
                "fundStage": sig.fund_stage,
                "riskPosture": sig.risk_posture,
                "drawdownPct": sig.drawdown_pct,
                "hardStopActive": sig.hard_stop,
                "killSwitchActive": sig.kill_switch,
                "stabilityScore": sig.stability_score,
                "executionRealismScore": sig.execution_realism_score,
                "capitalBaseUsd": round(sig.capital_base_usd, 2),
                "riskScore": sig.risk_score,
                "falseAdmissionRate": sig.false_admission_rate,
                "falseDropRate": sig.false_drop_rate,
                "aggressivenessCap": float(posture["aggressiveness_cap"]),
                "pacing": str(posture["pacing"]),
                "pacingReasons": list(posture["reasons"]),
                "suggestedNextTargetPct": float(
                    suggestion.get("target_return_pct") or target_return_pct
                ),
                "nextGoalAllowed": bool(suggestion.get("allowed", True)),
                "nextGoalReasons": list(suggestion.get("reasons") or []),
                "nextGoalBlockedReasons": list(suggestion.get("blocked_reasons") or []),
                "goalLadder": list(suggestion.get("goal_ladder") or []),
                "goalUrgency": str(suggestion.get("urgency") or "steady"),
                "nextGoalAggressivenessHint": float(
                    suggestion.get("aggressiveness_hint") or posture["aggressiveness_cap"]
                ),
                "blockedGoalReasonCodes": list(suggestion.get("blocked_reasons") or []),
                "goalVelocityPctPerDay": float(suggestion.get("goal_velocity_pct_per_day") or 0.0),
                "requiredVelocityPctPerDay": float(
                    suggestion.get("required_velocity_pct_per_day") or 0.0
                ),
                "goalHorizonCompatibility": float(
                    suggestion.get("goal_horizon_compatibility") or 1.0
                ),
                "elapsedGoalDays": float(suggestion.get("elapsed_goal_days") or 0.0),
            },
            "recommendation": suggestion,
            "explanation": explanation,
            "history": list(self._history)[-10:],
        }
        self._state["meta"] = meta
        self._state["goal"] = state["goal"]
        self._save_json(self._state_path, self._state)
        self._cache_key = cache_sig
        self._cache_state = dict(state)
        return state

    def set_goal(
        self, runtime: Any, payload: Dict[str, Any], *, actor: str = "operator", reason: str = ""
    ) -> Dict[str, Any]:
        treasury = getattr(runtime, "_treasury", None)
        if treasury is None:
            return unavailable_state(
                "treasury_disabled",
                include_error=True,
                extra={"goal": None, "service": "wealth_goal_service"},
            )
        goal = getattr(getattr(treasury, "cfg", None), "goal", None)
        if goal is None:
            return {
                "ok": False,
                "error": "goal_missing",
                "reason_code": "goal_missing",
                "goal": None,
            }
        current_goal = self._goal_dict(runtime)
        resolved = resolve_goal_patch_payload(payload, current_goal=current_goal)
        changed = goal_patch_changes_state(resolved, current_goal=current_goal)
        for src, attr in [
            ("target_return_percentage", "target_return_percentage"),
            ("time_horizon_seconds", "time_horizon_seconds"),
            ("risk_tolerance", "risk_tolerance"),
            ("max_drawdown_pct", "max_drawdown_pct"),
            ("capital_commitment_pct", "capital_commitment_pct"),
        ]:
            value = resolved[src]
            if getattr(goal, attr) != value:
                setattr(goal, attr, value)
                changed = True
        if not changed:
            state = self.state(runtime)
            state["changed"] = False
            return state

        treasury.cfg.goal = goal
        treasury._save_goal()
        meta = self._goal_meta()
        if changed:
            ts = int(time.time() * 1000)
            previous_goal = (
                dict(self._state.get("goal") or {}) if isinstance(self._state, dict) else {}
            )
            if previous_goal:
                self._history.append(
                    {
                        "goal_id": meta.get("active_goal_id"),
                        "target_return_pct": float(
                            previous_goal.get("target_return_percentage")
                            or previous_goal.get("target_return_pct")
                            or 0.0
                        ),
                        "closed_at_ms": ts,
                        "status": "replaced",
                        "reason": str(reason or "goal_update"),
                    }
                )
            next_rev = int(meta.get("goal_revision") or 0) + 1
            meta = {
                "active_goal_id": f"goal-{self.chain}-{ts}-r{next_rev}",
                "active_since_ms": ts,
                "goal_revision": next_rev,
                "achieved_at_ms": 0,
                "updated_by": actor,
                "reason": reason,
            }
            self._state["meta"] = meta
            self._save_json(self._history_path, self._history)
            self._cache_key = None
            self._cache_state = None
        state = self.state(runtime)
        state["changed"] = True
        return state

    def replay_payload(self, runtime: Any) -> Dict[str, Any]:
        st = self.state(runtime)
        state = dict(st.get("state") or {}) if isinstance(st.get("state"), dict) else {}
        return {
            **dict(st.get("goal") or {}),
            "current_return_pct": float(state.get("currentReturnPct") or 0.0),
            "progress_pct": float(state.get("progressPct") or 0.0),
            "goal_achieved": bool(state.get("goalAchieved")),
            "goal_status": str(state.get("goalStatus") or "active"),
            "suggested_next_target_pct": float(state.get("suggestedNextTargetPct") or 0.0),
            "next_goal_allowed": bool(state.get("nextGoalAllowed", True)),
            "next_goal_blocked_reasons": list(state.get("nextGoalBlockedReasons") or []),
            "aggressiveness_cap": float(state.get("aggressivenessCap") or 1.0),
            "pacing": str(state.get("pacing") or "steady"),
            "capital_base_usd": float(state.get("capitalBaseUsd") or 0.0),
            "execution_realism_score": float(state.get("executionRealismScore") or 0.0),
            "stability_score": float(state.get("stabilityScore") or 0.0),
            "goal_urgency": str(state.get("goalUrgency") or "steady"),
            "next_goal_aggressiveness_hint": float(state.get("nextGoalAggressivenessHint") or 1.0),
            "goal_velocity_pct_per_day": float(state.get("goalVelocityPctPerDay") or 0.0),
            "goal_horizon_compatibility": float(state.get("goalHorizonCompatibility") or 1.0),
        }
