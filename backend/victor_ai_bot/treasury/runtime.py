from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

from victor_ai_bot.determinism import stable_hash_int

from .config import ProfitGoal, TreasuryConfig
from .inventory_balancer import InventoryBalancer
from .allocation_engine import allocate_capital
from .reinvestment import reinvestment_policy
from .metrics import capital_efficiency_metrics
from ..persistence.db import PersistenceDB
from ..persistence.repositories.treasury_repository import TreasuryMetricsRepository
from ..persistence.repositories.treasury_state_repository import TreasuryStateRepository
from ..persistence.repositories.capital_event_repository import CapitalEventRepository
from ..strategies.family_scorecards import FamilyScorecardStore
from ..strategies.covariance import FamilyCovarianceStore
from ..pathing import canonical_data_dir


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _level_rank(level: str) -> int:
    order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "MAXIMUM": 3}
    return int(order.get(str(level or "LOW").upper(), 0))


class TreasuryRuntime:
    """Adaptive Treasury & Capital Optimization Layer.

    Non-destructive overlay:
    - provides aggressiveness level
    - provides capital allocation weight suggestions
    - records audit logs
    - never directly executes trades
    """

    def __init__(
        self,
        *,
        cfg: Optional[TreasuryConfig] = None,
        data_dir: str = "backend/data",
        db: PersistenceDB | None = None,
        chain: str = "default",
        capital_event_repo: CapitalEventRepository | None = None,
    ):
        self.cfg = cfg or TreasuryConfig()
        cfg_data_dir = str(getattr(self.cfg, "data_dir", "") or "").strip()
        explicit_data_dir = str(data_dir or "").strip()
        self.data_dir = canonical_data_dir(explicit_data_dir or cfg_data_dir)
        self._chain = str(chain or "default")
        self._started_ts = int(time.time())
        self._goal: ProfitGoal = self.cfg.profit_goal
        self._state_path = os.path.join(
            self.data_dir, "state", f"treasury_runtime_last_{self._chain}.json"
        )
        self._last: Dict[str, Any] = self._load_last_state()
        self._audit_path = os.path.join(self.data_dir, "governance", "treasury_decisions.jsonl")
        os.makedirs(os.path.dirname(self._audit_path), exist_ok=True)
        # Config stores liquidity buffer as a percentage (e.g. 25.0 == 25%).
        # InventoryBalancer expects a 0..1 fraction. Support legacy attr names.
        buf_pct = float(
            getattr(
                self.cfg,
                "liquidity_buffer_pct",
                getattr(
                    self.cfg,
                    "min_liquidity_buffer_pct",
                    getattr(self.cfg, "liquidity_min_buffer_pct", 25.0),
                ),
            )
            or 0.0
        )
        buf = buf_pct / 100.0 if buf_pct > 1.0 else buf_pct
        buf = max(0.0, min(1.0, float(buf)))
        self._liquidity_buffer_fraction = float(buf)
        self._inv_balancer = InventoryBalancer(min_stable_reserve=float(buf))
        self._db = db or PersistenceDB(
            os.path.join(self.data_dir, "state", "xdv_runtime_state.sqlite3")
        )
        self._metrics_repo = TreasuryMetricsRepository(self._db, chain=self._chain)
        self._state_repo = TreasuryStateRepository(self._db, chain=self._chain)
        if not self._last:
            self._last = self._load_last_state_from_repo()
        self._capital_event_repo = capital_event_repo
        self._scorecards = FamilyScorecardStore(
            path=os.path.join(self.data_dir, "strategies", f"family_scorecards_{self._chain}.json"),
            chain=self._chain,
        )
        self._covariance = FamilyCovarianceStore(
            path=os.path.join(self.data_dir, "strategies", f"family_covariance_{self._chain}.json")
        )
        self._ensure_state_history_bootstrap()

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _load_last_state(self) -> Dict[str, Any]:
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return dict(payload or {}) if isinstance(payload, dict) else {}
        except (OSError, TypeError, ValueError):
            return {}

    def _load_last_state_from_repo(self) -> Dict[str, Any]:
        try:
            latest = self._state_repo.latest(state_type="capital_snapshot")
        except (OSError, TypeError, ValueError, AttributeError):
            latest = {}
        payload = dict(latest.get("payload") or {}) if isinstance(latest, dict) else {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _save_last_state(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            tmp_path = f"{self._state_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._last, f, sort_keys=True)
            os.replace(tmp_path, self._state_path)
        except (OSError, TypeError, ValueError):
            return

    def _record_state_snapshot(
        self, payload: Dict[str, Any], *, state_type: str = "capital_snapshot"
    ) -> None:
        snapshot_payload = dict(payload or {})
        ts_ms = int(snapshot_payload.get("updated_ts_ms") or self._now_ms())
        try:
            self._state_repo.append_snapshot(
                ts_ms=ts_ms,
                state_type=str(state_type or "capital_snapshot"),
                payload=snapshot_payload,
            )
        except (OSError, TypeError, ValueError):
            pass
        if self._capital_event_repo is None:
            return
        try:
            self._capital_event_repo.append_event(
                ts_ms=ts_ms,
                domain="treasury",
                event_type=str(state_type or "capital_snapshot"),
                source="treasury_runtime",
                entity_id="treasury_runtime",
                payload=snapshot_payload,
            )
        except (OSError, TypeError, ValueError):
            return

    def _ensure_state_history_bootstrap(self) -> None:
        if not self._last:
            return
        try:
            latest = self._state_repo.latest(state_type="capital_snapshot")
        except (OSError, TypeError, ValueError):
            latest = {}
        latest_payload = dict(latest.get("payload") or {}) if isinstance(latest, dict) else {}
        if latest_payload and dict(latest_payload) == dict(self._last):
            return
        self._record_state_snapshot(self._last)

    def _stamp_snapshot(
        self, out: Dict[str, Any], *, bankroll_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        now_ms = self._now_ms()
        bankroll_ts_ms = max(
            0,
            int(
                bankroll_state.get("updated_ts_ms")
                or bankroll_state.get("profit_updated_ts_ms")
                or bankroll_state.get("sizing_updated_ts_ms")
                or 0
            ),
        )
        out["updated_ts_ms"] = int(now_ms)
        out["observed_ts_ms"] = int(now_ms)
        out["bankroll_state_ts_ms"] = int(bankroll_ts_ms)
        capital_engine = dict(out.get("capital_engine") or {})
        capital_engine["updated_ts_ms"] = int(now_ms)
        capital_engine["bankroll_state_ts_ms"] = int(bankroll_ts_ms)
        out["capital_engine"] = capital_engine
        reinvestment_policy = dict(out.get("reinvestment_policy") or {})
        reinvestment_policy["updated_ts_ms"] = int(now_ms)
        out["reinvestment_policy"] = reinvestment_policy
        capital_efficiency_metrics = dict(out.get("capital_efficiency_metrics") or {})
        capital_efficiency_metrics["updated_ts_ms"] = int(now_ms)
        out["capital_efficiency_metrics"] = capital_efficiency_metrics
        return out

    def set_goal(self, *, goal: ProfitGoal) -> None:
        self._goal = goal
        self._audit({"event": "set_goal", "goal": asdict(goal)})

    def _audit(self, row: Dict[str, Any]) -> None:
        try:
            payload = dict(row)
            payload.setdefault("ts", int(time.time()))
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except (OSError, TypeError, ValueError):
            return

    def compute_aggressiveness(
        self,
        *,
        realized_profit_wei: int,
        estimated_capital_wei: int,
        drawdown_pct: float,
        volatility_regime: str,
    ) -> Dict[str, Any]:
        """Compute aggressiveness level from profit goal + progress."""

        g = self._goal
        cap = max(1, int(estimated_capital_wei))
        realized = max(0, int(realized_profit_wei))
        current_return_pct = 100.0 * float(realized) / float(cap)

        elapsed = int(time.time()) - int(self._started_ts)
        remaining = max(1, int(g.time_horizon_seconds) - int(elapsed))
        performance_gap = float(g.target_return_percentage) - float(current_return_pct)
        urgency_factor = float(performance_gap) / float(
            max(1.0, float(remaining) / 3600.0)
        )  # gap per hour
        urgency_factor = float(_clip(urgency_factor, -10.0, 10.0))

        # base aggressiveness from risk tolerance / operator override
        rt = str(g.risk_tolerance or "conservative").lower()
        try:
            override = str((self.cfg.meta or {}).get("aggression_mode_override") or "").lower()
            if override in {"conservative", "balanced", "aggressive"}:
                rt = {
                    "conservative": "conservative",
                    "balanced": "moderate",
                    "aggressive": "aggressive",
                }[override]
        except (AttributeError, TypeError, ValueError):
            override = ""
        level = "LOW" if rt == "conservative" else ("MODERATE" if rt == "moderate" else "HIGH")

        if float(urgency_factor) > 0.10 and float(drawdown_pct) < float(g.max_drawdown_pct):
            level = "HIGH" if level in {"LOW", "MODERATE"} else level
        if float(urgency_factor) > 0.25 and float(drawdown_pct) < float(g.max_drawdown_pct) * 0.7:
            level = "MAXIMUM"
        if float(drawdown_pct) >= float(g.max_drawdown_pct) * 0.80:
            level = "LOW"
        if level == "MAXIMUM" and not bool(getattr(self.cfg, "allow_maximum", False)):
            level = "HIGH"

        # volatility cap
        if (
            str(volatility_regime or "").lower() in {"high_vol", "risk_off", "panic"}
            and rt == "conservative"
        ):
            level = "LOW"

        # derived multipliers used by strategy scoring
        mult = 1.0
        if level == "MODERATE":
            mult = 1.10
        elif level == "HIGH":
            mult = 1.25
        elif level == "MAXIMUM":
            mult = 1.40

        out = {
            "aggressiveness_level": level,
            "aggressiveness_multiplier": float(mult),
            "current_return_pct": float(current_return_pct),
            "performance_gap": float(performance_gap),
            "time_remaining_s": int(remaining),
            "urgency_factor": float(urgency_factor),
            "risk_tolerance": rt,
            "drawdown_pct": float(drawdown_pct),
        }
        return out

    def _borrow_cap_target(self, *, aggressiveness_level: str, urgency_factor: float) -> float:
        base_cap = float(self.cfg.borrow_mult_cap)
        level = str(aggressiveness_level or "LOW").upper()
        boost = 1.0
        if level == "MODERATE":
            boost = 1.15
        elif level == "HIGH":
            boost = 1.35
        elif level == "MAXIMUM":
            boost = 1.60
        boost *= float(_clip(1.0 + max(0.0, float(urgency_factor)) * 0.15, 1.0, 1.35))
        return float(
            _clip(
                base_cap * boost, float(self.cfg.borrow_mult_min), float(self.cfg.borrow_mult_cap)
            )
        )

    def governance_contract(
        self,
        *,
        aggressiveness_level: str,
        borrow_mult_target_cap: float,
        urgency_factor: float = 0.0,
        approved_by_human: bool = False,
    ) -> Dict[str, Any]:
        lvl = str(aggressiveness_level or "LOW").upper()
        if lvl not in {"LOW", "MODERATE", "HIGH", "MAXIMUM"}:
            lvl = "LOW"
        approved = bool(approved_by_human)
        max_without = str(
            getattr(self.cfg, "max_aggressiveness_without_approval", "HIGH") or "HIGH"
        ).upper()
        if max_without not in {"LOW", "MODERATE", "HIGH", "MAXIMUM"}:
            max_without = "HIGH"
        allow_maximum = bool(getattr(self.cfg, "allow_maximum", False))
        gov = self.governance_check(aggressiveness_level=lvl, approved_by_human=approved)
        reason = str(gov.get("reason") or "ok")
        ok = bool(gov.get("ok", False))
        effective_level = lvl
        if not approved:
            if effective_level == "MAXIMUM" and not allow_maximum:
                effective_level = "HIGH"
            if _level_rank(effective_level) > _level_rank(max_without):
                effective_level = max_without
        effective_cap = float(borrow_mult_target_cap)
        if not ok:
            effective_cap = 1.0
        return {
            "ok": ok,
            "blocked": not ok,
            "reason": reason,
            "reason_codes": ([] if reason == "ok" else [reason]),
            "approved_by_human": approved,
            "allow_maximum": allow_maximum,
            "max_aggressiveness_without_approval": max_without,
            "raw_aggressiveness_level": lvl,
            "effective_aggressiveness_level": effective_level,
            "raw_borrow_mult_target_cap": float(borrow_mult_target_cap),
            "effective_borrow_mult_target_cap": float(effective_cap),
            "urgency_factor": float(urgency_factor),
            "suggested_next_action": (
                "continue_treasury_plan"
                if ok
                else (
                    "lower_treasury_aggressiveness_or_enable_maximum"
                    if reason == "maximum_disabled"
                    else "obtain_treasury_approval_or_reduce_aggressiveness"
                )
            ),
        }

    def pre_select_strategy(
        self,
        *,
        bankroll_state: Dict[str, Any],
        volatility_regime: str = "unknown",
        persist: bool = True,
    ) -> Dict[str, Any]:
        if not bool(self.cfg.enabled):
            disabled = self._stamp_snapshot(
                {"ts": int(time.time()), "enabled": False}, bankroll_state=bankroll_state
            )
            if persist:
                self._last = dict(disabled)
                self._save_last_state()
                self._record_state_snapshot(self._last)
            return dict(disabled)

        realized = int(bankroll_state.get("realized_profit_wei") or 0)
        # estimated capital: config override or base borrow * 10 as coarse proxy
        try:
            cap = int(self.cfg.meta.get("estimated_capital_wei") or 0)
        except (AttributeError, TypeError, ValueError):
            cap = 0
        if cap <= 0:
            cap = max(1, int(bankroll_state.get("last_amount_in_wei") or 0) * 10)
        drawdown = float(self.cfg.meta.get("drawdown_pct") or 0.0)
        ag = self.compute_aggressiveness(
            realized_profit_wei=realized,
            estimated_capital_wei=cap,
            drawdown_pct=drawdown,
            volatility_regime=volatility_regime,
        )

        level = str(ag.get("aggressiveness_level") or "LOW")
        u = float(ag.get("urgency_factor") or 0.0)
        borrow_cap = self._borrow_cap_target(
            aggressiveness_level=str(level),
            urgency_factor=float(u),
        )
        prior_governance = (
            dict(self._last.get("governance") or {}) if isinstance(self._last, dict) else {}
        )
        approved = bool(
            prior_governance.get("approved_by_human")
            or (self._last.get("approved_by_human") if isinstance(self._last, dict) else False)
            or (self._last.get("governance_approved") if isinstance(self._last, dict) else False)
        )
        governance = self.governance_contract(
            aggressiveness_level=str(level),
            borrow_mult_target_cap=float(borrow_cap),
            urgency_factor=float(u),
            approved_by_human=approved,
        )
        effective_level = str(governance.get("effective_aggressiveness_level") or level)
        effective_borrow_cap = float(governance.get("effective_borrow_mult_target_cap") or 1.0)
        ag = dict(ag or {})
        ag["raw_aggressiveness_level"] = str(level)
        ag["aggressiveness_level"] = str(effective_level)
        ag["effective_aggressiveness_level"] = str(effective_level)
        ag["governance_blocked"] = bool(governance.get("blocked", False))
        ag["governance_reason"] = str(governance.get("reason") or "ok")
        ag["borrow_mult_target_cap"] = float(effective_borrow_cap)
        ag["raw_borrow_mult_target_cap"] = float(borrow_cap)
        ag["effective_borrow_mult_target_cap"] = float(effective_borrow_cap)

        out = {
            "ts": int(time.time()),
            "enabled": True,
            "goal": asdict(self._goal),
            "aggressiveness": ag,
            "borrow_mult_target_cap": float(borrow_cap),
            "effective_borrow_mult_target_cap": float(effective_borrow_cap),
            "effective_aggressiveness_level": str(effective_level),
            "approved_by_human": bool(governance.get("approved_by_human", False)),
            "governance_approved": bool(governance.get("approved_by_human", False)),
            "governance": governance,
        }
        # Inventory balancer (advisory): clarify current inventory/capital distribution targets
        try:
            inv = self._inv_balancer.compute_targets(
                volatility_regime=str(volatility_regime),
                aggressiveness_level=str(effective_level),
                liquidity_buffer=float(getattr(self, "_liquidity_buffer_fraction", 0.25)),
            )
            out["inventory_balancer"] = inv
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            out["capital_engine"] = allocate_capital(
                estimated_capital_wei=int(cap),
                drawdown_pct=float(drawdown),
                regime=str(volatility_regime),
                aggressiveness_level=str(effective_level),
                scorecards=self._scorecards.snapshot(),
                capital_metrics=out.get("capital_efficiency_metrics", {}),
                covariance_penalties=self._covariance.penalties(),
            )
        except (TypeError, ValueError, KeyError):
            out["capital_engine"] = {}
        try:
            out["reinvestment_policy"] = reinvestment_policy(
                realized_profit_wei=int(realized),
                aggressiveness_level=str(effective_level),
                auto_reinvest_enabled=bool(
                    (self.cfg.meta or {}).get("auto_reinvest_enabled", False)
                ),
            )
        except (TypeError, ValueError, KeyError):
            out["reinvestment_policy"] = {}
        try:
            raw_cap_engine = out.get("capital_engine")
            cap_engine = dict(raw_cap_engine) if isinstance(raw_cap_engine, dict) else {}
            out["capital_efficiency_metrics"] = capital_efficiency_metrics(
                realized_pnl_wei=int(realized),
                deployed_capital_wei=int(cap_engine.get("deployable_bankroll_wei") or 1),
                at_risk_capital_wei=int(cap_engine.get("drawdown_buffer_wei") or 1),
                gas_cost_wei=int((self.cfg.meta or {}).get("rolling_gas_cost_wei", 1) or 1),
                utilization_rate=float((self.cfg.meta or {}).get("utilization_rate", 0.5) or 0.5),
                failures=int((self.cfg.meta or {}).get("rolling_failures", 0) or 0),
                bankroll_wei=int(cap),
                turnover_count=int((self.cfg.meta or {}).get("turnover_count", 0) or 0),
            )
            try:
                raw_capital_efficiency_metrics = out.get("capital_efficiency_metrics")
                capital_efficiency_payload = (
                    dict(raw_capital_efficiency_metrics)
                    if isinstance(raw_capital_efficiency_metrics, dict)
                    else {}
                )
                self._metrics_repo.insert_snapshot(
                    ts_ms=int(time.time() * 1000),
                    metrics=capital_efficiency_payload,
                )
            except (OSError, TypeError, ValueError):
                pass
            out["capital_engine"] = allocate_capital(
                estimated_capital_wei=int(cap),
                drawdown_pct=float(drawdown),
                regime=str(volatility_regime),
                aggressiveness_level=str(effective_level),
                scorecards=self._scorecards.snapshot(),
                capital_metrics=out.get("capital_efficiency_metrics", {}),
                covariance_penalties=self._covariance.penalties(),
            )
        except (TypeError, ValueError, KeyError):
            out["capital_efficiency_metrics"] = {}
        out = self._stamp_snapshot(out, bankroll_state=bankroll_state)
        if persist:
            self._last = dict(out)
            self._save_last_state()
            self._record_state_snapshot(self._last)
            self._audit({"event": "pre_select", "data": out})
        return dict(out)

    def adopt_snapshot(self, snapshot: Dict[str, Any], *, persist_mirror: bool = True) -> None:
        self._last = dict(snapshot or {})
        if persist_mirror:
            self._save_last_state()

    def governance_check(
        self, *, aggressiveness_level: str, approved_by_human: bool = False
    ) -> Dict[str, Any]:
        """Treasury governance rules.

        - disallow MAXIMUM when config does not permit it
        - require approval when aggressiveness exceeds configured auto-trade limit
        """

        lvl = str(aggressiveness_level or "LOW").upper()
        approved = bool(approved_by_human)
        max_without = str(
            getattr(self.cfg, "max_aggressiveness_without_approval", "HIGH") or "HIGH"
        ).upper()
        if max_without not in {"LOW", "MODERATE", "HIGH", "MAXIMUM"}:
            max_without = "HIGH"
        allow_maximum = bool(getattr(self.cfg, "allow_maximum", False))

        if lvl == "MAXIMUM" and not allow_maximum and not approved:
            return {"ok": False, "reason": "maximum_disabled"}
        if _level_rank(lvl) > _level_rank(max_without) and not approved:
            if lvl == "MAXIMUM":
                return {"ok": False, "reason": "maximum_requires_approval"}
            return {"ok": False, "reason": "aggressiveness_requires_approval"}
        return {"ok": True, "reason": "ok"}

    def report_state(self) -> Dict[str, Any]:
        return dict(self._last or {})

    def snapshot(self) -> Dict[str, Any]:
        """API-friendly alias."""
        return self.report_state()
