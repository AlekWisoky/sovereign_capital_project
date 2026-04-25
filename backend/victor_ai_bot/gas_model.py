from __future__ import annotations
from typing import Any, Dict, Mapping

# Conservative route-level gas model used for *ranking only*.
# Execution still uses estimateGas/simulation gates when enabled.

DEFAULT_FLASH_OVERHEAD = 180_000
DEFAULT_EXEC_OVERHEAD = 90_000

LEG_GAS_HEURISTICS = {
    "univ3": 120_000,  # fallback when quoter gas_estimate missing
    "curve": 160_000,
    "balancer": 200_000,
}

_SAFE_META_ACCESS_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_SEQUENCE_EXCEPTIONS = (TypeError, ValueError)
_SAFE_GAS_ESTIMATE_EXCEPTIONS = (TypeError, ValueError)


def estimate_route_gas_units(opportunity_meta: Dict[str, Any]) -> int:
    """Estimate gas units for a route using per-leg heuristics + UniV3 QuoterV2 gas estimates when present."""
    legs = []
    if isinstance(opportunity_meta, Mapping):
        try:
            # meta contains leg1/leg2/leg3 dicts from quoting
            for k in ("leg1", "leg2", "leg3"):
                leg_value = opportunity_meta.get(k)
                if isinstance(leg_value, Mapping):
                    legs.append(leg_value)
        except _SAFE_META_ACCESS_EXCEPTIONS:
            legs = []

    venues = []
    if isinstance(opportunity_meta, Mapping):
        try:
            venues = list(opportunity_meta.get("venues") or [])
        except _SAFE_SEQUENCE_EXCEPTIONS:
            venues = []

    total = DEFAULT_FLASH_OVERHEAD + DEFAULT_EXEC_OVERHEAD

    for idx, dex in enumerate(venues):
        dex = str(dex)
        leg_meta = legs[idx] if idx < len(legs) else {}
        if dex == "univ3":
            gas_est = None
            try:
                gas_est = int(leg_meta.get("gas_estimate") or 0)
            except _SAFE_GAS_ESTIMATE_EXCEPTIONS:
                gas_est = None
            if gas_est and gas_est > 40_000:
                total += int(gas_est)
            else:
                total += int(LEG_GAS_HEURISTICS.get("univ3", 120_000))
        else:
            total += int(LEG_GAS_HEURISTICS.get(dex, 160_000))
    return int(total)


def _gwei_to_wei(gwei: int) -> int:
    return int(gwei) * 1_000_000_000


def estimate_gas_cost_wei_from_cfg(cfg: Any, gas_units: int) -> int:
    """Estimate gas cost in wei based on configured gas preset max fee for current mode.

    Used only for ranking. Execution uses live gas suggestion.
    """
    mode = str(getattr(getattr(cfg, "execution", None), "gas_mode", "standard") or "standard")
    presets = getattr(getattr(cfg, "execution", None), "gas_presets", None)
    max_fee_gwei = 25
    if presets is not None:
        if mode == "fast":
            max_fee_gwei = int(getattr(presets, "fast_max_fee_gwei", max_fee_gwei))
        elif mode == "instant":
            max_fee_gwei = int(getattr(presets, "instant_max_fee_gwei", max_fee_gwei))
        else:
            max_fee_gwei = int(getattr(presets, "standard_max_fee_gwei", max_fee_gwei))
    return int(gas_units) * _gwei_to_wei(int(max_fee_gwei))
