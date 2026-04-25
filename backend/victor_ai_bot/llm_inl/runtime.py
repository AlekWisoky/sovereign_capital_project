from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from dataclasses import asdict
from typing import Any, Deque, Dict, List, Optional, Tuple

from .config import LLMINLConfig
from ..fioa.audit import AuditLogger
from ..portfolio_optimizer import opportunity_route_ready
from ..runtime_services.profitability_truth import (
    inspect_profit_after_costs_truth,
    opportunity_profit_after_costs_info,
)
from ..profitability_projection import profitability_summary_projection

_SAFE_VALUE_EXCEPTIONS: Tuple[type[BaseException], ...] = (TypeError, ValueError)
_SAFE_LOOKUP_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    AttributeError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
)
_SAFE_RUNTIME_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
    asyncio.TimeoutError,
)
_SAFE_QUEUE_EXCEPTIONS: Tuple[type[BaseException], ...] = (asyncio.QueueFull, RuntimeError)
_SAFE_JSON_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    TypeError,
    ValueError,
    UnicodeError,
    json.JSONDecodeError,
)


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, "") or isinstance(value, bool):
        return int(default)
    try:
        return int(value)
    except _SAFE_VALUE_EXCEPTIONS:
        try:
            return int(str(value))
        except _SAFE_VALUE_EXCEPTIONS:
            return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "") or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except _SAFE_VALUE_EXCEPTIONS:
        try:
            return float(str(value))
        except _SAFE_VALUE_EXCEPTIONS:
            return float(default)


def _safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    try:
        return list(value)
    except _SAFE_VALUE_EXCEPTIONS:
        return []


def _profit_after_costs_info(opp: Any) -> Tuple[int, bool, str]:
    return opportunity_profit_after_costs_info(opp)


def _plan_profit_after_costs_info(plan_like: Any) -> Tuple[int, bool, str]:
    plan = dict(plan_like or {}) if isinstance(plan_like, dict) else {}
    meta: Dict[str, Any] = {}
    if "profit_after_costs" in plan:
        meta["profit_after_costs"] = plan.get("profit_after_costs")
    safety = {}
    if isinstance(plan.get("safety"), dict):
        safety.update(plan.get("safety") or {})
    if "profit_after_costs_wei" in plan and "profit_after_costs_wei" not in safety:
        safety["profit_after_costs_wei"] = plan.get("profit_after_costs_wei")
    if safety:
        meta["safety"] = safety
    truth = inspect_profit_after_costs_truth(meta)
    return truth.value_wei, truth.verified, truth.reason_code


def _route_ready_info(opp: Any) -> Tuple[bool, str]:
    ready, reason, _reason_codes = opportunity_route_ready(opp)
    return bool(ready), str(reason or 'execution_route_not_ready')


def _estimated_profit_raw(opp: Any) -> int:
    return max(0, _safe_int(getattr(opp, "expected_profit_raw", 0), 0))


def _after_costs_rank_key(opp: Any) -> Tuple[int, int, int]:
    profit_after, verified, _reason = _profit_after_costs_info(opp)
    route_ready, _route_reason = _route_ready_info(opp)
    gross_est = _estimated_profit_raw(opp)
    if verified and route_ready and profit_after > 0:
        tier = 5
    elif verified and profit_after > 0:
        tier = 4
    elif verified and route_ready:
        tier = 3
    elif verified:
        tier = 2
    elif route_ready:
        tier = 1
    else:
        tier = 0
    return int(tier), int(profit_after if verified else 0), int(gross_est)


def _best_after_costs_opportunity(opps: List[Any]) -> Tuple[Any, int, bool, str]:
    candidates = list(opps or [])
    if not candidates:
        return None, 0, False, "profit_after_costs_unavailable"
    best_opp = max(candidates, key=_after_costs_rank_key)
    best_profit, best_verified, best_reason = _profit_after_costs_info(best_opp)
    return best_opp, best_profit, best_verified, best_reason


def _best_verified_route_ready_after_costs_opportunity(opps: List[Any]) -> Tuple[Any, int, bool, str, str]:
    best_opp: Any = None
    best_profit = 0
    best_verified = False
    best_profit_reason = "profit_after_costs_unavailable"
    best_route_reason = "execution_route_not_ready"
    for opp in list(opps or []):
        route_ready, route_reason = _route_ready_info(opp)
        if not route_ready:
            continue
        profit_after, verified, profit_reason = _profit_after_costs_info(opp)
        if not (verified and profit_after > 0):
            continue
        if best_opp is None or profit_after > best_profit:
            best_opp = opp
            best_profit = profit_after
            best_verified = True
            best_profit_reason = profit_reason
            best_route_reason = route_reason
    return best_opp, best_profit, best_verified, best_profit_reason, best_route_reason


class NarrativeMemory:
    """Bounded in-memory narrative history."""

    def __init__(self, *, max_items: int = 100):
        self.max_items = max(10, min(10_000, int(max_items)))
        self._items: Deque[Dict[str, Any]] = deque(maxlen=self.max_items)

    def append(self, item: Dict[str, Any]) -> None:
        self._items.append(item)

    def size(self) -> int:
        return len(self._items)

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(5_000, int(limit)))
        if not self._items:
            return []
        out = list(self._items)
        return out[-limit:]

    def last(self) -> Optional[Dict[str, Any]]:
        try:
            return self._items[-1]
        except IndexError:
            return None

    def as_lines(self, limit: int = 100) -> List[str]:
        out = []
        for it in self.tail(limit=limit):
            ts = int(it.get("ts") or 0)
            txt = str(it.get("text") or "")
            out.append(f"{ts}:{txt}")
        return out


