from __future__ import annotations

ENGINE_TO_FAMILY = {
    "cross_cex_dex": "cross_cex_dex",
    "funding_arb": "funding_arb",
    "cross_chain_arb": "cross_chain_arb",
    "mev_search": "mev_search",
    "auto_strategy_generator": "auto_generated_strategy",
}


def family_for_engine(engine_type: str) -> str:
    return ENGINE_TO_FAMILY.get(str(engine_type), "flashloan_atomic")
