from __future__ import annotations

"""Built-in DEX quote adapters.

These adapters intentionally reuse the project's existing quoting functions.
They are *quote-only* by default and should never change core execution.
"""

from typing import Any, Dict, Optional


_SAFE_DEX_ADAPTER_QUOTE_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
)

from victor_ai_bot.rpc import JsonRpcClient

from .dex import DEXAdapter, DEXQuote


def _failed_quote(exc: Exception) -> DEXQuote:
    return DEXQuote(ok=False, amount_out=0, meta={"error": str(exc)})


def _coerce_quote_amounts(q: Any) -> tuple[int, int]:
    out = int(getattr(q, "amount_out", 0) or 0)
    gas = int(getattr(q, "gas_estimate", 0) or 0)
    return out, gas


class UniswapV3Adapter:
    def __init__(self, *, chain: str, rpc: JsonRpcClient, quoter_v2: str, default_fee: int = 3000):
        self.chain = str(chain)
        self.name = "univ3"
        self.rpc = rpc
        self.quoter_v2 = str(quoter_v2)
        self.default_fee = int(default_fee)

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]:
        # Pool-state discovery is out of scope for this adapter; return scaffold.
        return {"pool": str(pool), "chain": self.chain, "dex": "univ3"}

    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote:
        try:
            from victor_ai_bot.quote_univ3 import quote_exact_input_single
            q = await quote_exact_input_single(
                rpc=self.rpc,
                quoter_v2=str(self.quoter_v2),
                token_in=str(token_in),
                token_out=str(token_out),
                fee=int(self.default_fee),
                amount_in=int(amount_in),
            )
            out, gas = _coerce_quote_amounts(q)
            return DEXQuote(ok=bool(out > 0), amount_out=out, gas_estimate=gas, meta={"pool": pool, "fee": int(self.default_fee)})
        except _SAFE_DEX_ADAPTER_QUOTE_EXCEPTIONS as e:
            return _failed_quote(e)

    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int:
        return 0

    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("execution handled by core engine")


class CurveAdapter:
    def __init__(self, *, chain: str, rpc: JsonRpcClient, pool: str, i: int, j: int, prefer_underlying: bool = False):
        self.chain = str(chain)
        self.name = "curve"
        self.rpc = rpc
        self.pool = str(pool)
        self.i = int(i)
        self.j = int(j)
        self.prefer_underlying = bool(prefer_underlying)

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]:
        return {"pool": str(pool), "chain": self.chain, "dex": "curve"}

    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote:
        try:
            from victor_ai_bot.quote_curve import quote_curve
            q = await quote_curve(self.rpc, pool=str(pool or self.pool), i=int(self.i), j=int(self.j), amount_in=int(amount_in), prefer_underlying=bool(self.prefer_underlying))
            out, _ = _coerce_quote_amounts(q)
            return DEXQuote(ok=bool(out > 0), amount_out=out, meta={"pool": str(pool or self.pool), "i": int(self.i), "j": int(self.j)})
        except _SAFE_DEX_ADAPTER_QUOTE_EXCEPTIONS as e:
            return _failed_quote(e)

    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int:
        return 0

    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("execution handled by core engine")


class BalancerAdapter:
    def __init__(self, *, chain: str, rpc: JsonRpcClient, vault: str, pool_id: str):
        self.chain = str(chain)
        self.name = "balancer"
        self.rpc = rpc
        self.vault = str(vault)
        self.pool_id = str(pool_id)

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]:
        return {"pool": str(pool), "chain": self.chain, "dex": "balancer"}

    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote:
        try:
            from victor_ai_bot.quote_balancer import quote_balancer_given_in
            q = await quote_balancer_given_in(self.rpc, vault=str(self.vault), pool_id_hex32=str(pool or self.pool_id), token_in=str(token_in), token_out=str(token_out), amount_in=int(amount_in))
            out, _ = _coerce_quote_amounts(q)
            return DEXQuote(ok=bool(out > 0), amount_out=out, meta={"pool_id": str(pool or self.pool_id)})
        except _SAFE_DEX_ADAPTER_QUOTE_EXCEPTIONS as e:
            return _failed_quote(e)

    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int:
        return 0

    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("execution handled by core engine")


class UniswapV2RouterAdapter:
    def __init__(self, *, chain: str, router: str = ""):
        self.chain = str(chain)
        self.name = "univ2"
        self.router = str(router or "")

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]:
        return {"pool": str(pool), "chain": self.chain, "dex": "univ2"}

    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote:
        # UniswapV2 quote requires a router contract call; scaffold only.
        return DEXQuote(ok=False, amount_out=0, meta={"note": "univ2 quote scaffold"})

    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int:
        return 0

    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("execution handled by core engine")
