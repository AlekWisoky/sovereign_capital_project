from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class AlphaClassification:
    family: str
    alpha_type: str
    holding_horizon: str
    liquidity_sensitivity: str
    capital_intensity: str
    execution_sensitivity: str
    regime_preference: List[str]
    engine_type: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_alpha_classifications() -> Dict[str, AlphaClassification]:
    return {
        'flashloan_atomic': AlphaClassification('flashloan_atomic', 'arbitrage', 'intraday', 'high', 'medium', 'high', ['balanced', 'high_volatility'], 'execution_capture'),
        'cross_cex_dex': AlphaClassification('cross_cex_dex', 'arbitrage', 'intraday', 'high', 'high', 'high', ['balanced', 'high_volatility'], 'cross_cex_dex'),
        'funding_arb': AlphaClassification('funding_arb', 'carry', 'multi_hour', 'medium', 'high', 'medium', ['balanced', 'low_volatility'], 'funding_arb'),
        'cross_chain_arb': AlphaClassification('cross_chain_arb', 'rebalancing', 'multi_hour', 'medium', 'high', 'high', ['balanced'], 'cross_chain_arb'),
        'mev_search': AlphaClassification('mev_search', 'protective', 'sub_block', 'high', 'medium', 'very_high', ['high_volatility', 'balanced'], 'mev_search'),
        'flash_arb': AlphaClassification('flash_arb', 'arbitrage', 'sub_block', 'high', 'high', 'very_high', ['high_volatility', 'balanced', 'gas_spike'], 'execution_capture'),
        'cex_dex_arb': AlphaClassification('cex_dex_arb', 'arbitrage', 'intraday', 'high', 'high', 'high', ['balanced', 'high_volatility'], 'cross_cex_dex'),
        'cex_cex_arb': AlphaClassification('cex_cex_arb', 'arbitrage', 'intraday', 'medium', 'high', 'high', ['balanced'], 'cross_exchange_engine'),
        'liquidation_capture': AlphaClassification('liquidation_capture', 'tactical', 'sub_block', 'high', 'medium', 'very_high', ['bear', 'high_volatility'], 'liquidation_engine'),
        'volatility_market_making': AlphaClassification('volatility_market_making', 'tactical', 'continuous', 'medium', 'high', 'medium', ['balanced', 'low_volatility'], 'market_making'),
        'stat_arb': AlphaClassification('stat_arb', 'generated', 'intraday', 'medium', 'medium', 'medium', ['balanced', 'bull', 'bear'], 'stat_arb'),
        'treasury_yield': AlphaClassification('treasury_yield', 'carry', 'multi_day', 'low', 'low', 'low', ['low_volatility', 'balanced'], 'treasury_yield'),
        'auto_generated_strategy': AlphaClassification('auto_generated_strategy', 'generated', 'mixed', 'mixed', 'low', 'mixed', ['balanced', 'bull', 'bear'], 'auto_strategy_generator'),
    }
