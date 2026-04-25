from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from ..caq_kds.bus import BUS


_SAFE_BUS_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)
_SAFE_WRITE_EXCEPTIONS: Tuple[type[BaseException], ...] = (OSError, TypeError, ValueError)
_SAFE_SNAPSHOT_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, TypeError, ValueError)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, float(x))))


def _entropy(ps: List[float]) -> float:
    # Shannon entropy; ps must sum to 1
    e = 0.0
    for p in ps:
        if p <= 0.0:
            continue
        e -= float(p) * math.log(float(p) + 1e-12)
    return float(e)


@dataclass
class StabilitySnapshot:
    ok: bool
    ts: float
    window_s: float
    negotiation_rate_per_min: float
    conflict_rate_per_min: float
    rejection_rate: float
    capital_fragmentation: float
    coordination_entropy: float
    instability_score: float
    tripped: bool
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "ts": float(self.ts),
            "window_s": float(self.window_s),
            "negotiation_rate_per_min": float(self.negotiation_rate_per_min),
            "conflict_rate_per_min": float(self.conflict_rate_per_min),
            "rejection_rate": float(self.rejection_rate),
            "capital_fragmentation": float(self.capital_fragmentation),
            "coordination_entropy": float(self.coordination_entropy),
            "instability_score": float(self.instability_score),
            "tripped": bool(self.tripped),
            "meta": dict(self.meta or {}),
        }


def _write_all(fd: int, payload: bytes) -> None:
    written = 0
    while written < len(payload):
        n = os.write(fd, payload[written:])
        if n <= 0:
            raise OSError('stability_write_incomplete')
        written += n


