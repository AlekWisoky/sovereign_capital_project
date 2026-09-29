from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RpcEconomicEvidence:
    endpoint: str
    provider: str
    profit_after_costs_usd_micro: int
    profitable_opportunity_count: int
    quote_requests: int
    quote_successes: int
    operational_score: float
    block_number: int | None = None
    scan_latency_ms: float = 0.0
    healthy: bool = True
    quote_quarantined: bool = False

    @property
    def quote_success_rate(self) -> float:
        return (
            float(self.quote_successes) / float(self.quote_requests)
            if self.quote_requests > 0
            else 0.0
        )

    @property
    def economically_eligible(self) -> bool:
        return bool(self.healthy and not self.quote_quarantined)


def _selection_key(evidence: RpcEconomicEvidence) -> tuple:
    return (
        1 if evidence.economically_eligible else 0,
        int(evidence.profit_after_costs_usd_micro),
        int(evidence.profitable_opportunity_count),
        float(evidence.quote_success_rate),
        -float(evidence.operational_score),
        str(evidence.endpoint),
    )


def select_best_rpc_evidence(
    evidence: Iterable[RpcEconomicEvidence],
) -> tuple[RpcEconomicEvidence | None, list[RpcEconomicEvidence]]:
    """Select the best read RPC from read-only economic quote evidence.

    Canonical after-fee USD profitability is the primary economic signal.
    Operational health/score remains a hard eligibility gate and a deterministic
    tie-breaker when no provider has a better economic result.
    """
    candidates = list(evidence)
    ordered = sorted(candidates, key=_selection_key, reverse=True)
    selected = ordered[0] if ordered else None
    return selected, ordered
