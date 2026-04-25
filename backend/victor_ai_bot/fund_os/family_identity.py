from __future__ import annotations

from typing import Any, Dict, Iterable, List


_FAMILY_IDENTITY_TABLE: dict[str, dict[str, Any]] = {
    "flash_arb": {
        "launchFamily": "flash_arb",
        "runtimeFamily": "flashloan_atomic",
        "capitalFamily": "flashloan_atomic",
        "displayName": "Flash Arbitrage",
        "aliases": ["flash_arb", "flashloan_atomic"],
        "isCore": True,
    },
    "funding_arb": {
        "launchFamily": "funding_arb",
        "runtimeFamily": "funding_arb",
        "capitalFamily": "funding_arb",
        "displayName": "Funding Arbitrage",
        "aliases": ["funding_arb"],
        "isCore": False,
    },
    "cex_cex_arb": {
        "launchFamily": "cex_cex_arb",
        "runtimeFamily": "cex_cex_arb",
        "capitalFamily": "cex_cex_arb",
        "displayName": "CEX-CEX Arbitrage",
        "aliases": ["cex_cex_arb"],
        "isCore": False,
    },
    "cex_dex_arb": {
        "launchFamily": "cex_dex_arb",
        "runtimeFamily": "cross_cex_dex",
        "capitalFamily": "cross_cex_dex",
        "displayName": "CEX-DEX Arbitrage",
        "aliases": ["cex_dex_arb", "cross_cex_dex"],
        "isCore": False,
    },
    "liquidation_capture": {
        "launchFamily": "liquidation_capture",
        "runtimeFamily": "liquidation_capture",
        "capitalFamily": "liquidation_anticipation",
        "displayName": "Liquidation Capture",
        "aliases": ["liquidation_capture", "liquidation_anticipation"],
        "isCore": False,
    },
    "mev_search": {
        "launchFamily": "mev_search",
        "runtimeFamily": "mev_search",
        "capitalFamily": "mev_search",
        "displayName": "MEV Search",
        "aliases": ["mev_search"],
        "isCore": False,
    },
    "stat_arb": {
        "launchFamily": "stat_arb",
        "runtimeFamily": "stat_arb",
        "capitalFamily": "stat_arb",
        "displayName": "Statistical Arbitrage",
        "aliases": ["stat_arb"],
        "isCore": False,
    },
    "volatility_market_making": {
        "launchFamily": "volatility_market_making",
        "runtimeFamily": "volatility_market_making",
        "capitalFamily": "volatility_market_making",
        "displayName": "Volatility Market Making",
        "aliases": ["volatility_market_making", "market_making"],
        "isCore": False,
    },
    "treasury_yield": {
        "launchFamily": "treasury_yield",
        "runtimeFamily": "treasury_yield",
        "capitalFamily": "treasury_yield",
        "displayName": "Treasury Yield",
        "aliases": ["treasury_yield"],
        "isCore": False,
    },
    "auto_strategy_generator": {
        "launchFamily": "auto_strategy_generator",
        "runtimeFamily": "auto_generated_strategy",
        "capitalFamily": "auto_generated_strategy",
        "displayName": "Auto Strategy Generator",
        "aliases": ["auto_strategy_generator", "auto_generated_strategy"],
        "isCore": False,
    },
}

_ALIAS_TO_LAUNCH: dict[str, str] = {}
for _launch_family, _info in _FAMILY_IDENTITY_TABLE.items():
    for _alias in list(_info.get("aliases") or []):
        alias_s = str(_alias or "")
        if alias_s:
            _ALIAS_TO_LAUNCH[alias_s] = _launch_family
    _ALIAS_TO_LAUNCH[_launch_family] = _launch_family
    runtime = str(_info.get("runtimeFamily") or "")
    capital = str(_info.get("capitalFamily") or "")
    if runtime:
        _ALIAS_TO_LAUNCH[runtime] = _launch_family
    if capital:
        _ALIAS_TO_LAUNCH[capital] = _launch_family


def canonical_launch_family_id(family: str) -> str:
    family_s = str(family or "")
    return _ALIAS_TO_LAUNCH.get(family_s, family_s)



def family_identity(family: str) -> Dict[str, Any]:
    launch_family = canonical_launch_family_id(family)
    base = dict(_FAMILY_IDENTITY_TABLE.get(launch_family) or {})
    if not base:
        return {
            "requestedFamily": str(family or ""),
            "launchFamily": launch_family,
            "runtimeFamily": launch_family,
            "capitalFamily": launch_family,
            "displayName": launch_family.replace("_", " ").title(),
            "aliases": [launch_family] if launch_family else [],
            "isCore": False,
        }
    return {
        "requestedFamily": str(family or ""),
        "launchFamily": launch_family,
        "runtimeFamily": str(base.get("runtimeFamily") or launch_family),
        "capitalFamily": str(base.get("capitalFamily") or launch_family),
        "displayName": str(base.get("displayName") or launch_family.replace("_", " ").title()),
        "aliases": list(base.get("aliases") or [launch_family]),
        "isCore": bool(base.get("isCore", False)),
    }



def family_alias_candidates(families: str | Iterable[str]) -> List[str]:
    raw_values = [families] if isinstance(families, str) else list(families or [])
    out: List[str] = []
    for raw in raw_values:
        info = family_identity(str(raw or ""))
        for value in [
            str(raw or ""),
            str(info.get("launchFamily") or ""),
            str(info.get("runtimeFamily") or ""),
            str(info.get("capitalFamily") or ""),
            *[str(x or "") for x in list(info.get("aliases") or [])],
        ]:
            if value and value not in out:
                out.append(value)
    return out



def family_matches(*, family: str, candidate: str) -> bool:
    candidate_s = str(candidate or "")
    return bool(candidate_s) and candidate_s in family_alias_candidates(family)



def is_core_launch_family(family: str) -> bool:
    return bool(family_identity(family).get("isCore", False))
