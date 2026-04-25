from __future__ import annotations

from typing import Any, Dict, Tuple


def _safe_str(x: Any) -> str:
    try:
        return str(x)
    except (TypeError, ValueError):
        return ""


def classify_opportunity_income(opp: Any) -> Tuple[str, str, str]:
    """Derive (strategy_type, income_stream, venue_path) from an Opportunity-like object.

    This is intentionally heuristic and deterministic.
    It is used for:
      - clarifying stream of income (reporting/analytics)
      - BI dataset categorization

    Returns:
      strategy_type: e.g. dex_flash_2leg, dex_flash_3leg, unknown
      income_stream: e.g. flash_arb, funding, cex_arb, yield, other
      venue_path: e.g. uniswapv3->uniswapv3
    """

    strat = _safe_str(getattr(opp, "strategy", "") or "")
    venue_path = ""
    if ":" in strat:
        venue_path = strat.split(":", 1)[1]
    else:
        venue_path = strat

    st = "unknown"
    if strat.startswith("two-leg") or strat.startswith("two_leg") or "two-leg" in strat:
        st = "dex_flash_2leg"
    elif strat.startswith("three-leg") or strat.startswith("three_leg") or "three-leg" in strat:
        st = "dex_flash_3leg"
    elif "funding" in strat or "perp" in strat:
        st = "funding_arb"
    elif "cex" in strat or "cross" in strat or "spread" in strat:
        st = "cex_spread_arb"
    elif "yield" in strat or "lending" in strat:
        st = "yield"

    stream = "other"
    if st.startswith("dex_flash") or "flash" in strat or "arb" in strat:
        # Most on-chain arb in this codebase is flashloan-centric.
        stream = "flash_arb"
    if st.startswith("funding") or "funding" in strat:
        stream = "funding"
    if st.startswith("cex") or "cex" in strat:
        stream = "cex_arb"
    if st == "yield":
        stream = "yield"

    return st, stream, venue_path
