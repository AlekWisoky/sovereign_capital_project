
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Deque, Mapping
from collections import deque

from .bus import BUS


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_MAPPING_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)
_SAFE_AUDIT_EXCEPTIONS = (OSError, TypeError, ValueError)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default)


def _safe_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written <= 0:
            raise OSError('short_write')
        total += written


@dataclass
class DecisionExplanation:
    """CAQ-KDS Layer 4: Explainable AI decision record."""
    decision_id: str
    ts: float
    chain: str
    kind: str  # trade|arbitrage|mev_bundle|simulation
    mode: str  # auto|manual|dry_run|observe
    ok: bool

    tx_hash: str = ""
    opportunity_id: str = ""
    route_id: str = ""
    strategy: str = ""

    contributing_features: Dict[str, Any] = field(default_factory=dict)
    agent_signal_weights: Dict[str, float] = field(default_factory=dict)
    intrinsic_vs_extrinsic_ratio: float = 0.0
    risk_adjustment_factor: float = 1.0
    graph_context_used: Dict[str, Any] = field(default_factory=dict)
    funding_influence: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0

    outcome: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class DecisionAuditLog:
    """Append-only audit log with bounded in-memory cache."""

    def __init__(self, *, data_dir: str, chain: str = "global", max_cache: int = 500):
        root = str(data_dir or "") or os.path.join(os.getcwd(), "data")
        self.path = os.path.join(root, "caq_kds", f"decision_audit_{chain}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._cache: Deque[DecisionExplanation] = deque(maxlen=int(max_cache))
        self._by_id: Dict[str, DecisionExplanation] = {}
        self._state: Dict[str, Any] = {
            "append": {"ok": True, "path": self.path, "last_error_code": "", "last_error": "", "last_write_ts": 0.0},
            "degraded": False,
        }

    def _record_append(self, *, ok: bool, code: str = "", detail: str = "") -> None:
        append = self._state["append"]
        append["ok"] = bool(ok)
        append["last_error_code"] = str(code or "")
        append["last_error"] = str(detail or "")
        if ok:
            append["last_write_ts"] = float(time.time())
        self._state["degraded"] = not append["ok"]

    def log(self, expl: DecisionExplanation) -> str:
        self._cache.append(expl)
        self._by_id[expl.decision_id] = expl
        try:
            payload = json.dumps(expl.as_dict(), separators=(",", ":"), ensure_ascii=False) + "\n"
        except _SAFE_AUDIT_EXCEPTIONS as exc:
            self._record_append(ok=False, code="audit_serialize_failed", detail=repr(exc))
            return expl.decision_id
        fd: Optional[int] = None
        try:
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            _write_all(fd, payload.encode("utf-8"))
        except _SAFE_AUDIT_EXCEPTIONS as exc:
            self._record_append(ok=False, code="audit_append_failed", detail=repr(exc))
        else:
            self._record_append(ok=True)
        finally:
            if fd is not None:
                os.close(fd)
        return expl.decision_id

    def latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        n = int(limit)
        out = list(self._cache)[-n:]
        return [x.as_dict() for x in reversed(out)]

    def get(self, decision_id: str) -> Optional[Dict[str, Any]]:
        x = self._by_id.get(str(decision_id))
        if x:
            return x.as_dict()
        return None

    def state(self) -> Dict[str, Any]:
        return {"append": dict(self._state["append"]), "degraded": bool(self._state["degraded"])}


class XAIEngine:
    """Builds DecisionExplanation objects using available runtime metadata.

    Safe defaults:
      - Works even if only partial metadata is provided.
      - Never blocks execution.
    """

    def __init__(self, *, data_dir: str, chain: str):
        self.audit = DecisionAuditLog(data_dir=data_dir, chain=chain)

    def build(
        self,
        *,
        chain: str,
        kind: str,
        mode: str,
        ok: bool,
        tx_hash: str = "",
        route_id: str = "",
        opportunity_id: str = "",
        strategy: str = "",
        brain: Optional[Dict[str, Any]] = None,
        aqe_debug: Optional[Dict[str, Any]] = None,
        reward: Optional[Dict[str, Any]] = None,
        outcome: Optional[Dict[str, Any]] = None,
    ) -> DecisionExplanation:
        brain = dict(brain or {})
        aqe_debug = dict(aqe_debug or {})
        reward = dict(reward or {})
        outcome = dict(outcome or {})

        # contributing features: combine brain.features + agent feature logs (bounded)
        feats: Dict[str, Any] = {}
        features = _safe_mapping(brain.get("features"))
        if features:
            feats.update(features)
        af = aqe_debug.get("agent_features_used") or {}
        if isinstance(af, Mapping):
            feats["agent_features_used"] = {
                str(k): _safe_mapping(v) for k, v in list(af.items())[:20]
            }

        # agent signal weights: normalized abs(signal)*confidence
        weights: Dict[str, float] = {}
        sig = aqe_debug.get("agent_signals") or {}
        conf = aqe_debug.get("agent_confidence") or {}
        if isinstance(sig, Mapping) and isinstance(conf, Mapping):
            raw = {}
            for k, v in sig.items():
                w = abs(_safe_float(v)) * _clip(_safe_float(conf.get(k, 0.0)), 0.0, 1.0)
                raw[str(k)] = float(w)
            s = sum(raw.values()) or 1.0
            weights = {k: float(v / s) for k, v in raw.items()}

        # intrinsic/extrinsic ratio (from reward struct if present)
        r_team = _safe_float(reward.get("r_team", 0.0))
        r_intr = _safe_float(reward.get("r_intrinsic", 0.0))
        denom = abs(r_team) + abs(r_intr) + 1e-9
        ratio = float(abs(r_intr) / denom)

        # graph context: best-effort from aqe_debug (if state captured) else from bus snapshot
        graph_ctx: Dict[str, Any] = {}
        st = aqe_debug.get("state") or {}
        if isinstance(st, Mapping):
            graph_ctx = _safe_mapping(st.get("C_t"))
        if not graph_ctx:
            try:
                snap = BUS.snapshot()
                graph_ctx = _safe_mapping(_safe_mapping(snap.get("S_global")).get("context"))
            except _SAFE_BUS_EXCEPTIONS:
                graph_ctx = {}

        # funding influence (best-effort from bus)
        funding: Dict[str, Any] = {}
        try:
            snap = BUS.snapshot()
            cex = snap.get("cex") or {}
            if isinstance(cex, Mapping):
                funding = _safe_mapping(cex.get("funding"))
        except _SAFE_BUS_EXCEPTIONS:
            funding = {}

        # aggregate agent confidence weighted
        if weights:
            conf = aqe_debug.get("agent_confidence") or {}
            if isinstance(conf, Mapping):
                conf_score = sum(float(weights.get(k, 0.0)) * _clip(_safe_float(conf.get(k, 0.0)), 0.0, 1.0) for k in weights.keys())
            else:
                conf_score = 0.0
        else:
            conf_score = _clip(_safe_float(reward.get("confidence", 0.0)), 0.0, 1.0)

        # risk adjustment factor: if risk manager agent present, derive from its signal
        raf = 1.0
        sig = aqe_debug.get("agent_signals") or {}
        if isinstance(sig, Mapping):
            for k, v in sig.items():
                if "RiskManager" in str(k):
                    # risk signal in [-1,+1]; map to [0.5,1.5] but clip
                    raf = _clip(1.0 + 0.35 * _safe_float(v), 0.5, 1.5)
                    break

        expl = DecisionExplanation(
            decision_id=str(uuid.uuid4()),
            ts=float(time.time()),
            chain=str(chain),
            kind=str(kind),
            mode=str(mode),
            ok=bool(ok),
            tx_hash=str(tx_hash or ""),
            opportunity_id=str(opportunity_id or ""),
            route_id=str(route_id or ""),
            strategy=str(strategy or ""),
            contributing_features=feats,
            agent_signal_weights=weights,
            intrinsic_vs_extrinsic_ratio=float(ratio),
            risk_adjustment_factor=float(raf),
            graph_context_used=graph_ctx,
            funding_influence=funding,
            confidence_score=float(_clip(conf_score, 0.0, 1.0)),
            outcome=outcome,
        )
        return expl


# Per-chain engines are created lazily by callers
_ENGINES: Dict[str, XAIEngine] = {}


def engine(*, data_dir: str, chain: str) -> XAIEngine:
    k = str(chain or "global")
    if k not in _ENGINES:
        _ENGINES[k] = XAIEngine(data_dir=data_dir, chain=k)
    return _ENGINES[k]

