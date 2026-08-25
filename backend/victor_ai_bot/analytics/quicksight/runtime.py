from __future__ import annotations

import json
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .config import QuickSightAnalyticsConfig
from .dashboards import build_dashboards_with_status
from .datasets import (
    build_governance_metrics_row_with_status,
    build_regime_context_row_with_status,
    build_trading_metrics_rows_with_status,
    build_treasury_metrics_row_with_status,
)
from .query_engine import GenerativeQueryEngine
from .rbac import has_permission, PERM_TRIGGER_SIM, PERM_ASK_ANALYTICS
from .scenario import simulate_scenario
from ...pathing import canonical_data_dir


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_SAFE_RUNTIME_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)
_SAFE_EXPORT_EXCEPTIONS = (OSError, TypeError, ValueError)


def _coerce_mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _ensure_dir(p: str) -> bool:
    try:
        os.makedirs(p, exist_ok=True)
        return True
    except OSError:
        return False


class QuickSightAnalyticsRuntime:
    """QuickSight / Generative BI governance layer.

    Non-destructive:
      - produces datasets/dashboards for observability
      - cannot execute trades or modify strategy execution
    """

    def __init__(self, cfg: QuickSightAnalyticsConfig, *, pnl_store: Any = None):
        self.cfg = cfg
        self._pnl = pnl_store  # optional PnLStore

        self._last_tick_ts: float = 0.0
        self.datasets: Dict[str, List[Dict[str, Any]]] = {name: [] for name in (cfg.datasets or [])}
        self.dashboards: Dict[str, Any] = {}
        self.income: Dict[str, Any] = {}
        self.alerts: List[Dict[str, Any]] = []
        self.last_report: Dict[str, Any] = {}
        self.query_engine = GenerativeQueryEngine()
        self.export_status: Dict[str, Any] = {"ok": True, "writes": [], "last_error": ""}
        self.dataset_status: Dict[str, Any] = {}
        self.dashboard_status: Dict[str, Any] = {}

        export_dir = str(getattr(cfg, "export_dir", "") or "")
        if export_dir.startswith("backend/data"):
            cfg.export_dir = canonical_data_dir(export_dir)
        self._mark_export_dir_ready()

    # -----------------
    # RBAC helpers
    # -----------------
    def authorize(self, *, role: str, token: str, perm: str) -> bool:
        if not bool(self.cfg.rbac.enabled):
            return True
        # token check if provided
        expected = (self.cfg.rbac.role_tokens or {}).get(str(role).upper())
        if expected is not None and str(token or "") != str(expected):
            return False
        return bool(has_permission(role, perm))

    # -----------------
    # Main tick
    # -----------------
    async def tick(self, *, state: Dict[str, Any]) -> None:
        if not bool(self.cfg.enabled):
            return

        now = float(time.time())
        if (now - float(self._last_tick_ts)) < float(self.cfg.tick_seconds):
            return
        self._last_tick_ts = now

        ts = int(state.get("ts") or int(now))

        market = _coerce_mapping(state.get("market"))
        treasury = _coerce_mapping(state.get("treasury"))
        governance = _coerce_mapping(state.get("governance"))
        behave = _coerce_mapping(state.get("behaveagent"))
        pnl = _coerce_mapping(state.get("pnl"))
        pnl_store = self._pnl
        if (not pnl) and (pnl_store is not None):
            pnl = await self._safe_async_mapping(
                lambda: pnl_store.summary(window=3600),
                fallback=dict(pnl or {}),
            )

        circuit_breaker = _coerce_mapping(state.get("circuit_breaker"))
        agent_perf = _coerce_mapping(state.get("agent_perf"))

        # Income breakdown (from PnLStore if available)
        if pnl_store is not None:
            self.income = await self._safe_async_mapping(
                lambda: pnl_store.income_breakdown(window=3600),
                fallback=dict(self.income or {}),
            )
        else:
            self.income = dict(self.income or {})

        # Build dataset rows
        self.dataset_status = {}
        if "TRADING_METRICS" in self.datasets:
            rows, status = build_trading_metrics_rows_with_status(ts=ts, pnl_summary=pnl)
            self.dataset_status["TRADING_METRICS"] = dict(status or {})
            self._append_rows("TRADING_METRICS", rows)
        if "TREASURY_METRICS" in self.datasets:
            row, status = build_treasury_metrics_row_with_status(ts=ts, treasury_state=treasury)
            self.dataset_status["TREASURY_METRICS"] = dict(status or {})
            self._append_rows("TREASURY_METRICS", [row])
        if "GOVERNANCE_METRICS" in self.datasets:
            row, status = build_governance_metrics_row_with_status(
                ts=ts, governance_state=governance
            )
            self.dataset_status["GOVERNANCE_METRICS"] = dict(status or {})
            self._append_rows("GOVERNANCE_METRICS", [row])
        if "REGIME_CONTEXT" in self.datasets:
            row, status = build_regime_context_row_with_status(
                ts=ts, behave_state=behave, market_state=market
            )
            self.dataset_status["REGIME_CONTEXT"] = dict(status or {})
            self._append_rows("REGIME_CONTEXT", [row])

        # Dashboards
        self.dashboards, self.dashboard_status = build_dashboards_with_status(
            ts=ts,
            pnl=pnl,
            treasury=treasury,
            income=self.income,
            market=market,
            governance=governance,
            circuit_breaker=circuit_breaker,
            agent_perf=agent_perf,
        )

        # Alerting / report automation
        self._check_triggers(
            ts=ts, pnl=pnl, treasury=treasury, governance=governance, behave=behave
        )

        # Export (optional)
        if bool(self.cfg.export_on_tick):
            self._export_all()

    def _mark_export_dir_ready(self) -> None:
        ok = _ensure_dir(str(self.cfg.export_dir))
        if ok:
            self.export_status["last_error"] = ""
        else:
            self.export_status["ok"] = False
            self.export_status["last_error"] = "export_dir_unavailable"

    async def _safe_async_mapping(
        self,
        producer: Callable[[], Awaitable[Any]],
        *,
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            value = await producer()
        except _SAFE_RUNTIME_EXCEPTIONS:
            return dict(fallback or {})
        return dict(value or {}) if isinstance(value, dict) else dict(fallback or {})

    def _latest_trading_metrics_row(self) -> Dict[str, Any]:
        tm = self.datasets.get("TRADING_METRICS") or []
        if not tm:
            return {}
        row = tm[-1]
        return dict(row) if isinstance(row, dict) else {}

    def _record_export_result(self, path: str, *, ok: bool, error: str = "") -> None:
        writes = list(self.export_status.get("writes") or [])
        writes.append({"path": path, "ok": bool(ok), "error": str(error or "")})
        self.export_status["writes"] = writes[-20:]
        if not ok or error:
            self.export_status["ok"] = False
            self.export_status["last_error"] = str(error or "export_failed")

    def _write_jsonl(self, path: str, rows: List[Dict[str, Any]]) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row, sort_keys=True) + "\n")
        except _SAFE_EXPORT_EXCEPTIONS as exc:
            self._record_export_result(path, ok=False, error=str(exc))
            return
        self._record_export_result(path, ok=True)

    def _write_json(self, path: str, payload: Any) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, sort_keys=True, indent=2))
        except _SAFE_EXPORT_EXCEPTIONS as exc:
            self._record_export_result(path, ok=False, error=str(exc))
            return
        self._record_export_result(path, ok=True)

    def _append_rows(self, dataset: str, rows: List[Dict[str, Any]]) -> None:
        if dataset not in self.datasets:
            self.datasets[dataset] = []
        ds = self.datasets[dataset]
        for r in rows:
            ds.append(dict(r))
        # trim
        lim = int(self.cfg.max_rows_per_dataset)
        if lim > 0 and len(ds) > lim:
            self.datasets[dataset] = ds[-lim:]

    # -----------------
    # Triggers / reports
    # -----------------
    def _check_triggers(
        self,
        *,
        ts: int,
        pnl: Dict[str, Any],
        treasury: Dict[str, Any],
        governance: Dict[str, Any],
        behave: Dict[str, Any],
    ) -> None:
        if not bool(self.cfg.automation.enabled):
            return

        # Drawdown from trading metrics dataset (latest)
        latest_metrics = self._latest_trading_metrics_row()
        try:
            dd = _clip(float(latest_metrics.get("drawdown") or 0.0), 0.0, 1.0)
        except (TypeError, ValueError):
            dd = 0.0

        ag = str(
            ((treasury or {}).get("aggressiveness") or {}).get("aggressiveness_level") or "LOW"
        ).upper()
        threat = (governance or {}).get("threat") or {}
        tscore = float((threat.get("score") if isinstance(threat, dict) else 0.0) or 0.0)

        triggered = []
        if dd >= float(self.cfg.automation.drawdown_threshold):
            triggered.append({"type": "drawdown", "value": dd})
        # Aggressiveness escalation
        if ag in {
            "HIGH",
            "MAXIMUM",
        } and self.cfg.automation.aggressiveness_escalation_level.upper() in {"HIGH", "MAXIMUM"}:
            triggered.append({"type": "aggressiveness", "value": ag})
        if tscore >= float(self.cfg.automation.threat_monitor_breach):
            triggered.append({"type": "threat_breach", "value": tscore})

        if not triggered:
            return

        event = {
            "ts": int(ts),
            "triggers": triggered,
            "regime": str(behave.get("regime_label") or behave.get("regime") or "unknown"),
            "confidence": float(behave.get("confidence") or 0.0),
        }
        self.alerts.append(event)
        self.alerts = self.alerts[-200:]

        # Generate a simple report snapshot
        self.last_report = {
            "ts": int(ts),
            "event": event,
            "executive_overview": self.dashboards.get("EXECUTIVE_OVERVIEW") or {},
            "risk_panel": self.dashboards.get("RISK_CONTROL_PANEL") or {},
            "governance_audit": self.dashboards.get("GOVERNANCE_AUDIT_VIEW") or {},
        }

    def _export_all(self) -> None:
        out_dir = str(self.cfg.export_dir)
        self.export_status = {"ok": True, "writes": [], "last_error": ""}
        self._mark_export_dir_ready()
        if not bool(self.export_status.get("ok", True)):
            return

        for name, rows in (self.datasets or {}).items():
            path = os.path.join(out_dir, f"{name}.jsonl")
            self._write_jsonl(path, list(rows or []))

        self._write_json(os.path.join(out_dir, "dashboards.json"), self.dashboards)
        self._write_jsonl(os.path.join(out_dir, "alerts.jsonl"), list(self.alerts or []))
        self._write_json(os.path.join(out_dir, "last_report.json"), self.last_report)

    # -----------------
    # Public interface
    # -----------------
    def state(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.cfg.enabled),
            "mode": str(self.cfg.mode),
            "datasets": {k: len(v) for k, v in (self.datasets or {}).items()},
            "dashboards": list((self.dashboards or {}).keys()),
            "alerts": list(self.alerts[-50:]),
            "last_report": dict(self.last_report or {}),
            "income": dict(self.income or {}),
            "dataset_status": {k: dict(v or {}) for k, v in (self.dataset_status or {}).items()},
            "dashboard_status": {
                k: dict(v or {}) for k, v in (self.dashboard_status or {}).items()
            },
            "export_status": {
                "ok": bool(self.export_status.get("ok", True)),
                "last_error": str(self.export_status.get("last_error") or ""),
                "writes": list(self.export_status.get("writes") or []),
            },
        }

    def get_dataset(self, name: str) -> List[Dict[str, Any]]:
        return list(self.datasets.get(str(name), []) or [])

    def get_dashboards(self) -> Dict[str, Any]:
        return dict(self.dashboards or {})

    def ask(self, *, question: str, role: str, token: str = "") -> Dict[str, Any]:
        if not self.authorize(role=role, token=token, perm=PERM_ASK_ANALYTICS):
            return {"ok": False, "error": "forbidden"}
        return self.query_engine.ask(
            question=question,
            role=role,
            datasets=self.datasets,
            dashboards=self.dashboards,
            income=self.income,
        )

    def scenario(self, *, params: Dict[str, Any], role: str, token: str = "") -> Dict[str, Any]:
        if not self.authorize(role=role, token=token, perm=PERM_TRIGGER_SIM):
            return {"ok": False, "error": "forbidden"}
        # base metrics from latest trading metric row
        base = self._latest_trading_metrics_row()
        return simulate_scenario(
            base_metrics=base,
            income=self.income,
            hypothetical_volatility_change=float(
                params.get("hypothetical_volatility_change", 0.0) or 0.0
            ),
            capital_shift=float(params.get("capital_shift", 0.0) or 0.0),
            funding_rate_spike=float(params.get("funding_rate_spike", 0.0) or 0.0),
            aggressiveness_adjustment=float(params.get("aggressiveness_adjustment", 0.0) or 0.0),
        )
