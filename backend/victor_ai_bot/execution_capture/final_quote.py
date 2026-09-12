from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from typing import Any

from ..ethabi import enc_address, enc_uint, selector
from ..quote_univ3 import quote_exact_input_single
from ..rpc import JsonRpcClient


class FinalQuoteError(ValueError):
    """Raised when execution-time quote truth is unavailable or inconsistent."""


@dataclass(frozen=True)
class FinalQuote:
    quote_id: str
    quoted_at_ms: int
    block_number: int
    token: str
    raw_amount: int
    asset_decimals: int
    asset_price_usd: float
    price_source: str
    route_id: str
    decision_id: str
    correlation_id: str
    stable_token: str
    stable_decimals: int
    stable_amount_out_raw: int
    fee: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "quoted_at_ms": self.quoted_at_ms,
            "block_number": self.block_number,
            "token": self.token,
            "raw_amount": self.raw_amount,
            "asset_decimals": self.asset_decimals,
            "asset_price_usd": self.asset_price_usd,
            "price_source": self.price_source,
            "route_id": self.route_id,
            "decision_id": self.decision_id,
            "correlation_id": self.correlation_id,
            "stable_token": self.stable_token,
            "stable_decimals": self.stable_decimals,
            "stable_amount_out_raw": self.stable_amount_out_raw,
            "fee": self.fee,
        }


_DECIMALS_SELECTOR = selector("decimals()")
_GET_POOL_SELECTOR = selector("getPool(address,address,uint24)")
_FEE_TIERS = (100, 500, 3000, 10000)


def _word_uint(hex_result: Any) -> int:
    if not isinstance(hex_result, str) or not hex_result.startswith("0x"):
        raise FinalQuoteError("rpc_result_invalid")
    raw = bytes.fromhex(hex_result[2:])
    if len(raw) < 32:
        raise FinalQuoteError("rpc_result_short")
    return int.from_bytes(raw[-32:], "big")


def _word_address(hex_result: Any) -> str:
    if not isinstance(hex_result, str) or not hex_result.startswith("0x"):
        raise FinalQuoteError("rpc_result_invalid")
    raw = bytes.fromhex(hex_result[2:])
    if len(raw) < 32:
        raise FinalQuoteError("rpc_result_short")
    address = "0x" + raw[-20:].hex()
    if int(address, 16) == 0:
        raise FinalQuoteError("v3_pool_unavailable")
    return address


async def resolve_erc20_decimals(
    rpc: JsonRpcClient, token: str, *, block: str
) -> int:
    if not token:
        raise FinalQuoteError("asset_token_missing")
    result = await rpc.eth_call(token, "0x" + _DECIMALS_SELECTOR.hex(), block=block)
    if not result.ok:
        raise FinalQuoteError("asset_decimals_rpc_failed")
    decimals = _word_uint(result.result)
    if decimals < 0 or decimals > 255:
        raise FinalQuoteError("asset_decimals_invalid")
    return int(decimals)


async def _resolve_v3_pool(
    rpc: JsonRpcClient,
    factory: str,
    token: str,
    stable: str,
    fee: int,
    *,
    block: str,
) -> str | None:
    data = b"".join(
        [
            _GET_POOL_SELECTOR,
            enc_address(token),
            enc_address(stable),
            enc_uint(int(fee)),
        ]
    )
    result = await rpc.eth_call(factory, "0x" + data.hex(), block=block)
    if not result.ok or not isinstance(result.result, str):
        return None
    try:
        return _word_address(result.result)
    except FinalQuoteError:
        return None


def _quote_id(
    *,
    chain: str,
    block_number: int,
    token: str,
    stable: str,
    fee: int,
    raw_amount: int,
    stable_amount: int,
    decision_id: str,
    correlation_id: str,
    route_id: str,
) -> str:
    material = "|".join(
        [
            chain,
            str(block_number),
            token.lower(),
            stable.lower(),
            str(fee),
            str(raw_amount),
            str(stable_amount),
            decision_id,
            correlation_id,
            route_id,
        ]
    )
    return "quote-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _lineage(opp: Any, decision: Any | None) -> tuple[str, str, str]:
    opp_meta = dict(getattr(opp, "meta", {}) or {}) if isinstance(getattr(opp, "meta", None), dict) else {}
    lineage = dict(opp_meta.get("canonical_lineage") or {})
    brain = dict(opp_meta.get("brain") or {})
    decision_meta = dict(getattr(decision, "metadata", {}) or {}) if decision is not None else {}

    decision_id = str(
        decision_meta.get("canonical_decision_id")
        or decision_meta.get("decision_id")
        or lineage.get("decision_id")
        or brain.get("canonical_decision_id")
        or ""
    )
    correlation_id = str(
        decision_meta.get("correlation_id")
        or lineage.get("correlation_id")
        or brain.get("correlation_id")
        or ""
    )
    route_id = str(getattr(opp, "route_id", "") or "")
    if not decision_id or not correlation_id:
        raise FinalQuoteError("canonical_decision_lineage_required")
    if not route_id:
        raise FinalQuoteError("route_id_required")

    for source, values in (
        ("decision", decision_meta),
        ("opportunity", lineage),
    ):
        source_decision = str(values.get("canonical_decision_id") or values.get("decision_id") or "")
        source_correlation = str(values.get("correlation_id") or "")
        if source_decision and source_decision != decision_id:
            raise FinalQuoteError(f"decision_lineage_conflict:{source}")
        if source_correlation and source_correlation != correlation_id:
            raise FinalQuoteError(f"correlation_lineage_conflict:{source}")
    return decision_id, correlation_id, route_id


