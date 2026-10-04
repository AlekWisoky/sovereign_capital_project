from __future__ import annotations
from typing import Any, Dict, Mapping

from .ethabi import enc_bytes_dyn, enc_uint, selector

# Conservative route-level gas model used for *ranking only*.
# Execution still uses estimateGas/simulation gates when enabled.

DEFAULT_FLASH_OVERHEAD = 180_000
DEFAULT_EXEC_OVERHEAD = 90_000

LEG_GAS_HEURISTICS = {
    "univ3": 120_000,  # fallback when quoter gas_estimate missing
    "curve": 160_000,
    "balancer": 200_000,
    "aerodrome": 140_000,
    "slipstream": 165_000,
    "camelot_algebra": 170_000,
    "camelot_v2": 125_000,
    "constant_product": 125_000,
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


def select_consensus_gas_price(
    observations: list[dict[str, object]],
    *,
    max_block_lag: int = 2,
    agreement_ratio: float = 0.25,
) -> dict[str, object]:
    """Select a fail-closed gas-price consensus from cross-provider observations."""
    valid: list[dict[str, object]] = []
    anomalies: list[dict[str, object]] = []
    for raw in list(observations or []):
        try:
            price = int(raw.get("gas_price_wei") or 0)
            block = int(raw.get("block_number"))
        except (AttributeError, TypeError, ValueError):
            anomalies.append(dict(raw))
            continue
        if price <= 0 or block < 0:
            anomalies.append({**dict(raw), "reason": "invalid_observation"})
            continue
        valid.append({**dict(raw), "gas_price_wei": price, "block_number": block})

    if not valid:
        return {"gas_price_wei": None, "status": "insufficient_agreement", "observations": [], "anomalies": anomalies}

    max_block = max(int(item["block_number"]) for item in valid)
    fresh: list[dict[str, object]] = []
    for item in valid:
        if max_block - int(item["block_number"]) <= max(0, int(max_block_lag)):
            fresh.append(item)
        else:
            anomalies.append({**item, "reason": "stale_block"})

    if len(fresh) < 2:
        return {"gas_price_wei": None, "status": "insufficient_agreement", "observations": fresh, "anomalies": anomalies}

    prices = sorted(int(item["gas_price_wei"]) for item in fresh)
    median = prices[len(prices) // 2] if len(prices) % 2 else (prices[len(prices) // 2 - 1] + prices[len(prices) // 2]) // 2
    if median <= 0:
        return {"gas_price_wei": None, "status": "insufficient_agreement", "observations": fresh, "anomalies": anomalies}

    def close(price: int) -> bool:
        return abs(price - median) / float(median) <= max(0.0, float(agreement_ratio))

    inliers = [item for item in fresh if close(int(item["gas_price_wei"]))]
    if len(inliers) >= 2:
        consensus_prices = sorted(int(item["gas_price_wei"]) for item in inliers)
        consensus = consensus_prices[len(consensus_prices) // 2]
        for item in fresh:
            if item not in inliers:
                ratio = max(int(item["gas_price_wei"]), consensus) / float(max(1, min(int(item["gas_price_wei"]), consensus)))
                anomalies.append({**item, "reason": "gas_price_outlier", "ratio_to_consensus": ratio})
        return {
            "gas_price_wei": int(consensus),
            "status": "consensus",
            "observations": fresh,
            "inliers": inliers,
            "anomalies": anomalies,
        }

    return {
        "gas_price_wei": None,
        "status": "insufficient_agreement",
        "observations": fresh,
        "anomalies": anomalies,
    }


BASE_CHAIN_ID = 8453
BASE_GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"


async def estimate_base_l1_fee_wei(
    rpc: Any,
    calldata_hex: str,
    *,
    block: str = "latest",
) -> int | None:
    """Query Base's canonical GasPriceOracle for the exact calldata L1 fee."""
    if not isinstance(calldata_hex, str) or not calldata_hex.startswith("0x"):
        return None
    try:
        raw = bytes.fromhex(calldata_hex[2:])
    except (TypeError, ValueError):
        return None
    if not raw:
        return None

    # getL1Fee(bytes): selector + ABI dynamic-bytes argument.
    data = selector("getL1Fee(bytes)") + enc_uint(32) + enc_bytes_dyn(raw)
    result = await rpc.eth_call(
        BASE_GAS_PRICE_ORACLE,
        "0x" + data.hex(),
        block=block,
    )
    if not getattr(result, "ok", False) or not isinstance(getattr(result, "result", None), str):
        return None
    try:
        fee = int(str(result.result), 16)
    except (TypeError, ValueError):
        return None
    return fee if fee >= 0 else None


def _gwei_to_wei(gwei: int) -> int:
    return int(gwei) * 1_000_000_000


def estimate_gas_cost_wei_from_cfg(
    cfg: Any,
    gas_units: int,
    *,
    observed_gas_price_wei: int | None = None,
) -> int:
    """Estimate expected gas cost in wei for read-only economic ranking.

    An observed network gas price represents expected cost; the configured
    max-fee preset is a submission ceiling and must not be treated as expected
    cost. When no live price is available, retain the conservative fallback.
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
    if observed_gas_price_wei is not None:
        try:
            observed = max(0, int(observed_gas_price_wei))
        except (TypeError, ValueError):
            observed = 0
        if observed > 0:
            return int(gas_units) * observed
    return int(gas_units) * _gwei_to_wei(int(max_fee_gwei))
