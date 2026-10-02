from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .ethabi import selector


# This registry is the executable-provider authority for the current executor ABI.
# Provider names outside this set are observations/requests only and must never be
# silently converted into an executable provider.
EXECUTABLE_FLASHLOAN_PROVIDERS: tuple[str, ...] = ("aave", "balancer")


def normalize_flashloan_provider(provider: object) -> str:
    """Normalize a provider label without granting executable capability."""
    return str(provider or "").strip().lower()


def is_executable_flashloan_provider(provider: object) -> bool:
    """Return whether the normalized provider has a canonical executor adapter."""
    return normalize_flashloan_provider(provider) in EXECUTABLE_FLASHLOAN_PROVIDERS


def filter_executable_flashloan_providers(
    providers: Iterable[object],
) -> list[str]:
    """Keep only canonical providers, preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for provider in providers:
        normalized = normalize_flashloan_provider(provider)
        if normalized in EXECUTABLE_FLASHLOAN_PROVIDERS and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _decode_uint256_result(result: Any) -> int | None:
    raw = getattr(result, "result", None)
    if not isinstance(raw, str):
        return None
    try:
        payload = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
    except (TypeError, ValueError):
        return None
    if len(payload) < 32:
        return None
    return int.from_bytes(payload[:32], "big")


def _decode_address_result(result: Any) -> str | None:
    value = _decode_uint256_result(result)
    if value is None:
        return None
    address = f"0x{value & ((1 << 160) - 1):040x}"
    return address


async def observe_flashloan_fee_bps(
    rpc: Any,
    cfg: Any,
    provider: object,
    *,
    block: str = "latest",
) -> dict[str, Any]:
    """Read the selected provider's current flash-loan premium from-chain.

    Aave exposes the total premium directly in basis points. Balancer V2 stores
    the fee as a 1e18 fixed-point percentage on its ProtocolFeesCollector, so
    the returned bps is conservatively rounded upward.
    """
    normalized = normalize_flashloan_provider(provider)
    if normalized == "aave":
        pool = str(getattr(getattr(cfg, "chain", cfg), "aave_v3_pool", "") or "")
        if not pool:
            return {"ok": False, "provider": normalized, "reason": "provider_address_missing"}
        result = await rpc.eth_call(
            pool,
            "0x" + selector("FLASHLOAN_PREMIUM_TOTAL()").hex(),
            block=block,
        )
        if not getattr(result, "ok", False):
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": pool,
                "reason": "flashloan_premium_rpc_unavailable",
                "error": getattr(result, "error", None),
            }
        bps = _decode_uint256_result(result)
        if bps is None:
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": pool,
                "reason": "flashloan_premium_malformed",
            }
        return {
            "ok": True,
            "provider": normalized,
            "provider_address": pool,
            "fee_bps": int(bps),
            "source": "aave_pool_FLASHLOAN_PREMIUM_TOTAL",
            "block": block,
        }

    if normalized == "balancer":
        vault = str(getattr(getattr(cfg, "chain", cfg), "balancer_vault", "") or "")
        if not vault:
            return {"ok": False, "provider": normalized, "reason": "provider_address_missing"}
        collector_result = await rpc.eth_call(
            vault,
            "0x" + selector("getProtocolFeesCollector()").hex(),
            block=block,
        )
        if not getattr(collector_result, "ok", False):
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": vault,
                "reason": "flashloan_premium_rpc_unavailable",
                "error": getattr(collector_result, "error", None),
            }
        collector = _decode_address_result(collector_result)
        if not collector or collector == "0x" + "0" * 40:
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": vault,
                "reason": "flashloan_fee_collector_unavailable",
            }
        fee_result = await rpc.eth_call(
            collector,
            "0x" + selector("getFlashLoanFeePercentage()").hex(),
            block=block,
        )
        if not getattr(fee_result, "ok", False):
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": vault,
                "fee_collector": collector,
                "reason": "flashloan_premium_rpc_unavailable",
                "error": getattr(fee_result, "error", None),
            }
        scaled = _decode_uint256_result(fee_result)
        if scaled is None:
            return {
                "ok": False,
                "provider": normalized,
                "provider_address": vault,
                "fee_collector": collector,
                "reason": "flashloan_premium_malformed",
            }
        # Balancer FixedPoint uses 1e18 = 100%, so bps = scaled / 1e14.
        fee_bps = (int(scaled) + 10**14 - 1) // 10**14
        return {
            "ok": True,
            "provider": normalized,
            "provider_address": vault,
            "fee_collector": collector,
            "fee_percentage_scaled": str(int(scaled)),
            "fee_bps": int(fee_bps),
            "source": "balancer_protocol_fees_collector_getFlashLoanFeePercentage",
            "block": block,
        }

    return {
        "ok": False,
        "provider": normalized,
        "reason": f"unsupported_flashloan_provider:{normalized or 'missing'}",
    }