async def produce_final_quote(
    rpc: JsonRpcClient,
    cfg: Any,
    opp: Any,
    *,
    decision: Any | None,
    block_number: int,
) -> FinalQuote:
    """Produce the authoritative execution-time USD quote for the borrow asset.

    The producer uses only the existing on-chain V3 factory + QuoterV2 path.
    It resolves both ERC-20 decimals through RPC and quotes one whole token
    directly into the configured USD stable at the requested block. If no
    direct V3 pool exists, it fails closed rather than falling back to a stale
    admission-time price or an inferred USD value.
    """
    if int(block_number) <= 0:
        raise FinalQuoteError("execution_block_required")
    decision_id, correlation_id, route_id = _lineage(opp, decision)
    chain = getattr(getattr(cfg, "chain", None), "name", "")
    factory = str(getattr(getattr(cfg, "chain", None), "univ3_factory", "") or "")
    quoter = str(getattr(getattr(cfg, "chain", None), "univ3_quoter_v2", "") or "")
    preference = str(
        getattr(getattr(cfg, "execution", None), "usd_stable_preference", "usdc") or "usdc"
    ).lower()
    stable = str(
        getattr(getattr(cfg, "chain", None), preference, "") or ""
    )
    if not factory or not quoter or not stable:
        raise FinalQuoteError("v3_usd_reference_unavailable")

    legs = list(getattr(getattr(opp, "route", None), "legs", []) or [])
    if not legs:
        raise FinalQuoteError("route_legs_missing")
    token = str(getattr(legs[0], "token_in", "") or "")
    if not token:
        raise FinalQuoteError("asset_token_missing")

    block = hex(int(block_number))
    asset_decimals = await resolve_erc20_decimals(rpc, token, block=block)
    stable_decimals = await resolve_erc20_decimals(rpc, stable, block=block)
    raw_amount = 10**asset_decimals

    if token.lower() == stable.lower():
        stable_amount = 10**stable_decimals
        fee = 0
        price_usd = 1.0
    else:
        best: tuple[float, int, int] | None = None
        for fee in _FEE_TIERS:
            pool = await _resolve_v3_pool(
                rpc, factory, token, stable, fee, block=block
            )
            if not pool:
                continue
            quote = await quote_exact_input_single(
                rpc,
                quoter,
                token,
                stable,
                fee,
                raw_amount,
                block=block,
            )
            if quote is None or int(quote.amount_out) <= 0:
                continue
            candidate_price = float(quote.amount_out) / float(10**stable_decimals)
            if best is None or candidate_price > best[0]:
                best = (candidate_price, int(fee), int(quote.amount_out))
        if best is None:
            raise FinalQuoteError("v3_usd_reference_pool_unavailable")
        price_usd, fee, stable_amount = best

    if not price_usd > 0:
        raise FinalQuoteError("execution_usd_price_invalid")

    quoted_at_ms = int(time.time() * 1000)
    quote_id = _quote_id(
        chain=str(chain),
        block_number=int(block_number),
        token=token,
        stable=stable,
        fee=int(fee),
        raw_amount=raw_amount,
        stable_amount=stable_amount,
        decision_id=decision_id,
        correlation_id=correlation_id,
        route_id=route_id,
    )
    return FinalQuote(
        quote_id=quote_id,
        quoted_at_ms=quoted_at_ms,
        block_number=int(block_number),
        token=token,
        raw_amount=raw_amount,
        asset_decimals=asset_decimals,
        asset_price_usd=price_usd,
        price_source="univ3_quoter_v2_direct_usd_stable",
        route_id=route_id,
        decision_id=decision_id,
        correlation_id=correlation_id,
        stable_token=stable,
        stable_decimals=stable_decimals,
        stable_amount_out_raw=stable_amount,
        fee=int(fee),
    )