class LLMINLRuntime:
    """LLM-mediated Interactive Narrative Layer (LLM-INL).

    Non-breaking overlay:
      - Observes runtime state and execution events.
      - Provides an interactive query interface for operators.
      - Optional LLM calls are best-effort and never required.
    """

    # Data access levels
    PUBLIC_ANALYTICS = "PUBLIC_ANALYTICS"
    INTERNAL_STRATEGY = "INTERNAL_STRATEGY"
    CONFIDENTIAL_SIGNAL = "CONFIDENTIAL_SIGNAL"

    def __init__(
        self,
        *,
        cfg: Optional[LLMINLConfig],
        chain: str,
        data_dir: str,
        fioa: Any = None,
    ):
        self.cfg = cfg or LLMINLConfig(enabled=False)
        self.chain = str(chain)
        self._fioa = fioa

        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

        self._memory = NarrativeMemory(max_items=int(getattr(self.cfg, "max_narrative_memory", 100) or 100))
        self._ws_clients: List[asyncio.Queue] = []

        self._last_scan_block: int = 0

        audit_path = os.path.join(str(data_dir), f"llm_inl_audit_{self.chain}.jsonl")
        self.audit = AuditLogger(
            audit_path,
            max_bytes=int(getattr(self.cfg, "audit_max_bytes", 25_000_000) or 25_000_000),
            enabled=bool(getattr(self.cfg, "audit_enabled", True)),
        )

        # personalization
        self.explanation_level: str = str(getattr(self.cfg, "explanation_level", "STANDARD") or "STANDARD").upper()
        if self.explanation_level not in {"BASIC", "STANDARD", "ADVANCED"}:
            self.explanation_level = "STANDARD"

        # counters
        self.system_cycle: int = 0
        self.conflicts_detected: int = 0
        self.last_conflict_ts: int = 0
        self.last_llm_error: str = ""

        # runtime accessor (set on start)
        self._get_runtime: Any = None

        self._loop_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_cycle_ts": 0,
        }
        self._ws_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_publish_ts": 0,
        }
        self._llm_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_success_ts": 0,
        }

    def _mark_state(self, bucket: Dict[str, Any], *, ok: bool, code: str = "", error: str = "", ts_key: str = "") -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")
        if ok and ts_key:
            bucket[ts_key] = int(time.time())

    def _mark_loop_ok(self) -> None:
        self._mark_state(self._loop_state, ok=True, ts_key="last_cycle_ts")

    def _mark_loop_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._loop_state, ok=False, code=code, error=str(exc))

    def _mark_ws_ok(self) -> None:
        self._mark_state(self._ws_state, ok=True, ts_key="last_publish_ts")

    def _mark_ws_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._ws_state, ok=False, code=code, error=str(exc))

    def _mark_llm_ok(self) -> None:
        self.last_llm_error = ""
        self._mark_state(self._llm_state, ok=True, ts_key="last_success_ts")

    def _mark_llm_error(self, code: str, detail: BaseException | str) -> None:
        self.last_llm_error = f"{code}:{detail}"[:400]
        self._mark_state(self._llm_state, ok=False, code=code, error=str(detail))

    # -------------------------
    # lifecycle
    # -------------------------
    def start(self, runtime: Any) -> None:
        if not bool(getattr(self.cfg, "enabled", False)):
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._get_runtime = lambda: runtime
        self._task = asyncio.create_task(self._loop())
        self.audit.append("LLM_INL_START", chain=self.chain, cfg=self._safe_cfg_snapshot())

    async def stop(self) -> None:
        if not bool(getattr(self.cfg, "enabled", False)):
            return
        self._stop.set()
        if self._task:
            self._task.cancel()
        self._task = None
        self.audit.append("LLM_INL_STOP", chain=self.chain)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.system_cycle += 1
                rt = self._get_runtime() if self._get_runtime else None
                if rt is not None:
                    if bool(getattr(self.cfg, "conflict_mediation_enabled", True)):
                        await self._mediate_agent_conflict(rt)
                    if bool(getattr(self.cfg, "emit_block_summaries", False)):
                        await self._maybe_emit_block_summary(rt)
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_loop_error("llm_inl_loop_failed", exc)
            else:
                self._mark_loop_ok()
            await asyncio.sleep(float(getattr(self.cfg, "loop_interval_s", 1.0) or 1.0))

    # -------------------------
    # websocket helpers
    # -------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._ws_clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._ws_clients.remove(q)
        except ValueError:
            pass

    def _publish_ws(self, item: Dict[str, Any]) -> None:
        failed = False
        for q in list(self._ws_clients):
            try:
                q.put_nowait(item)
            except _SAFE_QUEUE_EXCEPTIONS as exc:
                failed = True
                self._mark_ws_error("ws_publish_failed", exc)
        if not failed:
            self._mark_ws_ok()

    # -------------------------
    # memory and audit
    # -------------------------
    def store_event(self, text: str, *, kind: str = "event", level: str = "info", **meta: Any) -> Dict[str, Any]:
        if not bool(getattr(self.cfg, "enabled", False)):
            return {}
        item: Dict[str, Any] = {
            "ts": int(time.time()),
            "chain": self.chain,
            "kind": str(kind or "event"),
            "level": str(level or "info"),
            "text": str(text or ""),
        }
        if meta:
            item["meta"] = meta
        self._memory.append(item)

        # Persist (append-only)
        if bool(getattr(self.cfg, "persist_history", True)):
            self.audit.append("NarrativeEvent", **item)

        # Push to websocket listeners
        self._publish_ws(item)
        return item

    def history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._memory.tail(limit=limit)

    # -------------------------
    # personalization
    # -------------------------
    def set_explanation_level(self, level: str) -> str:
        lvl = str(level or "STANDARD").upper()
        if lvl not in {"BASIC", "STANDARD", "ADVANCED"}:
            lvl = "STANDARD"
        self.explanation_level = lvl
        self.audit.append("ExplanationLevel", level=lvl)
        return lvl

    def format_explanation(self, base_text: str, *, details: str = "") -> str:
        txt = str(base_text or "")
        if self.explanation_level == "BASIC":
            return f"Summary: {txt}"
        if self.explanation_level == "ADVANCED":
            # Keep details bounded.
            det = (str(details or "").strip())
            if len(det) > 2000:
                det = det[:2000] + "…"
            if det:
                return f"Detailed Technical Breakdown: {txt}\n\n{det}"
            return f"Detailed Technical Breakdown: {txt}"
        return txt

    # -------------------------
    # decision narrative generation (Section 2)
    # -------------------------
    def generate_decision_narrative(
        self,
        *,
        agent_id: str,
        action: str,
        risk_score: float,
        pnl_expectation_wei: int,
        rationale: str = "",
        details: str = "",
        kind: str = "decision",
        **meta: Any,
    ) -> Dict[str, Any]:
        pnl = int(pnl_expectation_wei or 0)
        rs = float(max(0.0, min(1.0, float(risk_score or 0.0))))

        base = (
            f"Agent {agent_id} executed {action}. "
            f"Expected PnL (after costs): {pnl} wei. "
            f"Risk Score: {rs:.2f}."
        )
        if rationale:
            base += f" Rationale: {str(rationale).strip()}"

        msg = self.format_explanation(base, details=details)
        return self.store_event(
            msg,
            kind=kind,
            agent_id=str(agent_id),
            action=str(action),
            risk_score=float(rs),
            pnl_expectation_wei=str(pnl),
            **meta,
        )

    # -------------------------
    # interactive query engine (Section 3)
    # -------------------------
    async def query(self, rt: Any, *, agent_id: str, query_text: str, data_level: str = INTERNAL_STRATEGY) -> Dict[str, Any]:
        if not bool(getattr(self.cfg, "enabled", False)):
            return {"ok": False, "error": "llm_inl_disabled"}
        if not bool(getattr(self.cfg, "interactive_mode", True)):
            return {"ok": False, "error": "interactive_disabled"}

        q = str(query_text or "").strip()
        if not q:
            return {"ok": False, "error": "empty_query"}

        # Confidentiality gate (best-effort)
        if bool(getattr(self.cfg, "confidentiality_strict", False)):
            if str(data_level) == self.CONFIDENTIAL_SIGNAL and str(agent_id) != "GOVERNANCE_AGENT":
                self.store_event(
                    f"ConfidentialAccessBlocked:{agent_id}",
                    kind="policy",
                    level="warn",
                    agent_id=str(agent_id),
                    data_level=str(data_level),
                )
                return {"ok": False, "error": "confidential_access_blocked"}

        # Built-in command set (stable).
        if q == "WHY_LAST_DECISION":
            last = self._memory.last() or {}
            return {"ok": True, "response": self.format_explanation(str(last.get("text") or "No narrative yet.")), "last": last}
        if q == "SHOW_RISK_DRIVERS":
            rp, rs = self._risk_profile(rt)
            return {"ok": True, "response": self.format_explanation("Current Risk Drivers", details=json.dumps(rp, indent=2)), "risk_score": rs, "risk_profile": rp}
        if q == "SIMULATE_SCENARIO":
            sim = await self._scenario_simulation(rt)
            return {"ok": True, **sim}

        # Convenience queries (profit-optimized operator UX)
        if q == "SHOW_PROFIT_LEVERS":
            ins = await self.insights(rt)
            return {"ok": True, "response": self.format_explanation("Profit levers and operational suggestions", details=json.dumps(ins, indent=2)), "insights": ins}

        # Free-form query: use LLM if configured; else fallback.
        if str(getattr(self.cfg, "llm_mode", "template") or "template").lower() == "llm":
            ans = await self._llm_answer(rt, agent_id=agent_id, question=q)
            if ans:
                self.store_event(ans, kind="query", agent_id=str(agent_id), query=q)
                return {"ok": True, "response": ans, "llm": True}
            # fall through

        # Fallback: show supported commands.
        supported = ["WHY_LAST_DECISION", "SHOW_RISK_DRIVERS", "SIMULATE_SCENARIO", "SHOW_PROFIT_LEVERS"]
        resp = (
            f"Query not recognized (or LLM not configured). Supported commands: {', '.join(supported)}. "
            f"You asked: {q}"
        )
        self.store_event(resp, kind="query", level="info", agent_id=str(agent_id), query=q)
        return {"ok": True, "response": resp, "llm": False}

    # -------------------------
    # narrative audit report (Section 5)
    # -------------------------
    def narrative_audit_report(self, limit: int = 100) -> str:
        lines = self._memory.as_lines(limit=limit)
        out = ["==== INTERACTIVE GOVERNANCE REPORT ===="]
        out.extend(lines)
        out.append("==== END REPORT ====")
        return "\n".join(out)

    # -------------------------
    # conflict mediation narrative engine (Section 6)
    # -------------------------
    async def _mediate_agent_conflict(self, rt: Any) -> None:
        conflict = None

        fioa = getattr(rt, "_fioa", None)
        if fioa is not None:
            op_conf = _safe_int(getattr(fioa, "op_conflicts", 0), 0)
            if op_conf > int(self.conflicts_detected):
                conflict = {"type": "fioa_conflict", "delta": op_conf - int(self.conflicts_detected)}
                self.conflicts_detected = op_conf

        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        max_pending = _safe_int(getattr(cfg_exec, "max_pending_txs", 1), 1)
        pending_obj = getattr(rt, "_pending", {}) or {}
        cur_pending = len(pending_obj) if hasattr(pending_obj, "__len__") else 0
        if max_pending > 0 and cur_pending > max_pending:
            conflict = {"type": "pending_pressure", "pending": cur_pending, "cap": max_pending}

        if conflict:
            now = int(time.time())
            if self.last_conflict_ts and (now - self.last_conflict_ts) < 5:
                return
            self.last_conflict_ts = now
            mediation_text = (
                "Conflict detected between agents or subsystems. "
                "Proposed resolution: weighted consensus based on risk-adjusted ROI; "
                "Governance override available if needed."
            )
            self.store_event(mediation_text, kind="conflict", level="warn", conflict=conflict)

    # -------------------------
    # block scan summary hook
    # -------------------------
    async def _maybe_emit_block_summary(self, rt: Any) -> None:
        metrics = getattr(rt, "metrics", None)
        bn = _safe_int(getattr(metrics, "last_block", 0), 0)
        if bn <= 0:
            return

        interval = _safe_int(getattr(self.cfg, "block_summary_interval_blocks", 5), 5)
        if interval <= 0:
            interval = 5
        if bn == self._last_scan_block:
            return
        self._last_scan_block = bn
        if (bn % interval) != 0:
            return

        opps = _safe_list(getattr(rt, "_opps", []) or [])
        top, top_profit, top_profit_verified, top_profit_reason = _best_after_costs_opportunity(opps)
        top_route = ""
        if top is not None:
            top_route = str(getattr(top, "route_id", "") or "") or str(getattr(top, "id", "") or "")

        projection = profitability_summary_projection(top) if top is not None else {}
        display_profit = _safe_int((projection or {}).get("displayProfitAfterCostsWeiInt"), 0)

        minp = _safe_int(getattr(self.cfg, "block_summary_min_profit_wei", 0), 0)
        if minp > 0 and display_profit < minp:
            return

        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        base = f"Block {bn} scan summary: {len(opps)} opportunities; top expected profit ≈ {display_profit} wei."
        det = {
            "chain": self.chain,
            "block": bn,
            "opps": len(opps),
            "top_route_id": top_route,
            "top_profit_wei": str(display_profit),
            "top_profit_after_costs_wei": str(display_profit),
            "top_profit_after_costs_verified": bool(top_profit_verified),
            "top_profit_after_costs_reason": str(top_profit_reason or "profit_after_costs_unavailable"),
            "gas_mode": str(getattr(cfg_exec, "gas_mode", "")),
            "send_mode": str(getattr(cfg_exec, "send_mode", "")),
        }
        self.store_event(self.format_explanation(base, details=json.dumps(det, indent=2)), kind="scan", level="info", block=bn)

    # -------------------------
    # execution hooks (called by RuntimeBundle)
    # -------------------------
    def on_exec_result(self, rt: Any, *, res: Any, opp: Any, mode: str, agent_id: str, risk_score: float) -> None:
        """Observe an execution attempt result (dry-run, submitted, denied, etc.)."""

        if not bool(getattr(self.cfg, "enabled", False)):
            return

        ok = bool(getattr(res, "ok", False))
        dry_run = bool(getattr(res, "dry_run", True))
        attempted = bool(getattr(res, "attempted", False))
        submitted = bool(getattr(res, "submitted", False))
        reason = str(getattr(res, "reason", "") or "")
        tx_hash = str(getattr(res, "tx_hash", "") or "")

        plan = getattr(res, "plan", None) or {}
        exp_after, exp_after_verified, exp_after_reason = _plan_profit_after_costs_info(plan)

        # Rationale is heuristically derived.
        rationale = self._rationale_from_state(rt, opp, res)
        details = self._details_for_exec(rt, opp, res)

        action = "trade" if str(mode) in {"auto", "manual"} else str(mode)
        if not attempted:
            action = "execution_denied"
        elif submitted and (not dry_run):
            action = "trade_submitted"
        elif ok and dry_run:
            action = "trade_simulated"
        elif attempted and (not ok):
            action = "trade_failed"

        self.generate_decision_narrative(
            agent_id=agent_id,
            action=action,
            risk_score=float(risk_score),
            pnl_expectation_wei=int(exp_after),
            rationale=rationale,
            details=details,
            kind="execution",
            pnl_expectation_verified=bool(exp_after_verified),
            pnl_expectation_reason=str(exp_after_reason or "profit_after_costs_unavailable"),
            ok=bool(ok),
            attempted=bool(attempted),
            submitted=bool(submitted),
            dry_run=bool(dry_run),
            reason=reason,
            tx_hash=tx_hash,
            opportunity_id=str(getattr(opp, "id", "") or ""),
            route_id=str(getattr(opp, "route_id", "") or ""),
        )

    def on_receipt(self, rt: Any, *, tx_hash: str, status: int, decoded: Dict[str, Any], pending: Dict[str, Any]) -> None:
        if not bool(getattr(self.cfg, "enabled", False)):
            return

        # Determine agent from pending mode.
        mode = str(pending.get("mode") or "")
        agent = "ARBITRAGE_AGENT" if mode == "auto" else "HUMAN_OPERATOR"

        realized_after = _safe_int(decoded.get("realized_profit_after_gas_wei") or 0, 0)

        risk_profile, risk_score = self._risk_profile(rt)

        if status == 1:
            action = "receipt_success"
            rationale = "Receipt confirmed successful execution; realized profit updated."
            level = "info"
        else:
            action = "receipt_revert"
            rationale = "Receipt indicates revert; consider tightening simulation gates or switching to private submission."
            level = "warn"

        base = f"Tx {tx_hash} finalized with status={status}. Realized profit-after-gas (if decoded) ≈ {realized_after} wei."
        details = {
            "tx_hash": tx_hash,
            "status": status,
            "realized_profit_after_gas_wei": str(realized_after),
            "risk_score": float(risk_score),
            "risk_profile": risk_profile,
            "pending": {k: pending.get(k) for k in ["opportunity_id", "route_id", "mode"] if k in pending},
            "decoded": decoded,
        }
        msg = self.format_explanation(base, details=json.dumps(details, indent=2))
        self.store_event(msg, kind="receipt", level=level, agent_id=agent, action=action, tx_hash=tx_hash, rationale=rationale)

    # -------------------------
    # profit & governance insights (additive)
    # -------------------------
    async def insights(self, rt: Any) -> Dict[str, Any]:
        """Return bounded profit/ops insights (read-only)."""

        risk_profile, risk_score = self._risk_profile(rt)
        try:
            pnl = await rt.pnl_summary(window=50)
        except _SAFE_RUNTIME_EXCEPTIONS:
            pnl = {}

        opps = _safe_list(getattr(rt, "_opps", []) or [])
        top, top_after, top_after_verified, top_after_reason = _best_after_costs_opportunity(opps)

        suggestions: List[str] = []
        metrics = getattr(rt, "metrics", None)
        eff = _safe_float(getattr(metrics, "efficiency_pct", 0.0), 0.0)
        sr = _safe_float(getattr(metrics, "success_rate_pct", 0.0), 0.0)
        pnl_n = _safe_int((pnl or {}).get("n", 0), 0) if isinstance(pnl, dict) else 0

        if eff < 40.0 and pnl_n >= 10:
            suggestions.append("Efficiency is low vs expected. Consider increasing slippage_bps slightly, tightening route selection, or moving to private/protected submission.")
        if sr < 60.0 and pnl_n >= 10:
            suggestions.append("Success rate is low. Consider enabling require_simulation, lowering sizing (base_borrow_amount), or increasing minProfitAbs to filter thin edges.")
        if risk_score > 0.75:
            suggestions.append("System risk is elevated. Prefer private submission, conservative gas_mode, and reduce notional until stress normalizes.")
        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        if top_after_verified and top_after > 0 and not bool(getattr(cfg_exec, "auto_trading", False)):
            suggestions.append("Top opportunity appears profitable after costs; you can manually simulate/execute, then gradually enable auto_trading once confident.")

        cfg_safety = getattr(getattr(rt, "cfg", None), "safety", None)
        mp_abs = _safe_int(getattr(cfg_safety, "minProfitAbs", "0"), 0)
        if top_after_verified and mp_abs > 0 and top_after > 0 and top_after < mp_abs:
            suggestions.append("Your minProfitAbs may be too strict for current market. Consider lowering it temporarily (with simulation enabled) to capture more edges.")

        return {
            "chain": self.chain,
            "risk_score": float(risk_score),
            "risk_profile": risk_profile,
            "auto_trading": bool(getattr(cfg_exec, "auto_trading", False)),
            "send_mode": str(getattr(cfg_exec, "send_mode", "")),
            "gas_mode": str(getattr(cfg_exec, "gas_mode", "")),
            "top_opportunity_profit_after_costs_wei": str(top_after),
            "top_opportunity_profit_after_costs_verified": bool(top_after_verified),
            "top_opportunity_profit_after_costs_reason": str(top_after_reason or "profit_after_costs_unavailable"),
            "pnl": pnl,
            "suggestions": suggestions[:12],
        }

    # -------------------------
    # scenario simulation (what-if)
    # -------------------------
    async def _scenario_simulation(self, rt: Any) -> Dict[str, Any]:
        """Simulate PnL vs notional multipliers for the current top opportunity."""

        opps = _safe_list(getattr(rt, "_opps", []) or [])
        if not opps:
            return {"response": "No opportunities available to simulate.", "results": []}

        base_opp, _base_profit_after, _base_verified, base_profit_reason, base_route_reason = (
            _best_verified_route_ready_after_costs_opportunity(opps)
        )
        if base_opp is None:
            reason = str(base_route_reason or base_profit_reason or "selection_unavailable")
            return {
                "response": f"No route-ready, after-fee-verified opportunity available to simulate ({reason}).",
                "results": [],
            }

        route = getattr(base_opp, "route", None)
        legs = getattr(route, "legs", []) or []
        first_leg = legs[0] if legs else None
        base_in = _safe_int(getattr(first_leg, "amount_in", "0") if first_leg is not None else "0", 0)
        if base_in <= 0:
            return {"response": "Top opportunity has invalid amount_in.", "results": []}

        read_url = rt.rpc_manager.best_read() if hasattr(rt, "rpc_manager") else ""
        if not read_url:
            return {"response": "No RPC endpoint available for simulation.", "results": []}

        from ..rpc import JsonRpcClient
        from ..arb_engine import requote_opportunity
        from ..gas import suggest_gas
        from ..safety import check_profit_and_repay

        mults = [0.5, 1.0, 1.5, 2.0]
        _, rs = self._risk_profile(rt)
        if float(rs) < 0.35:
            mults.append(3.0)

        results: List[Dict[str, Any]] = []
        best = None

        async with JsonRpcClient(read_url, timeout_s=10.0, max_concurrency=20, max_batch=50) as rpc:
            cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
            cfg_safety = getattr(getattr(rt, "cfg", None), "safety", None)
            max_fee, prio = await suggest_gas(rpc, mode=str(getattr(cfg_exec, "gas_mode", "standard")), presets=cfg_exec.gas_presets)
            gas_limit = _safe_int(getattr(cfg_exec, "gas_limit", 550000), 550000)
            gas_cost = int(max_fee) * int(gas_limit)

            for m in mults:
                target_in = max(1, int(base_in * float(m)))
                cap = _safe_int(getattr(cfg_safety, "max_borrow_amount", "0"), 0)
                if cap > 0:
                    target_in = min(target_in, cap)

                rq = await requote_opportunity(
                    rpc,
                    rt.cfg,
                    rt.cache,
                    base_opp,
                    new_amount_in=int(target_in),
                    slippage_bps=_safe_int(getattr(cfg_safety, "slippage_bps", 50), 50),
                )
                if rq is None:
                    results.append({"mult": m, "amount_in": str(target_in), "ok": False, "reason": "requote_failed"})
                    continue

                min_outs = getattr(rq, "min_outs", None) or []
                rq_route = getattr(rq, "route", None)
                rq_legs = getattr(rq_route, "legs", []) or []
                last_leg = rq_legs[-1] if rq_legs else None
                amount_out = _safe_int(min_outs[-1] if min_outs else getattr(last_leg, "min_out", 0), 0)

                sr = check_profit_and_repay(
                    amount_in_wei=int(target_in),
                    amount_out_wei=int(amount_out),
                    min_profit_abs_wei=_safe_int(getattr(cfg_safety, "minProfitAbs", "0"), 0),
                    min_profit_bps=_safe_int(getattr(cfg_safety, "minProfitBps", 0), 0),
                    flashloan_fee_bps=_safe_int(getattr(cfg_exec, "flashloan_fee_bps", 9), 9),
                    gas_cost_wei=int(gas_cost),
                )

                prof = _safe_int(getattr(sr, "profit_after_costs_wei", 0), 0)
                roi_bps = int((prof * 10_000) / target_in) if target_in > 0 else 0
                row = {
                    "mult": float(m),
                    "amount_in": str(target_in),
                    "amount_out": str(amount_out),
                    "profit_after_costs_wei": str(prof),
                    "roi_bps": int(roi_bps),
                    "safe": bool(getattr(sr, "ok", False)),
                    "reason": ("ok" if getattr(sr, "ok", False) else str(getattr(sr, "reason", ""))),
                }
                results.append(row)
                if getattr(sr, "ok", False):
                    if best is None or prof > int(best.get("profit_after_costs_wei") or 0):
                        best = dict(row)

        lines = []
        for r in results:
            if not r.get("ok", True) and r.get("reason") == "requote_failed":
                lines.append(f"mult={r['mult']}: requote_failed")
                continue
            lines.append(
                f"mult={r['mult']:.2f} in={r['amount_in']} profit={r.get('profit_after_costs_wei','0')} roi_bps={r.get('roi_bps',0)} safe={r.get('safe', False)}"
            )

        summary = "Scenario simulation (profit-after-costs vs notional multipliers):\n" + "\n".join(lines)
        if best is not None:
            summary += f"\n\nRecommended multiplier: {best.get('mult')} (highest safe profit-after-costs)."

        self.store_event(self.format_explanation(summary), kind="scenario", level="info", route_id=str(getattr(base_opp, "route_id", "") or ""))
        return {"response": self.format_explanation(summary), "results": results, "best": best}

    # -------------------------
    # risk model / rationale helpers
    # -------------------------
    def _risk_profile(self, rt: Any) -> Tuple[Dict[str, Any], float]:
        stress = 0.0
        fioa = getattr(rt, "_fioa", None)
        if fioa is not None:
            stress = _safe_float(getattr(fioa, "last_stress", 0.0), 0.0)

        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        max_pending = max(1, _safe_int(getattr(cfg_exec, "max_pending_txs", 1), 1))
        pending_obj = getattr(rt, "_pending", {}) or {}
        cur = len(pending_obj) if hasattr(pending_obj, "__len__") else 0
        pending_ratio = max(0.0, min(1.0, float(cur) / float(max_pending)))

        mev = 0.0
        mr = getattr(rt, "_mev", None)
        if mr is not None:
            st = mr.state() if hasattr(mr, "state") else {}
            mev = _safe_float((st or {}).get("sandwich_risk_p90"), 0.0) if isinstance(st, dict) else 0.0
        mev = max(0.0, min(1.0, mev))

        metrics = getattr(rt, "metrics", None)
        basefee = _safe_float(getattr(metrics, "basefee_gwei", 0.0), 0.0)
        gas = min(1.0, max(0.0, basefee / 200.0))

        risk = max(stress, (0.45 * mev + 0.35 * gas + 0.20 * pending_ratio))
        risk = max(0.0, min(1.0, float(risk)))

        prof = {
            "system_stress": float(stress),
            "mev_risk": float(mev),
            "gas_regime": float(gas),
            "pending_ratio": float(pending_ratio),
        }
        return prof, float(risk)

    def _rationale_from_state(self, rt: Any, opp: Any, res: Any) -> str:
        profit_after, verified, profit_reason = _profit_after_costs_info(opp)
        route_ready, route_reason = _route_ready_info(opp)

        reasons = []
        if verified and profit_after > 0:
            reasons.append("profit-after-costs positive")
        elif not verified:
            reasons.append(f"after-fee truth unavailable ({str(profit_reason or 'profit_after_costs_unavailable')})")

        if not route_ready:
            reasons.append(f"route not ready ({str(route_reason or 'execution_route_not_ready')})")

        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        send_mode = str(getattr(cfg_exec, "send_mode", "public"))
        if send_mode != "public":
            reasons.append("private submission to reduce MEV leakage")
        if getattr(res, "dry_run", True) and getattr(res, "ok", False):
            reasons.append("simulation passed")

        if not reasons:
            return "Decision aligned with current volatility and capital allocation constraints."
        return "Decision aligned with: " + ", ".join(reasons) + "."

    def _details_for_exec(self, rt: Any, opp: Any, res: Any) -> str:
        plan = getattr(res, "plan", None) or {}
        route = getattr(opp, "route", None)
        legs = getattr(route, "legs", []) or []
        leg_count = len(legs) if hasattr(legs, "__len__") else 0
        risk_profile, risk_score = self._risk_profile(rt)
        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)

        details = {
            "chain": self.chain,
            "mode": str(getattr(res, "mode", "") or ""),
            "route_id": str(getattr(opp, "route_id", "") or ""),
            "legs": int(leg_count),
            "send_mode": str(getattr(cfg_exec, "send_mode", "")),
            "gas_mode": str(getattr(cfg_exec, "gas_mode", "")),
            "risk_score": float(risk_score),
            "risk_profile": risk_profile,
            "plan": {
                k: plan.get(k)
                for k in [
                    "amount_in",
                    "amount_out",
                    "profit_after_costs",
                    "profit_after_costs_wei",
                    "flashloan_fee",
                    "gas_cost",
                    "gas_limit",
                    "max_fee",
                    "priority_fee",
                ]
                if k in plan
            },
            "res": {
                "ok": bool(getattr(res, "ok", False)),
                "attempted": bool(getattr(res, "attempted", False)),
                "submitted": bool(getattr(res, "submitted", False)),
                "dry_run": bool(getattr(res, "dry_run", True)),
                "reason": str(getattr(res, "reason", "") or ""),
                "tx_hash": str(getattr(res, "tx_hash", "") or ""),
            },
        }
        try:
            return json.dumps(details, indent=2)
        except _SAFE_JSON_EXCEPTIONS:
            return ""

    # -------------------------
    # LLM answering (optional)
    # -------------------------
    async def _llm_answer(self, rt: Any, *, agent_id: str, question: str) -> str:
        key_env = str(getattr(self.cfg, "llm_api_key_env", "VICTOR_LLM_API_KEY") or "VICTOR_LLM_API_KEY")
        api_key = (os.environ.get(key_env, "") or "").strip()
        if not api_key:
            self._mark_llm_error("llm_api_key_missing", key_env)
            return ""

        provider = str(getattr(self.cfg, "llm_provider", "openai") or "openai").lower()
        if provider != "openai":
            self._mark_llm_error("llm_provider_unsupported", provider)
            return ""

        endpoint = str(getattr(self.cfg, "llm_endpoint", "") or "").strip()
        if not endpoint:
            self._mark_llm_error("llm_endpoint_missing", "")
            return ""

        model = str(getattr(self.cfg, "llm_model", "") or "").strip() or "gpt-4o-mini"
        timeout_s = _safe_float(getattr(self.cfg, "llm_timeout_s", 10.0), 10.0)
        temperature = _safe_float(getattr(self.cfg, "llm_temperature", 0.2), 0.2)

        ctx_lines = self._memory.as_lines(limit=min(50, _safe_int(getattr(self.cfg, "max_narrative_memory", 100), 100)))
        risk_profile, risk_score = self._risk_profile(rt)
        metrics = getattr(rt, "metrics", None)
        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None)
        cfg_safety = getattr(getattr(rt, "cfg", None), "safety", None)
        state = {
            "chain": self.chain,
            "risk_score": float(risk_score),
            "risk_profile": risk_profile,
            "metrics": {
                "last_block": _safe_int(getattr(metrics, "last_block", 0), 0),
                "scan_ms": _safe_int(getattr(metrics, "scan_ms", 0), 0),
                "success_rate_pct": _safe_float(getattr(metrics, "success_rate_pct", 0.0), 0.0),
                "efficiency_pct": _safe_float(getattr(metrics, "efficiency_pct", 0.0), 0.0),
            },
            "settings": {
                "auto_trading": bool(getattr(cfg_exec, "auto_trading", False)),
                "send_mode": str(getattr(cfg_exec, "send_mode", "")),
                "gas_mode": str(getattr(cfg_exec, "gas_mode", "")),
                "slippage_bps": _safe_int(getattr(cfg_safety, "slippage_bps", 50), 50),
                "minProfitAbs": str(getattr(cfg_safety, "minProfitAbs", "0") or "0"),
                "minProfitBps": _safe_int(getattr(cfg_safety, "minProfitBps", 0), 0),
            },
        }

        sys_prompt = (
            "You are an execution-governance narrative assistant for an automated DeFi arbitrage system. "
            "Your job is to answer operator questions concisely, explain trade decisions, "
            "and suggest safe, profit-optimized adjustments. "
            "Do not reveal private route details unless explicitly asked and authorized."
        )
        user_prompt = (
            f"Operator agent_id={agent_id}.\n\n"
            f"CurrentStateJSON:\n{json.dumps(state, indent=2)}\n\n"
            f"RecentNarrativeContext:\n" + "\n".join(ctx_lines[-30:]) + "\n\n"
            f"Question: {question}"
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            import aiohttp
        except ImportError as exc:
            self._mark_llm_error("llm_import_failed", exc)
            return ""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model, "messages": messages, "temperature": temperature}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s)) as sess:
                async with sess.post(endpoint, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        txt = ""
                        try:
                            txt = await resp.text()
                        except (aiohttp.ClientError, UnicodeError, ValueError, RuntimeError):
                            txt = ""
                        self._mark_llm_error(f"llm_http_{resp.status}", txt[:200])
                        return ""
                    obj = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, RuntimeError) as exc:
            self._mark_llm_error("llm_request_failed", exc)
            return ""

        choices = obj.get("choices") if isinstance(obj, dict) else None
        if not choices:
            self._mark_llm_error("llm_response_invalid", "missing_choices")
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if not content:
            self._mark_llm_error("llm_response_invalid", "missing_content")
            return ""
        self._mark_llm_ok()
        return str(content).strip()

    # -------------------------
    # state for API
    # -------------------------
    def state(self, rt: Any = None) -> Dict[str, Any]:
        last = self._memory.last() or {}
        public_last_text = str(last.get("text") or "")
        cfg_exec = getattr(getattr(rt, "cfg", None), "execution", None) if rt is not None else None
        if bool(getattr(cfg_exec, "redact_routes_when_private", False)) and str(getattr(cfg_exec, "send_mode", "public")) != "public":
            public_last_text = "(redacted in private send_mode)"

        return {
            "ok": True,
            "enabled": bool(getattr(self.cfg, "enabled", False)),
            "chain": self.chain,
            "system_mode": str(getattr(self.cfg, "system_mode", "")),
            "architecture_lock": bool(getattr(self.cfg, "architecture_lock", True)),
            "core_commands_immutable": bool(getattr(self.cfg, "core_commands_immutable", True)),
            "interactive_mode": bool(getattr(self.cfg, "interactive_mode", True)),
            "explanation_level": str(self.explanation_level),
            "counts": {
                "memory_items": int(self._memory.size()),
                "system_cycle": int(self.system_cycle),
                "conflicts_detected": int(self.conflicts_detected),
            },
            "last": {
                "ts": _safe_int(last.get("ts"), 0),
                "kind": str(last.get("kind") or ""),
                "level": str(last.get("level") or ""),
                "text": public_last_text,
            },
            "runtime": {
                "loop": dict(self._loop_state),
                "ws": dict(self._ws_state),
                "degraded": not all(bucket.get("ok", True) for bucket in (self._loop_state, self._ws_state)),
            },
            "llm": {
                "mode": str(getattr(self.cfg, "llm_mode", "template")),
                "provider": str(getattr(self.cfg, "llm_provider", "")),
                "model": str(getattr(self.cfg, "llm_model", "")),
                "last_error": str(self.last_llm_error or ""),
                "status": dict(self._llm_state),
            },
            "audit": self.audit.state(),
        }

    def _safe_cfg_snapshot(self) -> Dict[str, Any]:
        try:
            d = asdict(self.cfg)
        except (TypeError, ValueError):
            d = {}
        # Avoid logging secrets.
        return {
            "enabled": bool(d.get("enabled")),
            "interactive_mode": d.get("interactive_mode"),
            "require_admin_for_queries": d.get("require_admin_for_queries"),
            "max_narrative_memory": d.get("max_narrative_memory"),
            "persist_history": d.get("persist_history"),
            "explanation_level": d.get("explanation_level"),
            "conflict_mediation_enabled": d.get("conflict_mediation_enabled"),
            "emit_block_summaries": d.get("emit_block_summaries"),
            "llm_mode": d.get("llm_mode"),
            "llm_provider": d.get("llm_provider"),
            "llm_model": d.get("llm_model"),
        }
