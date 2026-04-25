from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..caq_kds.bus import BUS
from ..runtime_services.profitability_truth import inspect_profit_after_costs_truth
from ..profitability_projection import profitability_summary_projection


_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_INPUT_EXCEPTIONS = (AttributeError, IndexError, KeyError, TypeError, ValueError)
_SAFE_JSON_EXCEPTIONS = (TypeError, ValueError)
_SAFE_STORAGE_EXCEPTIONS = (OSError,)
_SAFE_LAST_EXCEPTIONS = (AttributeError, TypeError, ValueError)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return int(default)


@dataclass
class StrategyPlan:
    ok: bool
    chosen: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    ts: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "chosen": dict(self.chosen or {}),
            "candidates": list(self.candidates or []),
            "score": float(self.score),
            "ts": float(self.ts or 0.0),
        }


class StrategyPathPlanner:
    """Strategy Execution Graph (SEG) planner (Phase 16).

    We implement a conservative A*-style evaluation over a tiny discrete graph:
      node = (gas_mode, send_mode)

    Goal:
      maximize net EV while minimizing risk-adjusted execution costs.

    Important: Planner only recommends *overrides*; it never upsizes capital.
    """

    def __init__(self, *, data_dir: Optional[str] = None, chain: str = "global"):
        self.chain = str(chain or "global")
        self.root = canonical_data_dir(str(data_dir or "") or "backend/data")
        self._path = os.path.join(self.root, "superstructure", f"path_plan_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._last: StrategyPlan = StrategyPlan(ok=True, chosen={}, candidates=[], score=0.0, ts=time.time())
        self._bus_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_ts": 0.0,
        }
        self._storage_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_ts": 0.0,
        }
        self._input_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_field": "",
            "last_ts": 0.0,
        }

    def _mark_bucket(
        self,
        bucket: Dict[str, Any],
        *,
        ok: bool,
        code: str = "",
        error: str = "",
        action: str = "",
        field: str = "",
    ) -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")[:400]
        if "last_action" in bucket:
            bucket["last_action"] = str(action or "")
        if "last_field" in bucket:
            bucket["last_field"] = str(field or "")
        bucket["last_ts"] = float(time.time())

    def _runtime_state(self) -> Dict[str, Any]:
        buckets = (self._bus_state, self._storage_state, self._input_state)
        return {
            "bus": dict(self._bus_state),
            "storage": dict(self._storage_state),
            "inputs": dict(self._input_state),
            "degraded": not all(bool(bucket.get("ok", True)) for bucket in buckets),
        }

    def state(self) -> Dict[str, Any]:
        return self._runtime_state()

    def _snap(self) -> Dict[str, Any]:
        try:
            snap = BUS.snapshot()
            self._mark_bucket(self._bus_state, ok=True, action="snapshot")
            return snap if isinstance(snap, dict) else {}
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code="path_bus_snapshot_failed", error=str(exc), action="snapshot")
            return {}

    def _float_from_bus(self, bucket: str, field: str) -> float:
        snap = self._snap()
        try:
            data = (snap.get(bucket) or {}).get("data") or {}
            return float(data.get(field, 0.0) or 0.0)
        except _SAFE_INPUT_EXCEPTIONS as exc:
            self._mark_bucket(
                self._bus_state,
                ok=False,
                code=f"path_{bucket}_{field}_invalid",
                error=str(exc),
                action=bucket,
            )
            return 0.0

    def _mev_risk(self) -> float:
        return self._float_from_bus("mev", "sandwich_risk")

    def _vol_cluster(self) -> float:
        return self._float_from_bus("S_global", "vol_cluster")

    def _cost(self, *, gas_mode: str, send_mode: str, mev_risk: float, vol: float) -> float:
        # Heuristic cost units (lower is better).
        gm = str(gas_mode)
        sm = str(send_mode)
        gas_pen = {"standard": 1.0, "fast": 1.4, "instant": 1.9}.get(gm, 1.2)
        latency_pen = {"public": 0.7, "protected_rpc": 0.9, "private": 1.1}.get(sm, 1.0)
        mev_pen = float(mev_risk) * (1.2 if sm == "public" else 0.45)
        vol_pen = float(max(0.0, vol)) * 0.6
        return float(gas_pen + latency_pen + mev_pen + vol_pen)

    def _amount_in(self, opp: Any) -> int:
        try:
            route = getattr(opp, "route")
            legs = getattr(route, "legs")
            first_leg = legs[0]
            amount_in = int(getattr(first_leg, "amount_in", "0") or "0")
            self._mark_bucket(self._input_state, ok=True, field="amount_in")
            return amount_in
        except _SAFE_INPUT_EXCEPTIONS as exc:
            self._mark_bucket(self._input_state, ok=False, code="path_amount_in_invalid", error=str(exc), field="amount_in")
            return 0

    def _profit(self, opp: Any) -> int:
        projection = profitability_summary_projection(opp)
        amount = int(max(0, _safe_int(projection.get("displayProfitAfterCostsWeiInt") or 0)))
        reason = str(projection.get("reason") or "profit_after_costs_unavailable")
        if amount <= 0 and reason != "ok":
            self._mark_bucket(self._input_state, ok=False, code=f"path_{reason}", error=reason, field="profit_after_costs")
            return 0
        self._mark_bucket(self._input_state, ok=True, field="profit_after_costs")
        return amount

    def plan(self, *, opp: Any, current_gas_mode: str = "standard", current_send_mode: str = "public") -> StrategyPlan:
        ts = float(time.time())
        mev = float(self._mev_risk())
        vol = float(self._vol_cluster())

        # Profit proxy (bps) for scoring. Prefer profit_after_costs.
        amt_in = self._amount_in(opp)
        profit = self._profit(opp)
        ev_bps = 0.0
        if amt_in > 0:
            ev_bps = float((profit / float(amt_in)) * 10000.0)

        # Strategy Execution Graph nodes
        gas_modes = ["standard", "fast", "instant"]
        send_modes = ["public", "protected_rpc", "private"]

        candidates: List[Dict[str, Any]] = []
        best: Tuple[float, Dict[str, Any]] = (-1e18, {"gas_mode": current_gas_mode, "send_mode": current_send_mode})
        for gm in gas_modes:
            for sm in send_modes:
                cost = self._cost(gas_mode=gm, send_mode=sm, mev_risk=mev, vol=vol)
                # Score = EV - cost_weighted
                score = float(ev_bps - 8.0 * cost)
                # If mev risk high, strongly penalize public
                if mev >= 0.75 and sm == "public":
                    score -= 80.0
                # If EV is tiny, prefer standard gas
                if ev_bps <= 5.0 and gm != "standard":
                    score -= 20.0

                cand = {
                    "gas_mode": gm,
                    "send_mode": sm,
                    "score": float(score),
                    "ev_bps": float(ev_bps),
                    "cost": float(cost),
                    "mev_risk": float(mev),
                    "vol_cluster": float(vol),
                }
                candidates.append(cand)
                if score > best[0]:
                    best = (score, {"gas_mode": gm, "send_mode": sm})

        candidates_sorted = sorted(candidates, key=lambda x: float(x.get("score", -1e18)), reverse=True)[:9]
        chosen = best[1]
        plan = StrategyPlan(ok=True, chosen=chosen, candidates=candidates_sorted, score=float(best[0]), ts=ts)
        self._write(plan)
        self._last = plan
        try:
            BUS.update("path_plan", plan.as_dict())
            self._mark_bucket(self._bus_state, ok=True, action="publish")
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code="path_plan_publish_failed", error=str(exc), action="publish")
        return plan

    def _write_all(self, fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        written = 0
        while written < len(view):
            written += os.write(fd, view[written:])

    def _write(self, plan: StrategyPlan) -> None:
        rec = {"ts": float(plan.ts or time.time()), "chain": self.chain, "plan": plan.as_dict()}
        try:
            payload = (json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            try:
                self._write_all(fd, payload)
            finally:
                os.close(fd)
            self._mark_bucket(self._storage_state, ok=True, action="append")
        except (_SAFE_STORAGE_EXCEPTIONS + _SAFE_JSON_EXCEPTIONS) as exc:
            self._mark_bucket(self._storage_state, ok=False, code="path_plan_write_failed", error=str(exc), action="append")

    def last(self) -> Dict[str, Any]:
        try:
            last = self._last.as_dict()
        except _SAFE_LAST_EXCEPTIONS:
            return {"ok": False, "error": "path_last_failed", "runtime": self._runtime_state()}
        last["runtime"] = self._runtime_state()
        return last
