from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from .bus import BUS
from .knowledge_graph import GRAPH


_SAFE_STATE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_IO_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _h(s: str) -> str:
    return hashlib.blake2b(s.encode("utf-8", errors="ignore"), digest_size=6).hexdigest()


@dataclass
class Hypothesis:
    id: str
    ts: float
    chain: str
    pattern: str
    description: str
    patch: Dict[str, Any] = field(default_factory=dict)
    budget: float = 0.0
    trials: int = 0
    success: int = 0
    avg_r: float = 0.0
    status: str = "temp"
    confidence: float = 0.0
    last_update: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfEvolutionEngine:
    """CAQ-KDS Layer 6: Self-improving knowledge discovery loop."""

    def __init__(self, *, data_dir: str, chain: str):
        self.data_dir = str(data_dir or "") or os.path.join(os.getcwd(), "data")
        self.chain = str(chain or "global")
        self.enabled = bool(os.environ.get("VICTOR_CAQ_KDS_SELF_EVOLUTION", "").strip() == "1")
        self.max_active = int(os.environ.get("VICTOR_KDS_MAX_ACTIVE", "6"))
        self.min_trials = int(os.environ.get("VICTOR_KDS_MIN_TRIALS", "6"))
        self.promote_avg_r = float(os.environ.get("VICTOR_KDS_PROMOTE_AVG_R", "0.010"))
        self.promote_winrate = float(os.environ.get("VICTOR_KDS_PROMOTE_WINRATE", "0.60"))
        self.budget_B = float(os.environ.get("VICTOR_KDS_GLOBAL_BUDGET", "1.0"))
        self.max_budget_per = float(os.environ.get("VICTOR_KDS_MAX_BUDGET_PER", "0.35"))
        self._active: Dict[str, Hypothesis] = {}
        self._last_hypothesis_id = ""
        self._promotions_path = os.path.join(self.data_dir, "caq_kds", f"promoted_strategies_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._promotions_path), exist_ok=True)
        self._status: Dict[str, Any] = {
            "promotion_log": {"ok": True, "path": self._promotions_path, "last_error_code": "", "last_error": "", "last_write_ts": 0.0},
            "graph_update": {"ok": True, "last_error_code": "", "last_error": "", "last_update_ts": 0.0},
            "bus_publish": {"ok": True, "last_error_code": "", "last_error": "", "last_publish_ts": 0.0},
            "degraded": False,
        }

    def _refresh_degraded(self) -> None:
        self._status["degraded"] = not all(bucket.get("ok", True) for key, bucket in self._status.items() if key != "degraded")

    def _record_status(self, bucket: str, *, ok: bool, code: str = "", detail: str = "") -> None:
        entry = self._status[bucket]
        entry["ok"] = bool(ok)
        entry["last_error_code"] = str(code or "")
        entry["last_error"] = str(detail or "")
        now = float(time.time())
        if bucket == "promotion_log" and ok:
            entry["last_write_ts"] = now
        elif bucket == "graph_update":
            entry["last_update_ts"] = now
        elif bucket == "bus_publish" and ok:
            entry["last_publish_ts"] = now
        self._refresh_degraded()

    def _publish_bus(self, payload: Dict[str, Any]) -> None:
        try:
            BUS.publish("kds", payload)
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._record_status("bus_publish", ok=False, code="kds_publish_failed", detail=repr(exc))
            return
        self._record_status("bus_publish", ok=True)

    def _record_graph_hypothesis(self, *, hypothesis_id: str, regime: str, key: str, budget: float, score: float, status: str = "temp") -> None:
        try:
            GRAPH.upsert_node(node_id=hypothesis_id, node_type="hypothesis", attrs={"pattern": key, "budget": budget, "status": status}, ts=time.time())
            if regime:
                GRAPH.upsert_node(node_id=f"regime:{regime}", node_type="regime", attrs={}, ts=time.time())
                GRAPH.upsert_edge(src=f"regime:{regime}", dst=hypothesis_id, rel="hypothesis_of", weight=float(score), ts=time.time())
        except _SAFE_STATE_EXCEPTIONS as exc:
            self._record_status("graph_update", ok=False, code="kds_graph_update_failed", detail=repr(exc))
            return
        self._record_status("graph_update", ok=True)

    def _write_promotion_record(self, rec: Dict[str, Any]) -> None:
        line = json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n"
        try:
            fd = os.open(self._promotions_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(line)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._record_status("promotion_log", ok=False, code="kds_promotion_log_failed", detail=repr(exc))
            return
        self._record_status("promotion_log", ok=True)

    def _anomaly_score(self, state: Dict[str, Any]) -> float:
        S = state.get("S_global") or {}
        feats = (S.get("features") if isinstance(S, dict) else {}) or {}
        mr = float(feats.get("local.margin_ratio", state.get("margin_ratio", 0.0)) or 0.0)
        gr = float(feats.get("local.gas_ratio", state.get("gas_ratio", 0.0)) or 0.0)
        legs = float(feats.get("local.legs", state.get("legs", 2) or 2))
        mev_r = float(feats.get("mev.sandwich_risk", 0.0) or 0.0)
        vol = float(feats.get("local.vol_proxy", 0.0) or 0.0)
        rel = float(feats.get("rel.reliability", 0.0) or 0.0)
        novelty = 0.0
        C_t = state.get("C_t") or {}
        if isinstance(C_t, dict):
            try:
                novelty = float(C_t.get("novelty", 0.0) or 0.0)
            except _SAFE_STATE_EXCEPTIONS:
                novelty = 0.0

        score = 0.0
        score += _clip(abs(mr) * 18.0, 0.0, 1.0) * 0.30
        score += _clip(gr * 6.0, 0.0, 1.0) * 0.10
        score += _clip((legs - 2.0) / 2.0, 0.0, 1.0) * 0.10
        score += _clip(mev_r, 0.0, 1.0) * 0.20
        score += _clip(vol, 0.0, 1.0) * 0.10
        score += _clip(1.0 - rel, 0.0, 1.0) * 0.20
        score += _clip(novelty, 0.0, 1.0) * 0.10
        return float(_clip(score, 0.0, 1.0))

    def _propose_patch(self, state: Dict[str, Any]) -> Dict[str, Any]:
        S = state.get("S_global") or {}
        feats = (S.get("features") if isinstance(S, dict) else {}) or {}
        mr = float(feats.get("local.margin_ratio", state.get("margin_ratio", 0.0)) or 0.0)
        mev_r = float(feats.get("mev.sandwich_risk", 0.0) or 0.0)
        rel = float(feats.get("rel.reliability", 0.0) or 0.0)

        patch: Dict[str, Any] = {"safety": {}, "execution": {}}
        if mev_r >= 0.55:
            patch["execution"]["send_mode"] = "protected_rpc"
            patch["execution"]["mev"] = {"enabled": True, "mode": "defensive", "refuse_public_send_on_high_risk": True}
        if abs(mr) >= 0.02 and rel < 0.45:
            patch["safety"]["minProfitBps"] = 12
            patch["safety"]["require_simulation"] = True
        if rel >= 0.70 and abs(mr) >= 0.015:
            patch["execution"]["gas_mode"] = "fast"
            patch["execution"]["max_submit_per_block"] = 1
        patch["safety"]["slippage_bps"] = int(_clip(float(feats.get("local.slippage_bps", 45.0) or 45.0), 20.0, 90.0))
        patch["execution"]["auto_trading"] = False
        return patch

    def tick(self, *, state: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None
        score = self._anomaly_score(state)
        if score < 0.72:
            return None

        S = state.get("S_global") or {}
        regime = str(S.get("regime") or "") if isinstance(S, dict) else ""
        key = f"{regime}|mr:{round(float(state.get('margin_ratio', 0.0)), 3)}|legs:{int(state.get('legs', 2))}"
        pid = f"hyp_{int(time.time())}_{_h(key)}"
        if len(self._active) >= self.max_active:
            return None

        patch = self._propose_patch(state)
        bud = float(min(self.max_budget_per, self.budget_B * score))
        if "high_vol" in regime:
            bud = float(min(bud, 0.12))
        hypothesis = Hypothesis(
            id=pid,
            ts=float(time.time()),
            chain=self.chain,
            pattern=key,
            description=f"Anomaly score {round(score, 3)} in regime={regime}; test bounded patch",
            patch=patch,
            budget=float(bud),
            trials=0,
            success=0,
            avg_r=0.0,
            status="temp",
            confidence=float(score),
            last_update=float(time.time()),
        )
        self._active[pid] = hypothesis
        self._last_hypothesis_id = pid

        self._record_graph_hypothesis(hypothesis_id=pid, regime=regime, key=key, budget=float(bud), score=float(score), status="temp")
        self._publish_bus({"active": len(self._active), "last_id": pid, "last_conf": float(score), "explore_budget": float(bud)})
        return pid

    def observe(self, *, hypothesis_id: str, ok: bool, r_total: float) -> None:
        if not (self.enabled and hypothesis_id):
            return
        hypothesis = self._active.get(str(hypothesis_id))
        if not hypothesis or hypothesis.status != "temp":
            return

        hypothesis.trials += 1
        if ok:
            hypothesis.success += 1
        alpha = 0.25
        hypothesis.avg_r = float((1 - alpha) * float(hypothesis.avg_r) + alpha * float(r_total))
        hypothesis.last_update = float(time.time())
        win = float(hypothesis.success) / max(1, int(hypothesis.trials))
        hypothesis.confidence = float(_clip((win * 0.55 + _clip(hypothesis.avg_r / 0.02, 0.0, 1.0) * 0.45) * _clip(hypothesis.trials / self.min_trials, 0.0, 1.0), 0.0, 1.0))

        if hypothesis.trials >= self.min_trials:
            if win >= self.promote_winrate and hypothesis.avg_r >= self.promote_avg_r:
                self._promote(hypothesis, winrate=win)
            else:
                hypothesis.status = "decayed"
                self._record_graph_hypothesis(hypothesis_id=hypothesis.id, regime="", key=hypothesis.pattern, budget=float(hypothesis.budget), score=float(hypothesis.confidence), status="decayed")
                self._active.pop(hypothesis.id, None)

        self._publish_bus({"active": len(self._active), "last_id": hypothesis.id, "last_conf": float(hypothesis.confidence), "explore_budget": float(hypothesis.budget)})

    def _promote(self, hypothesis: Hypothesis, *, winrate: float) -> None:
        hypothesis.status = "promoted"
        record = {
            "ts": int(time.time()),
            "chain": self.chain,
            "id": hypothesis.id,
            "description": hypothesis.description,
            "patch": hypothesis.patch,
            "stats": {"trials": hypothesis.trials, "winrate": float(winrate), "avg_r": float(hypothesis.avg_r)},
        }
        self._write_promotion_record(record)
        try:
            sid = f"strategy:{_h(hypothesis.pattern)}"
            GRAPH.upsert_node(node_id=sid, node_type="strategy", attrs={"source": "kds_promotion", "patch": hypothesis.patch}, ts=time.time())
            GRAPH.upsert_edge(src=hypothesis.id, dst=sid, rel="promoted_to", weight=float(hypothesis.confidence), ts=time.time())
        except _SAFE_STATE_EXCEPTIONS as exc:
            self._record_status("graph_update", ok=False, code="kds_promotion_graph_failed", detail=repr(exc))
        else:
            self._record_status("graph_update", ok=True)
        self._active.pop(hypothesis.id, None)

    def state(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "active": [item.as_dict() for item in list(self._active.values())[:50]],
            "active_count": int(len(self._active)),
            "last_hypothesis_id": str(self._last_hypothesis_id),
            "storage": {
                "promotion_log": dict(self._status["promotion_log"]),
                "graph_update": dict(self._status["graph_update"]),
                "bus_publish": dict(self._status["bus_publish"]),
                "degraded": bool(self._status["degraded"]),
            },
            "graph": GRAPH.state(),
        }


_ENGINES: Dict[str, SelfEvolutionEngine] = {}


def engine(*, data_dir: str, chain: str) -> SelfEvolutionEngine:
    key = str(chain or "global")
    if key not in _ENGINES:
        _ENGINES[key] = SelfEvolutionEngine(data_dir=data_dir, chain=key)
    return _ENGINES[key]
