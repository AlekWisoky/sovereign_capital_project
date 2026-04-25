from __future__ import annotations

"""DEX adapter interface.

Adapters here are *not* the core execution engine. They provide normalized quote
and pool-state access that can be used by spread engines, dashboards, and
strategy generation. Execution methods are intentionally gated.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class DEXQuote:
    ok: bool
    amount_out: int = 0
    gas_estimate: int = 0
    meta: Dict[str, Any] | None = None


class DEXAdapter(Protocol):
    chain: str
    name: str

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]: ...
    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote: ...
    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int: ...
    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]: ...


class QuoteOnlyDEXAdapter:
    """Wrapper that forbids execution."""

    def __init__(self, inner: DEXAdapter):
        self.inner = inner
        self.chain = getattr(inner, "chain", "")
        self.name = getattr(inner, "name", "")

    async def fetch_pool_state(self, pool: str) -> Dict[str, Any]:
        return await self.inner.fetch_pool_state(pool)

    async def quote(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> DEXQuote:
        return await self.inner.quote(token_in, token_out, amount_in, pool=pool)

    async def estimate_gas(self, token_in: str, token_out: str, amount_in: int, *, pool: Optional[str] = None) -> int:
        return await self.inner.estimate_gas(token_in, token_out, amount_in, pool=pool)

    async def execute_swap(self, *args, **kwargs) -> Dict[str, Any]:
        raise RuntimeError("quote_only:execute_swap disabled")
