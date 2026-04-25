from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .contracts import StrategyPodContract


class StrategyPodWorker:
    def __init__(self, *, pod_id: str, family: str, budget_usd: float):
        self.contract = StrategyPodContract(
            pod_id=pod_id, family=family, health="HEALTHY", budget_usd=float(budget_usd)
        )

    def produce(self, opportunities: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for x in opportunities:
            row = dict(x)
            row["podId"] = self.contract.pod_id
            row["family"] = row.get("family") or self.contract.family
            out.append(row)
        return out
