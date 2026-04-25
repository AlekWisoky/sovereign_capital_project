from __future__ import annotations

import asyncio
import os
import time
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional, Tuple

from .audit import AuditLogger
from .config import FIOAConfig

_SAFE_TASK_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, RuntimeError, TypeError)
_SAFE_RUNTIME_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    AttributeError,
    KeyError,
    IndexError,
    RuntimeError,
    TypeError,
    ValueError,
)
_SAFE_CFG_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, RuntimeError, TypeError, ValueError)


class FIOARuntime:
    """FIU-inspired Operational Independence & Autonomy overlay (FIOA).

    Design goals:
      - **Non-breaking**: if disabled, does nothing.
      - **Wrapper-first**: gates execution and risky mutations through an
        execution wrapper without altering core semantics.
      - **Audit-first**: all denies / escalations are written to an append-only
        audit trail.
    """

    PUBLIC_ANALYTICS = "PUBLIC_ANALYTICS"
    INTERNAL_STRATEGY = "INTERNAL_STRATEGY"
    CONFIDENTIAL_SIGNAL = "CONFIDENTIAL_SIGNAL"

    TRADE_EXECUTION = "TRADE_EXECUTION"
    BUNDLE_OPTIMIZATION = "BUNDLE_OPTIMIZATION"
    CAPITAL_ALLOCATION = "CAPITAL_ALLOCATION"
    RISK_LIMIT_ENFORCEMENT = "RISK_LIMIT_ENFORCEMENT"
    POLICY_MONITORING = "POLICY_MONITORING"

    def __init__(self, *, cfg: Optional[FIOAConfig], chain: str, data_dir: str, superstructure: Any = None):
        self.cfg = cfg or FIOAConfig(enabled=False)
        self.chain = str(chain)
        self._super = superstructure
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

        audit_path = os.path.join(str(data_dir), f"fioa_audit_{self.chain}.jsonl")
        self.audit = AuditLogger(
            audit_path,
            max_bytes=int(getattr(self.cfg, "audit_max_bytes", 25_000_000)),
            enabled=bool(getattr(self.cfg, "audit_enabled", True)),
        )

        self.safe_mode: bool = False
        self.safe_mode_until_ts: int = 0
        self.safe_mode_reason: str = ""
        self.require_human_review: bool = False

        self.restricted: Dict[str, Dict[str, Any]] = {}

        self.system_cycle: int = 0
        self.last_strategy_review_cycle: int = 0
        self.last_strategy_review_ts: float = 0.0
        self.last_sizing_step_ts: float = 0.0

        self.op_total: int = 0
        self.op_auto: int = 0
        self.op_manual: int = 0
        self.op_conflicts: int = 0
        self.op_human_overrides: int = 0

        self.autonomy_health: float = 0.0
        self.last_stress: float = 0.0

        self._get_runtime: Callable[[], Any] | None = None

        self._loop_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_cycle": 0,
            "last_cycle_ts": 0,
        }
        self._registry_sync_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_agent": "",
            "last_action": "",
            "last_sync_ts": 0,
        }
        self._settings_update_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_reason": "",
            "last_update_ts": 0,
        }
        self._sizing_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_old_base": 0,
            "last_new_base": 0,
            "last_update_ts": 0,
        }
        self._stress_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_compute_ts": 0,
            "components": {},
        }
        self._execution_audit_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_audit_ts": 0,
        }
        self._cfg_snapshot_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_snapshot_ts": 0,
        }

    def _mark_state(
        self,
        bucket: Dict[str, Any],
        *,
        ok: bool,
        code: str = "",
        error: str = "",
        ts_key: str = "",
    ) -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")
        if ok and ts_key:
            bucket[ts_key] = int(time.time())

    def _mark_loop_ok(self) -> None:
        self._loop_state["last_cycle"] = int(self.system_cycle)
        self._mark_state(self._loop_state, ok=True, ts_key="last_cycle_ts")

    def _mark_loop_error(self, code: str, exc: BaseException) -> None:
        self._loop_state["last_cycle"] = int(self.system_cycle)
        self._mark_state(self._loop_state, ok=False, code=code, error=str(exc))

    def _mark_registry_sync_ok(self, agent_id: str, action: str) -> None:
        self._registry_sync_state["last_agent"] = str(agent_id or "")
        self._registry_sync_state["last_action"] = str(action or "")
        self._mark_state(self._registry_sync_state, ok=True, ts_key="last_sync_ts")

    def _mark_registry_sync_error(self, code: str, exc: BaseException, *, agent_id: str, action: str) -> None:
        self._registry_sync_state["last_agent"] = str(agent_id or "")
        self._registry_sync_state["last_action"] = str(action or "")
        self._mark_state(self._registry_sync_state, ok=False, code=code, error=str(exc))

    def _mark_settings_update_ok(self, reason: str) -> None:
        self._settings_update_state["last_reason"] = str(reason or "")
        self._mark_state(self._settings_update_state, ok=True, ts_key="last_update_ts")

    def _mark_settings_update_error(self, code: str, exc: BaseException, *, reason: str) -> None:
        self._settings_update_state["last_reason"] = str(reason or "")
        self._mark_state(self._settings_update_state, ok=False, code=code, error=str(exc))

    def _mark_sizing_ok(self, *, old_base: int, new_base: int) -> None:
        self._sizing_state["last_old_base"] = int(old_base)
        self._sizing_state["last_new_base"] = int(new_base)
        self._mark_state(self._sizing_state, ok=True, ts_key="last_update_ts")

    def _mark_sizing_error(self, code: str, exc: BaseException, *, old_base: int = 0, new_base: int = 0) -> None:
        self._sizing_state["last_old_base"] = int(old_base)
        self._sizing_state["last_new_base"] = int(new_base)
        self._mark_state(self._sizing_state, ok=False, code=code, error=str(exc))

    def _mark_stress_ok(self, *, components: Dict[str, float]) -> None:
        self._stress_state["components"] = dict(components)
        self._mark_state(self._stress_state, ok=True, ts_key="last_compute_ts")

    def _mark_stress_error(self, code: str, exc: BaseException, *, components: Dict[str, float]) -> None:
        self._stress_state["components"] = dict(components)
        self._mark_state(self._stress_state, ok=False, code=code, error=str(exc))

    def _mark_execution_audit_ok(self) -> None:
        self._mark_state(self._execution_audit_state, ok=True, ts_key="last_audit_ts")

    def _mark_execution_audit_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._execution_audit_state, ok=False, code=code, error=str(exc))

    def _mark_cfg_snapshot_ok(self) -> None:
        self._mark_state(self._cfg_snapshot_state, ok=True, ts_key="last_snapshot_ts")

    def _mark_cfg_snapshot_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._cfg_snapshot_state, ok=False, code=code, error=str(exc))

    def _runtime_state(self) -> Dict[str, Any]:
        buckets = (
            self._loop_state,
            self._registry_sync_state,
            self._settings_update_state,
            self._sizing_state,
            self._stress_state,
            self._execution_audit_state,
            self._cfg_snapshot_state,
        )
        return {
            "loop": dict(self._loop_state),
            "registry_sync": dict(self._registry_sync_state),
            "settings_update": dict(self._settings_update_state),
            "sizing": dict(self._sizing_state),
            "stress_inputs": dict(self._stress_state),
            "execution_audit": dict(self._execution_audit_state),
            "cfg_snapshot": dict(self._cfg_snapshot_state),
            "degraded": not all(bool(bucket.get("ok", True)) for bucket in buckets),
        }

    def _int_or_default(self, value: Any, *, default: int = 0) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return int(default)

    def _float_or_default(self, value: Any, *, default: float = 0.0) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return float(default)

    def _bankroll_success_rate(self, rt: Any) -> float:
        try:
            sr_pct = float(getattr(rt, "_bankroll").success_rate_pct())
            return sr_pct / 100.0
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_sizing_error("sizing_success_rate_unavailable", exc)
            return 0.0

    def _base_borrow_amount(self, rt: Any) -> int:
        try:
            return int(getattr(rt.cfg.execution, "base_borrow_amount", "0") or "0")
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_sizing_error("sizing_base_borrow_unavailable", exc)
            return 0

    def _max_borrow_amount(self, rt: Any) -> int:
        try:
            return int(getattr(rt.cfg.safety, "max_borrow_amount", "0") or "0")
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_sizing_error("sizing_max_borrow_unavailable", exc)
            return 0

    # -------------------------
    # Lifecycle
    # -------------------------
    def start(self, runtime: Any) -> None:
        if not bool(getattr(self.cfg, "enabled", False)):
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._get_runtime = lambda: runtime
        self._task = asyncio.create_task(self._loop())
        self.audit.append("FIOA_START", chain=self.chain, cfg=self._safe_cfg_snapshot())

    async def stop(self) -> None:
        if not bool(getattr(self.cfg, "enabled", False)):
            return
        self._stop.set()
        if self._task:
            try:
                self._task.cancel()
            except _SAFE_TASK_EXCEPTIONS as exc:
                self._mark_loop_error("loop_cancel_failed", exc)
        self._task = None
        self.audit.append("FIOA_STOP", chain=self.chain)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.system_cycle += 1
                rt = self._get_runtime() if self._get_runtime else None
                if rt is not None:
                    self._escalation_protocol(rt)
                    self._strategy_director_review(rt)
                self._compute_autonomy_score()
                self._mark_loop_ok()
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_loop_error("fioa_loop_failed", exc)
            await asyncio.sleep(1)

    # -------------------------
    # Core validations (Sections 1,2,4)
    # -------------------------
    def validate_operational_scope(self, agent_id: str, action_type: str) -> bool:
        if not self.cfg.enabled:
            return True
        aid = str(agent_id or "")
        at = str(action_type or "")

        if aid in self.restricted:
            self.op_conflicts += 1
            self.audit.append("ScopeViolation:RestrictedAgent", agent_id=aid, action_type=at)
            return False

        scope = (self.cfg.agent_scope or {}).get(aid)
        if scope == "*":
            return True

        if scope != at:
            self.op_conflicts += 1
            self.audit.append("ScopeViolation", agent_id=aid, expected=str(scope), got=at)
            self.restrict_agent(aid, reason=f"scope_violation:{at}")
            return False
        return True

    def enforce_resource_limits(self, agent_id: str, requested_capital: float, requested_risk: float) -> bool:
        if not self.cfg.enabled:
            return True
        aid = str(agent_id or "")
        cap = float(requested_capital or 0.0)
        risk = float(requested_risk or 0.0)

        if cap > float(self.cfg.max_capital_per_agent):
            self.op_conflicts += 1
            self.audit.append("CapitalLimitExceeded", agent_id=aid, requested=cap, cap=float(self.cfg.max_capital_per_agent))
            return False
        if risk > float(self.cfg.max_risk_exposure):
            self.op_conflicts += 1
            self.audit.append("RiskLimitExceeded", agent_id=aid, requested=risk, cap=float(self.cfg.max_risk_exposure))
            return False
        return True

    def validate_data_access(self, agent_id: str, data_level: str) -> bool:
        if not self.cfg.enabled:
            return True
        if not bool(getattr(self.cfg, "confidentiality_enabled", True)):
            return True
        if not bool(getattr(self.cfg, "confidentiality_strict", False)):
            return True
        aid = str(agent_id or "")
        lvl = str(data_level or "")
        if lvl == self.CONFIDENTIAL_SIGNAL and aid != "GOVERNANCE_AGENT":
            self.op_conflicts += 1
            self.audit.append("ConfidentialAccessBlocked", agent_id=aid)
            return False
        return True

    def restrict_agent(self, agent_id: str, *, reason: str = "") -> None:
        if not self.cfg.enabled:
            return
        aid = str(agent_id or "")
        if not aid:
            return
        self.restricted[aid] = {"ts": int(time.time()), "reason": str(reason or "")}
        self.audit.append("AgentRestricted", agent_id=aid, reason=str(reason or ""))
        if self._super is not None and hasattr(self._super, "registry"):
            try:
                self._super.registry.set_suspended(aid, True, reason=str(reason or "fioa_restrict"))
                self._mark_registry_sync_ok(aid, "restrict")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_registry_sync_error("registry_suspend_failed", exc, agent_id=aid, action="restrict")

    def resume_agent(self, agent_id: str) -> bool:
        if not self.cfg.enabled:
            return False
        aid = str(agent_id or "")
        if not aid:
            return False
        existed = aid in self.restricted
        self.restricted.pop(aid, None)
        self.audit.append("AgentResumed", agent_id=aid)
        if self._super is not None and hasattr(self._super, "registry"):
            try:
                self._super.registry.set_suspended(aid, False, reason="fioa_resume")
                self._mark_registry_sync_ok(aid, "resume")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_registry_sync_error("registry_resume_failed", exc, agent_id=aid, action="resume")
        return existed

    # -------------------------
    # Strategy director + escalation (Sections 3,6)
    # -------------------------
    def _strategy_director_review(self, rt: Any) -> None:
        if not self.cfg.enabled:
            return
        if not bool(getattr(self.cfg, "strategy_director_enabled", True)):
            return

        risk_profile = float(self.last_stress or 0.0)
        if risk_profile > 0.75:
            self._limit_agent_autonomy(rt, reason="StrategyDirectorRiskIntervention")

        interval = int(getattr(self.cfg, "strategy_review_interval", 300) or 300)
        if interval <= 0:
            interval = 300
        if (self.system_cycle % interval) == 0 and self.system_cycle != self.last_strategy_review_cycle:
            self.last_strategy_review_cycle = int(self.system_cycle)
            self.last_strategy_review_ts = float(time.time())
            self.audit.append("StrategyDirectorPeriodicRebalance", cycle=int(self.system_cycle), risk_profile=risk_profile)
            self._rebalance_capital_allocation(rt)

    def _rebalance_capital_allocation(self, rt: Any) -> None:
        if not bool(getattr(self.cfg, "enable_dynamic_sizing", False)):
            return

        now = time.time()
        min_interval = float(getattr(self.cfg, "sizing_min_step_interval_s", 60.0) or 60.0)
        if self.last_sizing_step_ts and (now - self.last_sizing_step_ts) < min_interval:
            return

        sr = self._bankroll_success_rate(rt)
        target = float(getattr(self.cfg, "target_success_rate", 0.75) or 0.75)
        up = float(getattr(self.cfg, "sizing_up_step_pct", 5.0) or 5.0) / 100.0
        down = float(getattr(self.cfg, "sizing_down_step_pct", 10.0) or 10.0) / 100.0

        base = self._base_borrow_amount(rt)
        cap = self._max_borrow_amount(rt)
        if base <= 0:
            return

        new_base = base
        if sr >= min(0.98, target + 0.10):
            new_base = int(base * (1.0 + up))
        elif sr <= max(0.0, target - 0.15):
            new_base = int(base * (1.0 - down))

        if cap > 0:
            new_base = min(new_base, cap)
        new_base = max(1, int(new_base))

        if new_base != base:
            try:
                rt.set_settings(base_borrow_amount=str(new_base))
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_sizing_error("sizing_update_failed", exc, old_base=base, new_base=new_base)
                return
            self.last_sizing_step_ts = now
            self.audit.append(
                "StrategyDirectorSizing",
                old=str(base),
                new=str(new_base),
                success_rate=float(sr),
                target=float(target),
            )
            self._mark_sizing_ok(old_base=base, new_base=new_base)

    def _escalation_protocol(self, rt: Any) -> None:
        if not self.cfg.enabled:
            return
        stress = float(self._calculate_system_stress(rt))
        self.last_stress = stress

        th = float(getattr(self.cfg, "escalation_threshold", 0.85) or 0.85)
        if stress > th:
            ttl = float(getattr(self.cfg, "safe_mode_default_ttl_s", 120.0) or 120.0)
            self._set_safe_mode(True, ttl_s=ttl, reason="FIU_EscalationTriggered")
            self._limit_agent_autonomy(rt, reason="FIU_EscalationTriggered")

    def _set_safe_mode(self, on: bool, *, ttl_s: float = 0.0, reason: str = "") -> None:
        if not self.cfg.enabled:
            return
        if on:
            now = int(time.time())
            ttl = int(max(1, ttl_s)) if ttl_s else int(getattr(self.cfg, "safe_mode_default_ttl_s", 120.0) or 120.0)
            self.safe_mode = True
            self.safe_mode_until_ts = now + ttl
            self.safe_mode_reason = str(reason or "")
            self.require_human_review = True
            self.audit.append("SafeModeOn", ttl_s=int(ttl), until=int(self.safe_mode_until_ts), reason=str(reason or ""))
        else:
            self.safe_mode = False
            self.safe_mode_until_ts = 0
            self.safe_mode_reason = ""
            self.require_human_review = False
            self.audit.append("SafeModeOff")

    def _limit_agent_autonomy(self, rt: Any, *, reason: str = "") -> None:
        try:
            rt.set_settings(auto_trading=False)
            self._mark_settings_update_ok(reason or "limit_agent_autonomy")
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_settings_update_error("settings_auto_trading_failed", exc, reason=reason or "limit_agent_autonomy")

        if hasattr(rt, "superstructure_force_safe_mode"):
            try:
                rt.superstructure_force_safe_mode(
                    ttl_s=float(getattr(self.cfg, "safe_mode_default_ttl_s", 120.0) or 120.0),
                    reason=str(reason or "fioa_safe_mode"),
                )
                self._mark_settings_update_ok(reason or "superstructure_safe_mode")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_settings_update_error("settings_superstructure_safe_mode_failed", exc, reason=reason or "superstructure_safe_mode")
        self.audit.append("LimitAgentAutonomy", reason=str(reason or ""))

    def _calculate_system_stress(self, rt: Any) -> float:
        components: Dict[str, float] = {}
        first_error: tuple[str, BaseException] | None = None

        try:
            fail_streak = int(getattr(rt, "_bankroll").state.fail_streak)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            fail_streak = 0
            first_error = first_error or ("stress_fail_streak_unavailable", exc)
        fail = min(1.0, max(0.0, float(fail_streak) / 5.0))
        components["fail_streak"] = float(fail)

        mev = 0.0
        try:
            mr = getattr(rt, "_mev", None)
            if mr is not None:
                st = mr.state() if hasattr(mr, "state") else {}
                mev = float(st.get("sandwich_risk_p90") or 0.0)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            mev = 0.0
            first_error = first_error or ("stress_mev_unavailable", exc)
        mev = max(0.0, min(1.0, mev))
        components["mev"] = float(mev)

        gas = 0.0
        try:
            basefee = float(getattr(rt.metrics, "basefee_gwei", 0.0) or 0.0)
            gas = min(1.0, max(0.0, basefee / 200.0))
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            gas = 0.0
            first_error = first_error or ("stress_gas_unavailable", exc)
        components["gas"] = float(gas)

        rpc = 0.0
        try:
            snap = rt.rpc_manager.snapshot()
            rows = (snap.get("read") or []) + (snap.get("send") or [])
            if rows:
                ok_ratio = sum(1 for r in rows if r.get("ok")) / float(len(rows))
                rpc = 1.0 - ok_ratio
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            rpc = 0.0
            first_error = first_error or ("stress_rpc_unavailable", exc)
        rpc = max(0.0, min(1.0, rpc))
        components["rpc"] = float(rpc)

        pending = 0.0
        try:
            max_pending = int(getattr(rt.cfg.execution, "max_pending_txs", 1) or 1)
            cur_pending = len(getattr(rt, "_pending", {}) or {})
            if max_pending > 0:
                pending = min(1.0, max(0.0, cur_pending / float(max_pending)))
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            pending = 0.0
            first_error = first_error or ("stress_pending_unavailable", exc)
        components["pending"] = float(pending)

        w1 = float(getattr(self.cfg, "stress_w_fail_streak", 0.35) or 0.35)
        w2 = float(getattr(self.cfg, "stress_w_mev", 0.25) or 0.25)
        w3 = float(getattr(self.cfg, "stress_w_gas", 0.20) or 0.20)
        w4 = float(getattr(self.cfg, "stress_w_rpc", 0.10) or 0.10)
        w5 = float(getattr(self.cfg, "stress_w_pending", 0.10) or 0.10)
        denom = max(1e-9, w1 + w2 + w3 + w4 + w5)
        stress = (w1 * fail + w2 * mev + w3 * gas + w4 * rpc + w5 * pending) / denom
        stress = float(max(0.0, min(1.0, stress)))
        if first_error is None:
            self._mark_stress_ok(components=components)
        else:
            self._mark_stress_error(first_error[0], first_error[1], components=components)
        return stress

    # -------------------------
    # Autonomy health scoreboard (Section 5)
    # -------------------------
    def _compute_autonomy_score(self) -> None:
        total = max(1, int(self.op_total))
        full_auto_ratio = float(self.op_auto) / float(total)
        human_override_rate = float(self.op_human_overrides) / float(total)
        conflict_rate = float(self.op_conflicts) / float(total)

        ah = (full_auto_ratio * 0.5) - (human_override_rate * 0.3) - (conflict_rate * 0.2)
        self.autonomy_health = float(ah)
        self.audit.append(
            "AutonomyHealth",
            value=float(self.autonomy_health),
            full_auto_ratio=float(full_auto_ratio),
            human_override_rate=float(human_override_rate),
            conflict_rate=float(conflict_rate),
        )

        if self.safe_mode and self.safe_mode_until_ts and int(time.time()) >= int(self.safe_mode_until_ts):
            self._set_safe_mode(False)

    # -------------------------
    # Trade-context helpers
    # -------------------------
    def estimate_trade_context(self, rt: Any, opp: Any, decision: Any = None) -> Tuple[float, float]:
        amt = 0
        try:
            route = getattr(opp, "route", None)
            legs = getattr(route, "legs", None) or []
            first_leg = legs[0]
            amt = int(getattr(first_leg, "amount_in", "0") or "0")
        except _SAFE_RUNTIME_EXCEPTIONS:
            amt = 0

        try:
            if decision is not None:
                size_mult = float(getattr(decision, "size_mult", 1.0) or 1.0)
                borrow_mult = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
            else:
                bm = (opp.meta.get("brain") if isinstance(getattr(opp, "meta", None), dict) else {}) or {}
                size_mult = float(bm.get("size_mult") or 1.0)
                borrow_mult = float(bm.get("borrow_mult") or 1.0)
            mult = max(0.10, float(size_mult) * float(borrow_mult))
            if amt > 0 and mult != 1.0:
                amt = int(max(1, int(amt * mult)))
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass

        try:
            cap = int(getattr(rt.cfg.safety, "max_borrow_amount", "0") or "0")
            if cap > 0:
                amt = min(int(amt), int(cap))
        except _SAFE_RUNTIME_EXCEPTIONS:
            pass

        system_cap = 0
        try:
            ss = getattr(rt.cfg.execution, "superstructure", None)
            system_cap = int(getattr(ss, "capital_total_wei", "0") or "0") if ss is not None else 0
        except _SAFE_RUNTIME_EXCEPTIONS:
            system_cap = 0
        if system_cap <= 0:
            try:
                system_cap = int(getattr(rt.cfg.safety, "max_borrow_amount", "0") or "0")
            except _SAFE_RUNTIME_EXCEPTIONS:
                system_cap = 0
        if system_cap <= 0:
            try:
                system_cap = int(getattr(rt.cfg.execution, "base_borrow_amount", "0") or "0")
            except _SAFE_RUNTIME_EXCEPTIONS:
                system_cap = 0
        if system_cap <= 0:
            system_cap = max(1, amt)

        capital_frac = float(amt) / float(max(1, int(system_cap)))
        capital_frac = max(0.0, min(1.0, capital_frac))

        risk = float(self._calculate_system_stress(rt))
        return float(capital_frac), float(max(0.0, min(1.0, risk)))

    # -------------------------
    # Wrapper (Section 8)
    # -------------------------
    async def execution_wrapper(
        self,
        core_coro: Callable[[], Any],
        *,
        agent_id: str,
        action_type: str,
        capital: float,
        risk: float,
        data_level: str = INTERNAL_STRATEGY,
        core_command: str = "",
        mode: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if not bool(getattr(self.cfg, "enabled", False)):
            return await core_coro()

        self.op_total += 1
        if str(mode) == "auto":
            self.op_auto += 1
        elif str(mode) in {"manual", "simulate"}:
            self.op_manual += 1
            self.op_human_overrides += 1

        if not self.validate_operational_scope(agent_id, action_type):
            return self._deny_result(core_command or "core", reason="fioa_scope_violation")
        if not self.enforce_resource_limits(agent_id, capital, risk):
            return self._deny_result(core_command or "core", reason="fioa_resource_limits")
        if not self.validate_data_access(agent_id, data_level):
            return self._deny_result(core_command or "core", reason="fioa_data_access")

        rt = self._get_runtime() if self._get_runtime else None
        if rt is not None:
            self._escalation_protocol(rt)
            self._strategy_director_review(rt)

        if self.safe_mode and str(mode) == "auto":
            self.audit.append(
                "AutoBlockedSafeMode",
                agent_id=str(agent_id),
                action_type=str(action_type),
                reason=str(self.safe_mode_reason or ""),
            )
            return self._deny_result(core_command or "core", reason="fioa_safe_mode")

        res = await core_coro()

        try:
            payload = {
                "agent_id": str(agent_id),
                "action_type": str(action_type),
                "core_command": str(core_command or ""),
                "mode": str(mode or ""),
                "capital": float(capital),
                "risk": float(risk),
            }
            if meta:
                payload["meta"] = meta
            ok = getattr(res, "ok", None)
            reason = getattr(res, "reason", None)
            txh = getattr(res, "tx_hash", None)
            if ok is not None:
                payload["ok"] = bool(ok)
            if reason is not None:
                payload["reason"] = str(reason)
            if txh:
                payload["tx_hash"] = str(txh)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_execution_audit_error("execution_audit_payload_invalid", exc)
            return res
        self.audit.append("Executed", **payload)
        self._mark_execution_audit_ok()
        return res

    def _deny_result(self, core_command: str, *, reason: str) -> Any:
        class _R:
            def __init__(self, why: str):
                self.ok = False
                self.dry_run = True
                self.reason = str(why)
                self.tx_hash = ""
                self.plan = None
                self.attempted = False
                self.submitted = False

        self.op_conflicts += 1
        self.audit.append("ExecutionDenied", core_command=str(core_command or ""), reason=str(reason))
        return _R(reason)

    # -------------------------
    # API helpers
    # -------------------------
    def state(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": bool(self.cfg.enabled),
            "chain": self.chain,
            "system_mode": str(getattr(self.cfg, "system_mode", "")),
            "architecture_lock": bool(getattr(self.cfg, "architecture_lock", True)),
            "core_commands_immutable": bool(getattr(self.cfg, "core_commands_immutable", True)),
            "limits": {
                "max_capital_per_agent": float(getattr(self.cfg, "max_capital_per_agent", 0.25)),
                "max_risk_exposure": float(getattr(self.cfg, "max_risk_exposure", 0.18)),
                "max_leverage": float(getattr(self.cfg, "max_leverage", 3.0)),
            },
            "agent_scope": dict(getattr(self.cfg, "agent_scope", {}) or {}),
            "restricted": dict(self.restricted or {}),
            "safe_mode": {
                "on": bool(self.safe_mode),
                "until_ts": int(self.safe_mode_until_ts or 0),
                "reason": str(self.safe_mode_reason or ""),
                "require_human_review": bool(self.require_human_review),
            },
            "health": {
                "autonomy_health": float(self.autonomy_health),
                "system_stress": float(self.last_stress),
                "op_total": int(self.op_total),
                "op_auto": int(self.op_auto),
                "op_manual": int(self.op_manual),
                "op_conflicts": int(self.op_conflicts),
                "op_human_overrides": int(self.op_human_overrides),
            },
            "runtime": self._runtime_state(),
            "audit": self.audit.state(),
        }

    def governance_report(self, limit_audit: int = 200) -> Dict[str, Any]:
        items = self.audit.tail(limit=limit_audit)
        counts: Dict[str, int] = {}
        by_agent: Dict[str, Dict[str, Any]] = {}
        for it in items:
            ev = str(it.get("event") or "")
            counts[ev] = int(counts.get(ev, 0)) + 1
            aid = str(it.get("agent_id") or "")
            if aid:
                agent_perf = by_agent.get(aid) or {"actions": 0, "ok": 0, "denied": 0}
                agent_perf["actions"] = int(agent_perf.get("actions", 0)) + 1
                if ev == "Executed" and it.get("ok") is True:
                    agent_perf["ok"] = int(agent_perf.get("ok", 0)) + 1
                if ev in {
                    "ExecutionDenied",
                    "ScopeViolation",
                    "CapitalLimitExceeded",
                    "RiskLimitExceeded",
                    "ConfidentialAccessBlocked",
                    "AutoBlockedSafeMode",
                }:
                    agent_perf["denied"] = int(agent_perf.get("denied", 0)) + 1
                by_agent[aid] = agent_perf
        return {
            "ok": True,
            "chain": self.chain,
            "generated_ts": int(time.time()),
            "safe_mode": {
                "on": bool(self.safe_mode),
                "until_ts": int(self.safe_mode_until_ts or 0),
                "reason": str(self.safe_mode_reason or ""),
            },
            "autonomy_health": float(self.autonomy_health),
            "system_stress": float(self.last_stress),
            "recent_events": counts,
            "agent_performance": by_agent,
            "restricted": dict(self.restricted or {}),
            "runtime": self._runtime_state(),
            "audit": self.audit.state(),
        }

    def _safe_cfg_snapshot(self) -> Dict[str, Any]:
        try:
            raw = asdict(self.cfg)
            self._mark_cfg_snapshot_ok()
        except _SAFE_CFG_EXCEPTIONS as exc:
            raw = {}
            self._mark_cfg_snapshot_error("cfg_snapshot_failed", exc)
        return {
            "enabled": bool(raw.get("enabled")),
            "system_mode": raw.get("system_mode"),
            "architecture_lock": raw.get("architecture_lock"),
            "core_commands_immutable": raw.get("core_commands_immutable"),
            "max_capital_per_agent": raw.get("max_capital_per_agent"),
            "max_risk_exposure": raw.get("max_risk_exposure"),
            "max_leverage": raw.get("max_leverage"),
            "strategy_director_enabled": raw.get("strategy_director_enabled"),
            "strategy_review_interval": raw.get("strategy_review_interval"),
            "confidentiality_enabled": raw.get("confidentiality_enabled"),
            "confidentiality_strict": raw.get("confidentiality_strict"),
            "escalation_threshold": raw.get("escalation_threshold"),
            "audit_enabled": raw.get("audit_enabled"),
            "enable_dynamic_sizing": raw.get("enable_dynamic_sizing"),
        }
