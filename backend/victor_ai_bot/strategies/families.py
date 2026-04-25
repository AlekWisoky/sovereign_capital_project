from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class StrategyFamily:
    family: str
    assumptions: List[str]
    preferred_regimes: List[str]
    disallowed_regimes: List[str]
    risk_profile: str
    capital_cap_pct: float
    execution_sensitivity: str
    confidence_requirement: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CATALOG: Dict[str, StrategyFamily] = {
    "flashloan_atomic": StrategyFamily(
        "flashloan_atomic",
        ["atomic settlement", "pool depth available"],
        ["balanced", "high_volatility", "gas_spike"],
        ["low_liquidity"],
        "core",
        55.0,
        "high",
        0.55,
    ),
    "liquidation_anticipation": StrategyFamily(
        "liquidation_anticipation",
        ["liquidation queues visible", "close-to-threshold positions"],
        ["high_volatility", "bear"],
        ["low_volatility"],
        "satellite",
        15.0,
        "very_high",
        0.62,
    ),
    "oracle_drift": StrategyFamily(
        "oracle_drift",
        ["price source divergence", "bounded oracle lag"],
        ["high_volatility", "bear", "bull"],
        [],
        "satellite",
        12.0,
        "high",
        0.60,
    ),
    "liquidity_migration": StrategyFamily(
        "liquidity_migration",
        ["flow between venues", "cross-pool inventory rotation"],
        ["bull", "balanced", "low_volatility"],
        ["gas_spike"],
        "satellite",
        10.0,
        "medium",
        0.52,
    ),
    "volatility_event_overlay": StrategyFamily(
        "volatility_event_overlay",
        ["event-driven spread expansion"],
        ["high_volatility", "bull", "bear"],
        ["low_volatility"],
        "satellite",
        8.0,
        "very_high",
        0.64,
    ),
    "flash_arb": StrategyFamily(
        "flash_arb",
        ["atomic settlement", "loan fee recovered after gas and mev"],
        ["balanced", "high_volatility", "gas_spike"],
        ["low_liquidity"],
        "core",
        36.0,
        "very_high",
        0.70,
    ),
    "cex_dex_arb": StrategyFamily(
        "cex_dex_arb",
        ["inventory on cex and dex", "settlement friction bounded"],
        ["balanced", "bull"],
        ["gas_spike"],
        "satellite",
        14.0,
        "high",
        0.62,
    ),
    "cex_cex_arb": StrategyFamily(
        "cex_cex_arb",
        ["inventory on multiple cex venues"],
        ["balanced"],
        ["gas_spike"],
        "satellite",
        14.0,
        "high",
        0.60,
    ),
    "liquidation_capture": StrategyFamily(
        "liquidation_capture",
        ["at-risk collateral exists", "private routing or speed edge available"],
        ["bear", "high_volatility"],
        ["low_volatility"],
        "tactical",
        12.0,
        "very_high",
        0.72,
    ),
    "volatility_market_making": StrategyFamily(
        "volatility_market_making",
        ["inventory controls active", "quote skew bounded"],
        ["balanced", "low_volatility"],
        ["high_volatility"],
        "tactical",
        10.0,
        "medium",
        0.58,
    ),
    "stat_arb": StrategyFamily(
        "stat_arb",
        ["cointegrated pairs remain stable", "hedge legs available"],
        ["balanced", "bull", "bear"],
        [],
        "satellite",
        10.0,
        "medium",
        0.60,
    ),
    "treasury_yield": StrategyFamily(
        "treasury_yield",
        ["stable carry deployment"],
        ["low_volatility", "balanced"],
        ["high_volatility"],
        "reserve",
        22.0,
        "low",
        0.50,
    ),
    "cross_cex_dex": StrategyFamily(
        "cross_cex_dex",
        ["inventory on cex and dex", "settlement friction bounded"],
        ["balanced", "low_volatility", "bull"],
        ["gas_spike"],
        "satellite",
        14.0,
        "high",
        0.60,
    ),
    "funding_arb": StrategyFamily(
        "funding_arb",
        ["funding dispersion available", "hedge legs remain collateral efficient"],
        ["balanced", "bull", "bear"],
        [],
        "satellite",
        18.0,
        "medium",
        0.62,
    ),
    "cross_chain_arb": StrategyFamily(
        "cross_chain_arb",
        ["prepositioned inventory", "bridge and finality risk bounded"],
        ["balanced", "bull"],
        ["high_volatility", "gas_spike"],
        "experimental",
        6.0,
        "very_high",
        0.72,
    ),
    "mev_search": StrategyFamily(
        "mev_search",
        ["private routing available", "defensive posture preserved"],
        ["high_volatility", "balanced"],
        ["low_volatility"],
        "satellite",
        8.0,
        "very_high",
        0.68,
    ),
    "auto_generated_strategy": StrategyFamily(
        "auto_generated_strategy",
        ["generated under governance bounds", "sandbox/paper validated"],
        ["balanced", "high_volatility", "low_volatility"],
        [],
        "experimental",
        4.0,
        "medium",
        0.70,
    ),
}


def family_for(strategy_name: str) -> StrategyFamily:
    return CATALOG.get(str(strategy_name), CATALOG["flashloan_atomic"])
