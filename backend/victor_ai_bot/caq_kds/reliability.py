
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .bus import BUS


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_STATE_EXCEPTIONS = (OSError, TypeError, ValueError, json.JSONDecodeError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default)


def _write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, indent=2))
    os.replace(tmp, path)


@dataclass
class ReliabilityState:
    ts: float = 0.0
    n: int = 0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    signal_accuracy: float = 0.0
    exploration_efficiency: float = 0.0
    joint_entropy_mean: float = 0.0
    joint_entropy_std: float = 0.0
    strategy_stability: float = 0.0
    reliability: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ts": float(self.ts),
            "n": int(self.n),
            "sharpe": float(self.sharpe),
            "sortino": float(self.sortino),
            "max_drawdown": float(self.max_drawdown),
            "signal_accuracy": float(self.signal_accuracy),
            "exploration_efficiency": float(self.exploration_efficiency),
            "joint_entropy_mean": float(self.joint_entropy_mean),
            "joint_entropy_std": float(self.joint_entropy_std),
            "strategy_stability": float(self.strategy_stability),
            "reliability": float(self.reliability),
            "extra": dict(self.extra or {}),
        }


class PerformanceQuantifier:
    """CAQ-KDS Layer 5: Performance quantification and reliability engine.

    Inputs:
      - trade outcomes (from DecisionEngine training log rows)
      - optional SMMAE debug fields (entropy, novelty, explore flag)

    Output:
      - rolling metrics + reliability score
      - publishes summary to MarketDataBus under key 'reliability'
    """

    def __init__(self, *, data_dir: str, chain: str, window: int = 200):
        self.data_dir = str(data_dir or "") or os.path.join(os.getcwd(), "data")
        self.chain = str(chain or "global")
        self.window = int(window)
        self._rets: List[float] = []
        self._ok: List[int] = []
        self._entropy: List[float] = []
        self._explore: List[int] = []
        self._explore_ret: List[float] = []
        self._exploit_ret: List[float] = []
        self._last_state = ReliabilityState()
        self._state_path = os.path.join(self.data_dir, "caq_kds", f"reliability_{self.chain}.json")
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        self._status: Dict[str, Any] = {
            "state_load": {"ok": True, "path": self._state_path, "last_error_code": "", "last_error": ""},
            "state_save": {"ok": True, "path": self._state_path, "last_error_code": "", "last_error": "", "last_write_ts": 0.0},
            "bus_publish": {"ok": True, "last_error_code": "", "last_error": "", "last_publish_ts": 0.0},
            "degraded": False,
        }
        self._load_state()

    def _refresh_degraded(self) -> None:
        self._status["degraded"] = not all(bucket.get("ok", True) for key, bucket in self._status.items() if key != "degraded")

    def _record_status(self, bucket: str, *, ok: bool, code: str = "", detail: str = "") -> None:
        entry = self._status[bucket]
        entry["ok"] = bool(ok)
        entry["last_error_code"] = str(code or "")
        entry["last_error"] = str(detail or "")
        if ok and bucket in {"state_save", "bus_publish"}:
            ts_key = "last_write_ts" if bucket == "state_save" else "last_publish_ts"
            entry[ts_key] = float(time.time())
        self._refresh_degraded()

    def _load_state(self) -> None:
        if not os.path.exists(self._state_path):
            self._record_status("state_load", ok=True)
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            self._last_state = ReliabilityState(
                ts=float(obj.get("ts", 0.0)),
                n=int(obj.get("n", 0)),
                sharpe=float(obj.get("sharpe", 0.0)),
                sortino=float(obj.get("sortino", 0.0)),
                max_drawdown=float(obj.get("max_drawdown", 0.0)),
                signal_accuracy=float(obj.get("signal_accuracy", 0.0)),
                exploration_efficiency=float(obj.get("exploration_efficiency", 0.0)),
                joint_entropy_mean=float(obj.get("joint_entropy_mean", 0.0)),
                joint_entropy_std=float(obj.get("joint_entropy_std", 0.0)),
                strategy_stability=float(obj.get("strategy_stability", 0.0)),
                reliability=float(obj.get("reliability", 0.0)),
                extra=dict(obj.get("extra") or {}),
            )
        except _SAFE_STATE_EXCEPTIONS as exc:
            self._record_status("state_load", ok=False, code="reliability_state_load_failed", detail=repr(exc))
            return
        self._record_status("state_load", ok=True)

    def _persist_state(self, st: ReliabilityState) -> None:
        try:
            _write_json_atomic(self._state_path, st.as_dict())
        except _SAFE_STATE_EXCEPTIONS as exc:
            self._record_status("state_save", ok=False, code="reliability_state_save_failed", detail=repr(exc))
            return
        self._record_status("state_save", ok=True)

    def _max_drawdown(self, xs: List[float]) -> float:
        # compute on cumulative sum of returns
        peak = 0.0
        cur = 0.0
        mdd = 0.0
        for r in xs:
            cur += float(r)
            peak = max(peak, cur)
            dd = peak - cur
            mdd = max(mdd, dd)
        # normalize by |peak| + 1 to keep bounded-ish
        denom = abs(peak) + 1.0
        return float(mdd / denom)

    def _sharpe(self, xs: List[float]) -> float:
        if len(xs) < 8:
            return 0.0
        mu = sum(xs) / len(xs)
        var = sum((x - mu) ** 2 for x in xs) / max(1, (len(xs) - 1))
        sd = math.sqrt(var) or 1e-9
        # per-trade sharpe scaled by sqrt(n)
        return float((mu / sd) * math.sqrt(len(xs)))

    def _sortino(self, xs: List[float]) -> float:
        if len(xs) < 8:
            return 0.0
        mu = sum(xs) / len(xs)
        downs = [min(0.0, x) for x in xs]
        var = sum((d - (sum(downs) / len(downs))) ** 2 for d in downs) / max(1, (len(downs) - 1))
        sd = math.sqrt(var) or 1e-9
        return float((mu / sd) * math.sqrt(len(xs)))

    def observe(self, *, row: Dict[str, Any]) -> ReliabilityState:
        # compute normalized return ratio
        amt = _f(row.get("amount_in_wei", 0.0))
        realized = _f(row.get("realized_after_gas_wei", 0.0))
        ok = bool(row.get("ok", False))
        ret = 0.0
        if amt > 0:
            ret = float(realized) / float(amt)
        # bound extreme outliers
        ret = float(_clip(ret, -5.0, 5.0))

        self._rets.append(ret)
        self._ok.append(1 if ok else 0)

        extra = row.get("extra") or {}
        aqe_dbg = {}
        if isinstance(extra, dict):
            aqe_dbg = extra.get("aqe_debug") or {}
        ent = 0.0
        explore = 0
        if isinstance(aqe_dbg, dict):
            ent = _f(aqe_dbg.get("joint_entropy", 0.0))
            explore = 1 if bool(aqe_dbg.get("explore", False)) else 0

        self._entropy.append(ent)
        self._explore.append(explore)
        if explore:
            self._explore_ret.append(ret)
        else:
            self._exploit_ret.append(ret)

        # enforce window
        for arr in (self._rets, self._ok, self._entropy, self._explore):
            if len(arr) > self.window:
                del arr[0 : len(arr) - self.window]
        for arr in (self._explore_ret, self._exploit_ret):
            if len(arr) > self.window:
                del arr[0 : len(arr) - self.window]

        xs = list(self._rets)
        sharpe = self._sharpe(xs)
        sortino = self._sortino(xs)
        mdd = self._max_drawdown(xs)
        acc = sum(self._ok) / max(1, len(self._ok))

        # strategy stability: prefer low variance and positive mean
        mu = sum(xs) / max(1, len(xs))
        var = sum((x - mu) ** 2 for x in xs) / max(1, (len(xs) - 1))
        sd = math.sqrt(var) if var > 0 else 0.0
        stability = 1.0 - _clip(sd / (abs(mu) + 1e-6), 0.0, 1.0)

        ent_mu = sum(self._entropy) / max(1, len(self._entropy))
        ent_var = sum((e - ent_mu) ** 2 for e in self._entropy) / max(1, (len(self._entropy) - 1))
        ent_sd = math.sqrt(ent_var) if ent_var > 0 else 0.0

        # exploration efficiency: compare explore vs exploit returns (bounded)
        ex_mu = sum(self._explore_ret) / max(1, len(self._explore_ret)) if self._explore_ret else 0.0
        ep_mu = sum(self._exploit_ret) / max(1, len(self._exploit_ret)) if self._exploit_ret else 0.0
        eff = 0.0
        denom = abs(ep_mu) + 1e-6
        eff = _clip(ex_mu / denom, -2.0, 2.0)
        eff_norm = _clip((eff + 2.0) / 4.0, 0.0, 1.0)

        # Reliability score
        perf = _clip((acc * 0.6 + _clip(sharpe / 3.0, 0.0, 1.0) * 0.4) * stability, 0.0, 1.0)
        entropy_stab = 1.0 - _clip(ent_sd / (abs(ent_mu) + 1e-6), 0.0, 1.0)
        dd_control = 1.0 - _clip(mdd / 0.35, 0.0, 1.0)
        graph_conf = 0.5
        try:
            snap = BUS.snapshot()
            kds = (snap.get('kds') or {}).get('data') if isinstance(snap.get('kds'), dict) else {}
            if isinstance(kds, dict):
                graph_conf = float(kds.get('last_conf', graph_conf) or graph_conf)
        except _SAFE_BUS_EXCEPTIONS:
            graph_conf = float(graph_conf)
        rel = _clip(0.45 * perf + 0.20 * entropy_stab + 0.25 * dd_control + 0.10 * graph_conf, 0.0, 1.0)

        st = ReliabilityState(
            ts=float(time.time()),
            n=int(len(xs)),
            sharpe=float(sharpe),
            sortino=float(sortino),
            max_drawdown=float(mdd),
            signal_accuracy=float(acc),
            exploration_efficiency=float(eff_norm),
            joint_entropy_mean=float(ent_mu),
            joint_entropy_std=float(ent_sd),
            strategy_stability=float(stability),
            reliability=float(rel),
            extra={"mean_return": float(mu), "std_return": float(sd)},
        )
        self._last_state = st
        self._persist_state(st)

        # Publish to bus (add-only)
        try:
            BUS.publish("reliability", st.as_dict())
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._record_status("bus_publish", ok=False, code="reliability_publish_failed", detail=repr(exc))
        else:
            self._record_status("bus_publish", ok=True)

        return st

    def state(self) -> Dict[str, Any]:
        out = self._last_state.as_dict()
        out["storage"] = {
            "state_load": dict(self._status["state_load"]),
            "state_save": dict(self._status["state_save"]),
            "bus_publish": dict(self._status["bus_publish"]),
            "degraded": bool(self._status["degraded"]),
        }
        return out


_TRACKERS: Dict[str, PerformanceQuantifier] = {}


def tracker(*, data_dir: str, chain: str) -> PerformanceQuantifier:
    k = str(chain or "global")
    if k not in _TRACKERS:
        _TRACKERS[k] = PerformanceQuantifier(data_dir=data_dir, chain=k)
    return _TRACKERS[k]

