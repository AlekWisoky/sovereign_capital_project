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


@dataclass(frozen=True)
class FinalQuoteRequest:
    rpc: JsonRpcClient
    cfg: Any
    opp: Any
    decision: Any | None
    block_number: int


@dataclass(frozen=True)
class _V3PoolRequest:
    rpc: JsonRpcClient
    factory: str
    token: str
    stable: str
    fee: int
    block: str


@dataclass(frozen=True)
class _QuoteLineage:
    decision_id: str
    correlation_id: str
    route_id: str


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
    if decimals > 255:
        raise FinalQuoteError("asset_decimals_invalid")
    return int(decimals)


async def _resolve_v3_pool(request: _V3PoolRequest) -> str | None:
    data = b"".join(
        [
            _GET_POOL_SELECTOR,
            enc_address(request.token),
            enc_address(request.stable),
            enc_uint(int(request.fee)),
        ]
    )
    result = await request.rpc.eth_call(
        request.factory,
        "0x" + data.hex(),
        block=request.block,
    )
    if not result.ok or not isinstance(result.result, str):
        return None
    try:
        return _word_address(result.result)
    except FinalQuoteError:
        return None


def _quote_id(material: str) -> str:
    return "quote-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _lineage_maps(opp: Any, decision: Any | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    meta = _mapping(getattr(opp, "meta", None))
    lineage = _mapping(meta.get("canonical_lineage"))
    brain = _mapping(meta.get("brain"))
    decision_meta = _mapping(getattr(decision, "metadata", None))
    return decision_meta, lineage, brain


def _lineage_identities(
    decision_meta: dict[str, Any],
    lineage: dict[str, Any],
    brain: dict[str, Any],
) -> tuple[str, str]:
    decision_id = _text(
        decision_meta.get("canonical_decision_id"),
        decision_meta.get("decision_id"),
        lineage.get("decision_id"),
        brain.get("canonical_decision_id"),
    )
    correlation_id = _text(
        decision_meta.get("correlation_id"),
        lineage.get("correlation_id"),
        brain.get("correlation_id"),
    )
    return decision_id, correlation_id


def _validate_lineage_sources(
    decision_meta: dict[str, Any],
    lineage: dict[str, Any],
    decision_id: str,
    correlation_id: str,
) -> None:
    for source, values in (("decision", decision_meta), ("opportunity", lineage)):
        source_decision = _text(values.get("canonical_decision_id"), values.get("decision_id"))
        source_correlation = _text(values.get("correlation_id"))
        if source_decision and source_decision != decision_id:
            raise FinalQuoteError(f"decision_lineage_conflict:{source}")
        if source_correlation and source_correlation != correlation_id:
            raise FinalQuoteError(f"correlation_lineage_conflict:{source}")


def _lineage(opp: Any, decision: Any | None) -> _QuoteLineage:
    decision_meta, lineage, brain = _lineage_maps(opp, decision)
    decision_id, correlation_id = _lineage_identities(decision_meta, lineage, brain)
    route_id = _text(getattr(opp, "route_id", ""))
    if not decision_id or not correlation_id:
        raise FinalQuoteError("canonical_decision_lineage_required")
    if not route_id:
        raise FinalQuoteError("route_id_required")
    _validate_lineage_sources(decision_meta, lineage, decision_id, correlation_id)
    return _QuoteLineage(decision_id, correlation_id, route_id)


def _quote_config(cfg: Any) -> tuple[str, str, str, str]:
    chain = getattr(cfg, "chain", None)
    execution = getattr(cfg, "execution", None)
    factory = str(getattr(chain, "univ3_factory", "") or "")
    quoter = str(getattr(chain, "univ3_quoter_v2", "") or "")
    preference = _text(getattr(execution, "usd_stable_preference", "usdc")).lower() or "usdc"
    stable = str(getattr(chain, preference, "") or "")
    if not factory or not quoter or not stable:
        raise FinalQuoteError("v3_usd_reference_unavailable")
    return str(getattr(chain, "name", "") or ""), factory, quoter, stable


def _route_token(opp: Any) -> str:
    legs = list(getattr(getattr(opp, "route", None), "legs", []) or [])
    if not legs:
        raise FinalQuoteError("route_legs_missing")
    token = str(getattr(legs[0], "token_in", "") or "")
    if not token:
        raise FinalQuoteError("asset_token_missing")
    return token


async def _best_v3_quote(
    request: FinalQuoteRequest,
    *,
    factory: str,
    quoter: str,
    token: str,
    stable: str,
    stable_decimals: int,
    raw_amount: int,
    block: str,
) -> tuple[float, int, int]:
    best: tuple[float, int, int] | None = None
    for fee in _FEE_TIERS:
        pool = await _resolve_v3_pool(
            _V3PoolRequest(request.rpc, factory, token, stable, fee, block)
        )
        if not pool:
            continue
        quote = await quote_exact_input_single(
            request.rpc,
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
    return best


def _quote_material(
    chain: str,
    block_number: int,
    token: str,
    stable: str,
    fee: int,
    raw_amount: int,
    stable_amount: int,
    lineage: _QuoteLineage,
) -> str:
    return "|".join(
        [
            chain,
            str(block_number),
            token.lower(),
            stable.lower(),
            str(fee),
            str(raw_amount),
            str(stable_amount),
            lineage.decision_id,
            lineage.correlation_id,
            lineage.route_id,
        ]
    )


async def produce_final_quote(request: FinalQuoteRequest) -> FinalQuote:
    """Produce authoritative execution-time USD quote truth for the borrow asset."""
    block_number = int(request.block_number)
    if block_number <= 0:
        raise FinalQuoteError("execution_block_required")

    lineage = _lineage(request.opp, request.decision)
    chain, factory, quoter, stable = _quote_config(request.cfg)
    token = _route_token(request.opp)
    block = hex(block_number)
    asset_decimals = await resolve_erc20_decimals(request.rpc, token, block=block)
    stable_decimals = await resolve_erc20_decimals(request.rpc, stable, block=block)
    raw_amount = 10**asset_decimals

    if token.lower() == stable.lower():
        stable_amount = 10**stable_decimals
        fee = 0
        price_usd = 1.0
    else:
        price_usd, fee, stable_amount = await _best_v3_quote(
            request,
            factory=factory,
            quoter=quoter,
            token=token,
            stable=stable,
            stable_decimals=stable_decimals,
            raw_amount=raw_amount,
            block=block,
        )

    if price_usd <= 0:
        raise FinalQuoteError("execution_usd_price_invalid")

    quoted_at_ms = int(time.time() * 1000)
    quote_id = _quote_id(
        _quote_material(
            chain,
            block_number,
            token,
            stable,
            int(fee),
            raw_amount,
            stable_amount,
            lineage,
        )
    )
    return FinalQuote(
        quote_id=quote_id,
        quoted_at_ms=quoted_at_ms,
        block_number=block_number,
        token=token,
        raw_amount=raw_amount,
        asset_decimals=asset_decimals,
        asset_price_usd=price_usd,
        price_source="univ3_quoter_v2_direct_usd_stable",
        route_id=lineage.route_id,
        decision_id=lineage.decision_id,
        correlation_id=lineage.correlation_id,
        stable_token=stable,
        stable_decimals=stable_decimals,
        stable_amount_out_raw=stable_amount,
        fee=int(fee),
    )
