"""Latency profiling utilities (observability-only).

Design goals:
- Additive: does not alter execution semantics.
- Low overhead: small fixed-size windows, O(n log n) percentile snapshot.
- Safety: latency metrics MUST NOT be used for decisions.

We track stage timings for execution (gas/calldata/estimate/safety/simulate/sign/send)
and end-to-end paths (proposal->submit, submit->receipt).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import time


def _ms(ns: int) -> float:
    return float(ns) / 1_000_000.0


@dataclass
class LatencySpan:
    """A single timing span with named stage marks."""

    _t0_ns: int = 0
    _last_ns: int = 0
    _marks: Dict[str, int] = None  # type: ignore

    def __post_init__(self) -> None:
        now = time.perf_counter_ns()
        self._t0_ns = now
        self._last_ns = now
        self._marks = {"start": now}

    def mark(self, name: str) -> None:
        now = time.perf_counter_ns()
        self._marks[str(name)] = now
        self._last_ns = now

    def stages_ms(self) -> Dict[str, float]:
        # Compute deltas between marks. Ordering is insertion order.
        keys = list(self._marks.keys())
        out: Dict[str, float] = {}
        prev_key = "start"
        prev = self._marks.get(prev_key, self._t0_ns)
        for k in keys:
            if k == "start":
                continue
            t = self._marks.get(k, prev)
            out[f"{prev_key}->{k}"] = _ms(int(t - prev))
            prev_key = k
            prev = t
        out["total"] = _ms(int(self._last_ns - self._t0_ns))
        return out


class RollingLatency:
    """Rolling percentile stats over a bounded window."""

    def __init__(self, *, window: int = 400):
        self.window = max(20, min(2000, int(window)))
        self._values: List[float] = []

    def add(self, value_ms: float) -> None:
        try:
            v = float(value_ms)
        except (TypeError, ValueError):
            return
        if v < 0:
            return
        self._values.append(v)
        if len(self._values) > self.window:
            self._values = self._values[-self.window :]

    def snapshot(self) -> Dict[str, float]:
        if not self._values:
            return {"count": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0, "last": 0.0}
        xs = sorted(self._values)
        n = len(xs)

        def q(p: float) -> float:
            if n == 1:
                return float(xs[0])
            idx = int(round((n - 1) * p))
            idx = max(0, min(n - 1, idx))
            return float(xs[idx])

        return {
            "count": float(n),
            "p50": q(0.50),
            "p90": q(0.90),
            "p99": q(0.99),
            "last": float(self._values[-1]),
        }


class LatencyProfiler:
    """Tracks multiple rolling latency series."""

    def __init__(self, *, window: int = 400):
        self.window = int(window)
        self._series: Dict[str, RollingLatency] = {}

    def add(self, name: str, value_ms: float) -> None:
        key = str(name)
        s = self._series.get(key)
        if s is None:
            s = RollingLatency(window=self.window)
            self._series[key] = s
        s.add(value_ms)

    def get(self, name: str) -> Dict[str, float]:
        s = self._series.get(str(name))
        return (
            s.snapshot()
            if s is not None
            else {"count": 0.0, "p50": 0.0, "p90": 0.0, "p99": 0.0, "last": 0.0}
        )

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {k: v.snapshot() for k, v in self._series.items()}
