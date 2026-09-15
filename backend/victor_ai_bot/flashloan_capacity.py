from __future__ import annotations

import math
import re
from typing import Any

from .flashloan_providers import normalize_flashloan_provider


_BALANCE_OF_SELECTOR = "70a08231"
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _address_word(address: str) -> str:
    if not _ADDRESS_RE.fullmatch(address):
        raise ValueError("invalid_asset_address")
    return "0x" + ("0" * 24) + address[2:].lower()


def provider_address_from_config(cfg: Any, provider: object) -> str:
    """Resolve the configured on-chain flash-loan provider contract."""
    normalized = normalize_flashloan_provider(provider)
    if normalized == "aave":
        address = getattr(getattr(cfg, "chain", cfg), "aave_v3_pool", "")
    elif normalized == "balancer":
        address = getattr(getattr(cfg, "chain", cfg), "balancer_vault", "")
    else:
        raise ValueError(f"unsupported_flashloan_provider:{normalized or 'missing'}")
    address = str(address or "")
    if not _ADDRESS_RE.fullmatch(address):
        raise ValueError(f"provider_address_missing_or_invalid:{normalized or 'missing'}")
    return address


async def observe_flashloan_asset_capacity(
    rpc: Any,
    *,
    provider: object,
    asset: str,
    provider_address: str,
    block: str = "latest",
) -> dict[str, Any]:
    """Observe provider-held raw asset liquidity without inferring USD value.

    The observation is deliberately a lower-level fact: ERC-20 balance held by
    the canonical provider contract at the requested block. It is not a claim
    that every unit is executable if provider-specific reserve/configuration
    controls reject the flash-loan. Callers must retain those provider checks.
    """
    normalized = normalize_flashloan_provider(provider)
    if normalized not in {"aave", "balancer"}:
        return {
            "ok": False,
            "provider": normalized,
            "asset": asset,
            "raw_available": None,
            "capacity_usd": None,
            "reason_code": f"unsupported_flashloan_provider:{normalized or 'missing'}",
        }
    if not _ADDRESS_RE.fullmatch(str(asset or "")):
        return {
            "ok": False,
            "provider": normalized,
            "asset": str(asset or ""),
            "raw_available": None,
            "capacity_usd": None,
            "reason_code": "invalid_asset_address",
        }
    if not _ADDRESS_RE.fullmatch(str(provider_address or "")):
        return {
            "ok": False,
            "provider": normalized,
            "asset": asset,
            "raw_available": None,
            "capacity_usd": None,
            "reason_code": "provider_address_missing_or_invalid",
        }

    data = "0x" + _BALANCE_OF_SELECTOR + _address_word(asset)[2:]
    result = await rpc.eth_call(provider_address, data, block=block)
    if not getattr(result, "ok", False):
        return {
            "ok": False,
            "provider": normalized,
            "asset": asset,
            "provider_address": provider_address,
            "raw_available": None,
            "capacity_usd": None,
            "block": block,
            "reason_code": "provider_asset_balance_unavailable",
            "error": getattr(result, "error", None),
        }
    raw = getattr(result, "result", None)
    try:
        if not isinstance(raw, str) or not raw.startswith("0x"):
            raise ValueError
        raw_available = int(raw, 16)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "provider": normalized,
            "asset": asset,
            "provider_address": provider_address,
            "raw_available": None,
            "capacity_usd": None,
            "block": block,
            "reason_code": "provider_asset_balance_malformed",
        }
    return {
        "ok": True,
        "provider": normalized,
        "asset": asset,
        "provider_address": provider_address,
        "raw_available": raw_available,
        "capacity_usd": None,
        "block": block,
        "source": "erc20_balance_of_provider_contract",
        "reason_code": "observed_provider_asset_balance",
    }


def raw_capacity_to_usd(
    raw_available: int,
    *,
    asset_price_usd: float | int | str,
    asset_decimals: int,
) -> float:
    """Convert observed raw capacity to USD only with explicit price metadata."""
    if raw_available < 0 or asset_decimals < 0:
        raise ValueError("capacity_units_invalid")
    price = float(asset_price_usd)
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("asset_price_usd_invalid")
    value = float(raw_available) / float(10**int(asset_decimals)) * price
    if not math.isfinite(value):
        raise ValueError("capacity_usd_invalid")
    return value
