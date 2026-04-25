from __future__ import annotations

from typing import Any, List

from ..arb_engine import find_three_leg_opportunities, find_two_leg_opportunities
from ..models import Opportunity
from .profitability_truth import opportunity_profit_sort_key


class RuntimePrimaryScanFacade:
    """Primary DEX loop-scan compatibility facade.

    This isolates the top-level two-leg / three-leg opportunity assembly from
    RuntimeBundle's scan loop while preserving current behavior:
    - no local swallowing of ordinary scan bugs
    - same discovery, scan, sort, and truncate semantics
    - no routing or execution-submission changes
    """

    async def _discover_extra_v3_pairs(self, rpc: Any, *, current_block: int) -> List[Any]:
        discovery = getattr(self, "_discovery", None)
        if discovery is None:
            return []
        pairs = await discovery.maybe_discover_univ3(rpc, self.cfg, int(current_block))
        return list(pairs or [])

    async def _scan_primary_opportunities(
        self,
        rpc: Any,
        *,
        current_block: int,
        amount_in: int,
    ) -> List[Opportunity]:
        if int(amount_in) <= 0:
            return []

        extra_v3_pairs = await self._discover_extra_v3_pairs(rpc, current_block=int(current_block))

        opps2: List[Opportunity] = []
        if bool(getattr(self.cfg.flags, "enable_two_leg_loops", True)):
            opps2 = await find_two_leg_opportunities(
                rpc,
                self.cfg,
                self.cache,
                current_block,
                amount_in=int(amount_in),
                slippage_bps=self.cfg.safety.slippage_bps,
                time_budget_ms=1500,
                max_opps=60,
                extra_v3_pairs=extra_v3_pairs,
            )

        opps3: List[Opportunity] = []
        if bool(
            getattr(self.cfg.flags, "enable_three_leg_loops", False)
            or getattr(self.cfg.flags, "enable_v3_triangular", False)
        ):
            opps3 = await find_three_leg_opportunities(
                rpc,
                self.cfg,
                self.cache,
                current_block,
                amount_in=int(amount_in),
                slippage_bps=self.cfg.safety.slippage_bps,
                time_budget_ms=1600,
                max_opps=40,
                extra_v3_pairs=extra_v3_pairs,
            )

        opps = list(opps2) + list(opps3)
        opps.sort(key=opportunity_profit_sort_key, reverse=True)
        return opps[:80]
