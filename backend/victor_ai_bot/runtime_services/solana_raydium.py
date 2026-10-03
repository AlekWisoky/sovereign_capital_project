from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import httpx

RAYDIUM_SWAP_HOST = "https://transaction-v1.raydium.io"


@dataclass(frozen=True)
class RaydiumQuote:
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    price_impact_pct: float
    route_plan: tuple[dict[str, Any], ...]
    request_id: str

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "RaydiumQuote":
        data = payload.get("data") if isinstance(payload, Mapping) else {}
        if not isinstance(data, Mapping):
            data = {}
        route = data.get("routePlan")
        route_plan = tuple(dict(item) for item in route if isinstance(item, Mapping)) if isinstance(route, list) else ()
        try:
            impact = float(data.get("priceImpactPct") or 0.0)
        except (TypeError, ValueError):
            impact = 0.0
        return cls(
            input_mint=str(data.get("inputMint") or ""),
            output_mint=str(data.get("outputMint") or ""),
            in_amount=int(data.get("inputAmount") or 0),
            out_amount=int(data.get("outputAmount") or 0),
            price_impact_pct=impact,
            route_plan=route_plan,
            request_id=str(payload.get("id") or ""),
        )


class RaydiumQuoteClient:
    """Read-only Raydium Trade API quote boundary; never builds or executes transactions."""

    def __init__(self, *, timeout_s: float = 8.0):
        self.timeout_s = max(1.0, float(timeout_s))

    async def quote(self, *, input_mint: str, output_mint: str, amount: int) -> RaydiumQuote:
        if not input_mint or not output_mint or int(amount) <= 0:
            raise ValueError("input_mint, output_mint and positive amount are required")
        params = {
            "inputMint": str(input_mint),
            "outputMint": str(output_mint),
            "amount": str(int(amount)),
            "slippageBps": "0",
            "txVersion": "V0",
        }
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.get(
                f"{RAYDIUM_SWAP_HOST}/compute/swap-base-in",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, Mapping) or not bool(payload.get("success")):
            raise ValueError(str((payload or {}).get("msg") if isinstance(payload, Mapping) else "raydium_quote_failed"))
        quote = RaydiumQuote.from_response(payload)
        if quote.in_amount <= 0 or quote.out_amount <= 0:
            raise ValueError("raydium_quote_invalid_amounts")
        return quote

    async def quote_matrix(self, requests: list[dict[str, Any]], *, concurrency: int = 4) -> list[RaydiumQuote | None]:
        import asyncio
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        async def one(request: dict[str, Any]) -> RaydiumQuote | None:
            async with semaphore:
                try:
                    return await self.quote(**request)
                except (httpx.HTTPError, TypeError, ValueError):
                    return None

        return await asyncio.gather(*(one(request) for request in requests))
