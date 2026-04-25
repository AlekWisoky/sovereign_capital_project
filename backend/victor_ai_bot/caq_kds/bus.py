from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


_SAFE_UPDATE_EXCEPTIONS = (TypeError, ValueError)


@dataclass
class _Bucket:
    ts: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)


class MarketDataBus:
    """In-process market data bus (add-only).

    Motivation:
      - DecisionEngine is deliberately decoupled from RuntimeBundle.
      - We need a safe way for runtimes (DEX scanner, CEX adapters, MEV monitor, reliability)
        to publish summaries that can be fused into S_global for agents/strategies.

    Safety:
      - Purely additive: no mutations to core logic.
      - Bounded payload: callers should publish *summaries*, not full tick streams.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._buckets: Dict[str, _Bucket] = {}

    def update(self, bucket: str, data: Dict[str, Any], *, ts: Optional[float] = None) -> None:
        bucket = str(bucket or "").strip() or "default"
        now = float(ts if ts is not None else time.time())
        try:
            payload = dict(data or {})
        except _SAFE_UPDATE_EXCEPTIONS:
            payload = {}
        with self._lock:
            b = self._buckets.get(bucket) or _Bucket()
            b.data.update(payload)
            b.ts = now
            self._buckets[bucket] = b

    def publish(self, bucket: str, data: Dict[str, Any], *, ts: Optional[float] = None) -> None:
        self.update(bucket, data, ts=ts)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out: Dict[str, Any] = {}
            for k, b in self._buckets.items():
                out[k] = {"ts": float(b.ts), "data": dict(b.data or {})}
            return out


# Global singleton used across modules
BUS = MarketDataBus()
