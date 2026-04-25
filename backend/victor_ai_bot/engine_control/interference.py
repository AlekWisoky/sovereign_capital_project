from __future__ import annotations

from typing import Iterable, List, Set, Tuple

from .models import EngineOpportunity


def apply_interference_controls(
    opportunities: Iterable[EngineOpportunity],
) -> List[EngineOpportunity]:
    seen: Set[Tuple[str, str, str]] = set()
    out: List[EngineOpportunity] = []
    for opp in sorted(
        list(opportunities),
        key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)),
    ):
        key = (str(opp.strategy_family), str(opp.route_family), "|".join(sorted(set(opp.venues))))
        if key in seen:
            continue
        seen.add(key)
        out.append(opp)
    return out
