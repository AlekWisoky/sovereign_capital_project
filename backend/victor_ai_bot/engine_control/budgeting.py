from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .models import EngineOpportunity


DEFAULT_BUDGETS = {
    "cross_cex_dex": {"max_opportunities": 12},
    "funding_arb": {"max_opportunities": 8},
    "cross_chain_arb": {"max_opportunities": 6},
    "mev_search": {"max_opportunities": 10},
    "auto_strategy_generator": {"max_opportunities": 5},
}


def apply_engine_budgets(
    opportunities: Iterable[EngineOpportunity], budgets: Dict[str, Dict[str, int]] | None = None
) -> List[EngineOpportunity]:
    budgets = budgets or DEFAULT_BUDGETS
    grouped: Dict[str, List[EngineOpportunity]] = defaultdict(list)
    for opp in opportunities:
        grouped[str(opp.engine_type)].append(opp)
    out: List[EngineOpportunity] = []
    for engine_type, rows in grouped.items():
        rows.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
        lim = int((budgets.get(engine_type) or {}).get("max_opportunities") or len(rows))
        out.extend(rows[:lim])
    out.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
    return out
