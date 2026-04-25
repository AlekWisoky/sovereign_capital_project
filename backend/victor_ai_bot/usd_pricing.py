from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .cache import PerBlockCache
from .quote_univ3 import UniV3Quote, quote_exact_input_single
from .rpc import JsonRpcClient


COMMON_UNIV3_FEES: Sequence[int] = (500, 3000, 10000)
_SAFE_USD_FORMAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)


@dataclass(frozen=True)
class USDToken:
    """Represents the stable token we treat as USD for accounting."""

    address: str
    symbol: str


def _norm_addr(a: str) -> str:
    return (a or "").lower()


def select_usd_stable(chain: object, *, preference: str = "usdc") -> Optional[USDToken]:
    """Select USDC/USDT address from config.

    This is an *analytics* convenience. We assume the selected stable is ~1 USD.
    """

    pref = (preference or "").strip().lower()
    usdc = _norm_addr(getattr(chain, "usdc", "") or "")
    usdt = _norm_addr(getattr(chain, "usdt", "") or "")

    if pref == "usdt" and usdt:
        return USDToken(address=usdt, symbol="USDT")
    if pref == "usdc" and usdc:
        return USDToken(address=usdc, symbol="USDC")

    # Fallback: whichever is configured.
    if usdc:
        return USDToken(address=usdc, symbol="USDC")
    if usdt:
        return USDToken(address=usdt, symbol="USDT")
    return None


def format_usd_micro(usd_micro: int | None, *, decimals: int = 6, places: int = 2) -> str:
    """Format a micro-dollar integer into a human string."""

    if usd_micro is None:
        return "0"
    try:
        v = float(int(usd_micro)) / float(10 ** int(decimals))
        return f"{v:.{int(places)}f}"
    except _SAFE_USD_FORMAT_EXCEPTIONS:
        return "0"


async def _quote_best_univ3_out(
    rpc: JsonRpcClient,
    *,
    quoter_v2: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    block_tag: str,
    cache: PerBlockCache | None = None,
) -> Optional[int]:
    """Best-effort UniV3 quoteExactInputSingle across common fee tiers.

    Deterministic choice rule: pick the highest `amount_out`; if tied, pick lowest fee.
    """

    ti = _norm_addr(token_in)
    to = _norm_addr(token_out)
    if not ti or not to or amount_in <= 0:
        return None
    if ti == to:
        return int(amount_in)

    key = None
    if cache is not None:
        key = f"usd_q:{block_tag}:{ti}->{to}:{int(amount_in)}"
        cached = cache.get(key)
        if cached is not None:
            return int(cached) if cached is not False else None

    best_out: int | None = None
    best_fee: int | None = None
    for fee in COMMON_UNIV3_FEES:
        q: UniV3Quote | None = await quote_exact_input_single(
            rpc,
            quoter_v2,
            ti,
            to,
            int(fee),
            int(amount_in),
            0,
            block=block_tag,
        )
        if q is None:
            continue
        out = int(q.amount_out)
        if (
            best_out is None
            or out > best_out
            or (out == best_out and int(fee) < int(best_fee or fee))
        ):
            best_out = out
            best_fee = int(fee)

    if cache is not None and key is not None:
        cache.set(key, best_out if best_out is not None else False)

    return best_out


async def token_to_usd_micro(
    rpc: JsonRpcClient,
    *,
    chain: object,
    token: str,
    amount_wei: int,
    block_number: int,
    cache: PerBlockCache | None = None,
    preference: str = "usdc",
) -> Optional[int]:
    """Convert an ERC20 amount to approximate USD micro units.

    - Uses UniV3 QuoterV2.
    - Treats configured USDC/USDT as USD.

    Notes:
    - We assume the selected stable uses 6 decimals (USDC/USDT mainnet behavior).
      If a chain uses a different decimals, the *absolute* USD micro value will be off,
      but relative comparisons remain useful.
    """

    usd = select_usd_stable(chain, preference=preference)
    if usd is None:
        return None

    tok = _norm_addr(token)
    if not tok:
        return None

    if tok == _norm_addr(usd.address):
        # Stable token amount is already "USD-ish".
        return int(amount_wei)

    quoter_v2 = getattr(chain, "univ3_quoter_v2", "") or ""
    if not quoter_v2:
        return None

    block_tag = hex(int(block_number))
    out = await _quote_best_univ3_out(
        rpc,
        quoter_v2=str(quoter_v2),
        token_in=tok,
        token_out=str(usd.address),
        amount_in=int(amount_wei),
        block_tag=block_tag,
        cache=cache,
    )
    return int(out) if out is not None else None


async def gas_wei_to_usd_micro(
    rpc: JsonRpcClient,
    *,
    chain: object,
    gas_cost_wei: int,
    block_number: int,
    cache: PerBlockCache | None = None,
    preference: str = "usdc",
) -> Optional[int]:
    """Convert native gas cost (wei) -> USD micro via WETH->stable UniV3 quote."""

    usd = select_usd_stable(chain, preference=preference)
    if usd is None:
        return None

    weth = _norm_addr(getattr(chain, "weth", "") or "")
    if not weth:
        return None

    quoter_v2 = getattr(chain, "univ3_quoter_v2", "") or ""
    if not quoter_v2:
        return None

    block_tag = hex(int(block_number))
    out = await _quote_best_univ3_out(
        rpc,
        quoter_v2=str(quoter_v2),
        token_in=weth,
        token_out=str(usd.address),
        amount_in=int(gas_cost_wei),
        block_tag=block_tag,
        cache=cache,
    )
    return int(out) if out is not None else None


async def gas_wei_to_token_wei(
    rpc: JsonRpcClient,
    *,
    chain: object,
    gas_cost_wei: int,
    token_out: str,
    block_number: int,
    cache: PerBlockCache | None = None,
) -> Optional[int]:
    """Convert native gas cost (wei) -> token_out units via WETH->token_out quote.

    This is used to compute realized profit-after-gas in *profit token units*.
    """

    weth = _norm_addr(getattr(chain, "weth", "") or "")
    out_tok = _norm_addr(token_out)
    if not weth or not out_tok:
        return None
    if out_tok == weth:
        return int(gas_cost_wei)

    quoter_v2 = getattr(chain, "univ3_quoter_v2", "") or ""
    if not quoter_v2:
        return None

    block_tag = hex(int(block_number))
    out = await _quote_best_univ3_out(
        rpc,
        quoter_v2=str(quoter_v2),
        token_in=weth,
        token_out=out_tok,
        amount_in=int(gas_cost_wei),
        block_tag=block_tag,
        cache=cache,
    )
    return int(out) if out is not None else None