class OrgStabilityMonitor:
    """Reliability & organizational stability monitor (Phase 18).

    Tracks:
      - agent coordination entropy (proxy: selected proposal kinds/agents)
      - negotiation frequency
      - conflict frequency
      - proposal rejection rate
      - capital fragmentation index

    If instability is detected, the superstructure can degrade to safe mode.
    """

    def __init__(self, *, data_dir: str, chain: str, window_s: float = 600.0):
        self.chain = str(chain or "global")
        self.root = canonical_data_dir(str(data_dir or '') or 'backend/data')
        self._path = os.path.join(self.root, "superstructure", f"stability_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self.window_s = float(max(60.0, float(window_s or 600.0)))

        self._events: Deque[Dict[str, Any]] = deque(maxlen=5000)
        self._last: StabilitySnapshot = StabilitySnapshot(
            ok=True,
            ts=time.time(),
            window_s=self.window_s,
            negotiation_rate_per_min=0.0,
            conflict_rate_per_min=0.0,
            rejection_rate=0.0,
            capital_fragmentation=0.0,
            coordination_entropy=0.0,
            instability_score=0.0,
            tripped=False,
            meta={},
        )
        self._bus_state: Dict[str, Any] = {
            'ok': True,
            'last_error_code': '',
            'last_error': '',
            'last_ts': 0,
        }
        self._storage_state: Dict[str, Any] = {
            'ok': True,
            'last_error_code': '',
            'last_error': '',
            'path': self._path,
            'last_ts': 0,
        }
        self._snapshot_state: Dict[str, Any] = {
            'ok': True,
            'last_error_code': '',
            'last_error': '',
            'last_ts': 0,
        }

    def _mark_bucket(
        self,
        bucket: Dict[str, Any],
        *,
        ok: bool,
        code: str = '',
        error: str = '',
        **extra: Any,
    ) -> None:
        bucket['ok'] = bool(ok)
        bucket['last_error_code'] = str(code or '')
        bucket['last_error'] = str(error or '')
        bucket['last_ts'] = int(time.time())
        if extra:
            bucket.update(extra)

    def state(self) -> Dict[str, Any]:
        return {
            'bus': dict(self._bus_state),
            'storage': dict(self._storage_state),
            'snapshot': dict(self._snapshot_state),
            'degraded': bool(
                (not bool(self._bus_state.get('ok', True)))
                or (not bool(self._storage_state.get('ok', True)))
                or (not bool(self._snapshot_state.get('ok', True)))
            ),
        }


    def record(self, kind: str, payload: Dict[str, Any]) -> None:
        self._events.append({"ts": float(time.time()), "kind": str(kind), "payload": dict(payload or {})})

    def compute(self, *, trip_threshold: float = 0.75) -> StabilitySnapshot:
        now = float(time.time())
        window_start = now - self.window_s
        evs = [e for e in list(self._events) if float(e.get("ts", 0.0)) >= window_start]
        n_neg = sum(1 for e in evs if e.get("kind") == "negotiation")
        n_conf = sum(1 for e in evs if e.get("kind") == "conflict")
        n_rej = sum(1 for e in evs if e.get("kind") == "rejection")
        n_total = max(1, n_neg + n_rej)
        rej_rate = float(n_rej / float(n_total))
        neg_rate = float(n_neg / (self.window_s / 60.0))
        conf_rate = float(n_conf / (self.window_s / 60.0))

        # Coordination entropy proxy from selected agent ids + kinds
        labels: List[str] = []
        for e in evs:
            if e.get("kind") != "negotiation":
                continue
            p = (e.get("payload") or {})
            sel = (p.get("selected") or {})
            if isinstance(sel, dict):
                labels.append(str(sel.get("agent_id") or ""))
                labels.append(str(sel.get("kind") or ""))
        ent = 0.0
        if labels:
            counts: Dict[str, int] = {}
            for l in labels:
                counts[l] = counts.get(l, 0) + 1
            total = float(sum(counts.values()) or 1.0)
            ps = [float(v) / total for v in counts.values()]
            ent = float(_entropy(ps))
            # normalize to [0,1] using log(K)
            k = max(2, len(ps))
            ent = float(ent / (math.log(float(k)) + 1e-12))

        # Capital fragmentation proxy: last seen allocation frag
        frag = 0.0
        for e in reversed(evs):
            if e.get("kind") == "capital":
                frag = float((e.get("payload") or {}).get("fragmentation_index", 0.0) or 0.0)
                break

        # Instability score (bounded) — conservative.
        # Penalties:
        #   - entropy collapse or explosion
        #   - high conflict frequency
        #   - high rejection rate
        #   - high capital fragmentation
        #   - very high negotiation churn
        target_ent = 0.60
        ent_pen = _clip(abs(ent - target_ent) / target_ent)
        conf_pen = _clip(conf_rate / 6.0)          # 6 conflicts/min is severe
        rej_pen = _clip(rej_rate / 0.50)           # 50% rejection is severe
        frag_pen = _clip(frag / 0.70)              # 0.7 fragmentation is high
        churn_pen = _clip(neg_rate / 12.0)         # 12 negotiations/min is severe

        instability = _clip(0.25 * ent_pen + 0.20 * conf_pen + 0.20 * rej_pen + 0.15 * frag_pen + 0.20 * churn_pen)
        tripped = bool(instability >= float(trip_threshold))

        snap = StabilitySnapshot(
            ok=True,
            ts=now,
            window_s=self.window_s,
            negotiation_rate_per_min=float(neg_rate),
            conflict_rate_per_min=float(conf_rate),
            rejection_rate=float(rej_rate),
            capital_fragmentation=float(frag),
            coordination_entropy=float(ent),
            instability_score=float(instability),
            tripped=tripped,
            meta={
                "ent_pen": float(ent_pen),
                "conf_pen": float(conf_pen),
                "rej_pen": float(rej_pen),
                "frag_pen": float(frag_pen),
                "churn_pen": float(churn_pen),
            },
        )

        self._last = snap
        self._mark_bucket(self._snapshot_state, ok=True)
        self._write(snap)
        try:
            BUS.update('org_stability', snap.as_dict())
            self._mark_bucket(self._bus_state, ok=True)
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code='stability_bus_publish_failed', error=str(exc))
        return snap

    def _write(self, snap: StabilitySnapshot) -> None:
        rec = {'ts': float(snap.ts), 'chain': self.chain, 'stability': snap.as_dict()}
        fd = -1
        try:
            payload = json.dumps(rec, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\n'
            fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            _write_all(fd, payload)
            self._mark_bucket(self._storage_state, ok=True, path=self._path)
        except _SAFE_WRITE_EXCEPTIONS as exc:
            self._mark_bucket(self._storage_state, ok=False, code='stability_write_failed', error=str(exc), path=self._path)
        finally:
            if fd >= 0:
                os.close(fd)

    def last(self) -> Dict[str, Any]:
        try:
            snap = self._last.as_dict()
            self._mark_bucket(self._snapshot_state, ok=True)
            snap['runtime'] = self.state()
            return snap
        except _SAFE_SNAPSHOT_EXCEPTIONS as exc:
            self._mark_bucket(self._snapshot_state, ok=False, code='stability_last_failed', error=str(exc))
            return {'ok': False, 'error': 'stability_last_failed', 'runtime': self.state()}
