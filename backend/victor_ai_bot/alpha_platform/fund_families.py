from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class FundFamily:
    family: str
    income_stream: str
    alpha_type: str
    description: str
    capacity_curve: str
    regime_bias: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_fund_families() -> Dict[str, FundFamily]:
    return {
        'flash_arb': FundFamily('flash_arb', 'intraday_spread_capture', 'arbitrage', 'Atomic flash-loan spread capture.', 'steep_decay', ['balanced', 'high_volatility', 'gas_spike']),
        'funding_arb': FundFamily('funding_arb', 'carry_income', 'carry', 'Funding carry and basis capture.', 'moderate_decay', ['low_volatility', 'balanced']),
        'cex_dex_arb': FundFamily('cex_dex_arb', 'cross_venue_spread', 'arbitrage', 'Cross venue spot/perp routing.', 'moderate_decay', ['balanced', 'high_volatility']),
        'cex_cex_arb': FundFamily('cex_cex_arb', 'cross_exchange_spread', 'arbitrage', 'Cross exchange orderbook spread capture.', 'moderate_decay', ['balanced']),
        'liquidation_capture': FundFamily('liquidation_capture', 'liquidation_fee_income', 'tactical', 'Liquidation races and protected settlement.', 'steep_decay', ['bear', 'high_volatility']),
        'mev_search': FundFamily('mev_search', 'protected_execution_alpha', 'protective', 'Private/protected bundle and backrun opportunities.', 'steep_decay', ['high_volatility', 'balanced']),
        'volatility_market_making': FundFamily('volatility_market_making', 'spread_and_rebalance_income', 'market_making', 'Inventory-aware quoting and hedging.', 'capacity_bounded', ['balanced', 'low_volatility']),
        'stat_arb': FundFamily('stat_arb', 'mean_reversion', 'statistical', 'Cointegration and z-score driven reversion.', 'capacity_bounded', ['balanced', 'bear', 'bull']),
        'treasury_yield': FundFamily('treasury_yield', 'carry_income', 'yield', 'Treasury carry and stable deployment.', 'shallow_decay', ['low_volatility', 'balanced']),
    }
