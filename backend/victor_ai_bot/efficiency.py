from __future__ import annotations
from dataclasses import dataclass
from typing import Deque
from collections import deque


@dataclass
class EfficiencyPoint:
    ts: int
    expected_after_costs_wei: int
    realized_after_gas_wei: int
    success: bool
    latency_ms: int


class EfficiencyTracker:
    def __init__(self, window: int = 50):
        self.points: Deque[EfficiencyPoint] = deque(maxlen=window)

    def add(self, p: EfficiencyPoint) -> None:
        self.points.append(p)

    def snapshot(self) -> dict:
        n = len(self.points)
        if n == 0:
            return {"n": 0, "efficiency_pct": 0.0, "success_rate_pct": 0.0, "latency_penalty": 0.0}
        exp = sum(x.expected_after_costs_wei for x in self.points)
        real = sum(x.realized_after_gas_wei for x in self.points)
        raw_eff = (real / exp * 100.0) if exp > 0 else 0.0
        succ = sum(1 for x in self.points if x.success) / n * 100.0
        avg_lat = sum(x.latency_ms for x in self.points) / n
        penalty = min(30.0, max(0.0, (avg_lat - 1000.0) / 100.0))
        eff_adj = max(0.0, raw_eff - penalty) * (succ / 100.0)
        return {
            "n": n,
            "efficiency_pct": round(eff_adj, 2),
            "raw_efficiency_pct": round(raw_eff, 2),
            "success_rate_pct": round(succ, 2),
            "avg_latency_ms": round(avg_lat, 1),
            "latency_penalty": round(penalty, 2),
        }
