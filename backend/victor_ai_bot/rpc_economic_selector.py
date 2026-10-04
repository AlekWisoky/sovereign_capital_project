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
    observed_after_cost_return_bps: float = -1e18
    successful_quote_edge_count: int = 0
    successful_quote_pool_count: int = 0
    successful_quote_pair_count: int = 0
    operational_score: float = 0.0
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
        int(evidence.profit_after_costs_usd_micro) if int(evidence.profit_after_costs_usd_micro) > 0 else 0,
        int(evidence.profitable_opportunity_count),
        float(evidence.observed_after_cost_return_bps),
        float(evidence.quote_success_rate),
        int(evidence.successful_quote_edge_count),
        int(evidence.successful_quote_pool_count),
        int(evidence.successful_quote_pair_count),
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
    eligible = [item for item in candidates if item.economically_eligible]
    ordered = sorted(eligible, key=_selection_key, reverse=True)
    selected = ordered[0] if ordered else None
    return selected, ordered
