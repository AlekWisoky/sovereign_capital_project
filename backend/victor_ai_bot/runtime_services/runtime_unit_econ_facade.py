from __future__ import annotations

import os
from typing import Sequence

from ..usd_pricing import (
    format_usd_micro,
    gas_wei_to_token_wei,
    gas_wei_to_usd_micro,
    token_to_usd_micro,
)

_SAFE_UNIT_ECON_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeUnitEconFacade:
    """Compatibility facade for analytics-only unit-economics enrichment.

    This boundary preserves the legacy runtime semantics:
    - enrichment is optional and best-effort
    - operator UX data may be added to opportunities
    - core execution semantics are unaffected by failures here
    - typed local enrichment failures skip the affected opportunity
    """

    def _unit_econ_topn(self) -> int:
        try:
            topn = int(os.environ.get("VICTOR_USD_ACCOUNTING_TOPN", "25") or 25)
        except _SAFE_UNIT_ECON_EXCEPTIONS:
            topn = 25
        return max(0, min(200, int(topn)))

    async def _annotate_single_unit_econ(
        self,
        *,
        rpc,
        opportunity,
        current_block: int,
        preference: str,
    ) -> bool:
        try:
            profit_token = str(opportunity.route.legs[0].token_in)
            gross_profit = int(opportunity.expected_profit_raw or 0)
            meta = opportunity.meta if isinstance(opportunity.meta, dict) else {}
            gas_native = int(meta.get("gas_cost_estimate_wei") or 0)

            gas_in_profit = await gas_wei_to_token_wei(
                rpc,
                chain=self.cfg.chain,
                gas_cost_wei=int(gas_native),
                token_out=str(profit_token),
                block_number=int(current_block),
                cache=self.cache,
            )

            unit = meta.get("unit_econ") if isinstance(meta.get("unit_econ"), dict) else {}
            if gas_in_profit is not None:
                unit["gas_cost_in_profit_token_wei"] = str(int(gas_in_profit))
                if gross_profit > 0:
                    unit["profit_after_gas_in_profit_token_wei"] = str(
                        int(max(0, int(gross_profit) - int(gas_in_profit)))
                    )

            usd_gross = await token_to_usd_micro(
                rpc,
                chain=self.cfg.chain,
                token=str(profit_token),
                amount_wei=int(gross_profit),
                block_number=int(current_block),
                cache=self.cache,
                preference=str(preference),
            )
            usd_gas = await gas_wei_to_usd_micro(
                rpc,
                chain=self.cfg.chain,
                gas_cost_wei=int(gas_native),
                block_number=int(current_block),
                cache=self.cache,
                preference=str(preference),
            )
            if usd_gross is not None:
                opportunity.expected_profit_usd = format_usd_micro(int(usd_gross))
                unit["expected_profit_usd_micro"] = str(int(usd_gross))
            if usd_gas is not None:
                unit["gas_cost_usd_micro"] = str(int(usd_gas))
            if usd_gross is not None and usd_gas is not None:
                unit["profit_after_gas_usd_micro"] = str(
                    int(max(0, int(usd_gross) - int(usd_gas)))
                )

            if not isinstance(opportunity.meta, dict):
                opportunity.meta = {}
            opportunity.meta["unit_econ"] = unit
            return True
        except _SAFE_UNIT_ECON_EXCEPTIONS:
            return False

    async def _annotate_unit_economics(
        self,
        *,
        opps: Sequence[object],
        rpc,
        current_block: int,
    ) -> bool:
        try:
            if not bool(getattr(self.cfg.execution, "usd_accounting_enabled", False)) or not opps:
                return False
            usd_pref = str(getattr(self.cfg.execution, "usd_stable_preference", "usdc") or "usdc")
            for opportunity in list(opps[: self._unit_econ_topn()]):
                await self._annotate_single_unit_econ(
                    rpc=rpc,
                    opportunity=opportunity,
                    current_block=int(current_block),
                    preference=usd_pref,
                )
            return True
        except _SAFE_UNIT_ECON_EXCEPTIONS:
            return False
