from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

JUPITER_SWAP_V2_BASE = "https://api.jup.ag/swap/v2"


class JupiterNotConfigured(RuntimeError):
    """Jupiter credentials are not configured for live quote discovery."""


@dataclass(frozen=True)
class JupiterQuote:
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    router: str
    request_id: str
    fee_bps: int
    fee_mint: str
    platform_fee_bps: int
    platform_fee_amount: int
    transaction_available: bool
    mode: str
    error_code: int | None

    @classmethod
    def from_response(cls, payload: Mapping[str, Any]) -> "JupiterQuote":
        def integer(key: str, default: int = 0) -> int:
            try:
                return int(payload.get(key) or default)
            except (TypeError, ValueError, OverflowError):
                return default

        platform = payload.get("platformFee")
        if not isinstance(platform, Mapping):
            platform = {}
        error_code_raw = payload.get("errorCode")
        try:
            error_code = int(error_code_raw) if error_code_raw is not None else None
        except (TypeError, ValueError):
            error_code = None
        transaction = payload.get("transaction")
        return cls(
            input_mint=str(payload.get("inputMint") or ""),
            output_mint=str(payload.get("outputMint") or ""),
            in_amount=integer("inAmount"),
            out_amount=integer("outAmount"),
            router=str(payload.get("router") or ""),
            request_id=str(payload.get("requestId") or ""),
            fee_bps=integer("feeBps"),
            fee_mint=str(payload.get("feeMint") or ""),
            platform_fee_bps=_mapping_int(platform, "feeBps"),
            platform_fee_amount=_mapping_int(platform, "amount"),
            transaction_available=bool(transaction),
            mode=str(payload.get("mode") or ""),
            error_code=error_code,
        )


def _mapping_int(mapping: Mapping[str, Any], key: str) -> int:
    try:
        return int(mapping.get(key) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


class JupiterSwapV2Client:
    """Read-only Jupiter Swap V2 meta-aggregator client.

    The discovery boundary intentionally uses /order without a taker so the
    system receives price evidence without signing or executing anything.
    Execution remains a separate, fail-closed phase.
    """

    def __init__(self, *, api_key: str | None = None, timeout_s: float = 8.0):
        self.api_key = str(api_key or os.getenv("JUPITER_API_KEY") or "").strip()
        self.timeout_s = max(1.0, float(timeout_s))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        amount: int,
        taker: str | None = None,
    ) -> JupiterQuote:
        if not self.configured:
            raise JupiterNotConfigured("JUPITER_API_KEY is not configured")
        if not input_mint or not output_mint or int(amount) <= 0:
            raise ValueError("input_mint, output_mint and positive amount are required")
        params = {
            "inputMint": str(input_mint),
            "outputMint": str(output_mint),
            "amount": str(int(amount)),
        }
        if taker:
            params["taker"] = str(taker)
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.get(
                f"{JUPITER_SWAP_V2_BASE}/order",
                params=params,
                headers={"x-api-key": self.api_key},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("Jupiter order response is not an object")
        return JupiterQuote.from_response(payload)

    async def quote_matrix(
        self,
        requests: list[dict[str, Any]],
        *,
        concurrency: int = 4,
    ) -> list[JupiterQuote | None]:
        """Bound quote fan-out; failed quotes remain explicit holes."""
        semaphore = asyncio.Semaphore(max(1, int(concurrency)))

        async def one(request: dict[str, Any]) -> JupiterQuote | None:
            async with semaphore:
                try:
                    return await self.quote(**request)
                except (httpx.HTTPError, JupiterNotConfigured, TypeError, ValueError):
                    return None

        return await asyncio.gather(*(one(request) for request in requests))


def after_cost_profit_usd(
    *,
    input_usd: float,
    output_usd: float,
    quote: JupiterQuote,
    network_cost_usd: float = 0.0,
    extra_cost_usd: float = 0.0,
) -> float:
    """Calculate a quote-backed USD edge; no synthetic profitability is added."""
    if input_usd <= 0.0 or output_usd <= 0.0 or quote.in_amount <= 0 or quote.out_amount <= 0:
        return 0.0
    gross = output_usd - input_usd
    fee_usd = 0.0
    if quote.fee_mint == quote.output_mint and quote.out_amount > 0:
        fee_usd = output_usd * (quote.platform_fee_amount / quote.out_amount)
    elif quote.fee_mint == quote.input_mint and quote.in_amount > 0:
        fee_usd = input_usd * (quote.platform_fee_amount / quote.in_amount)
    return gross - fee_usd - max(0.0, float(network_cost_usd)) - max(0.0, float(extra_cost_usd))


def economic_frontier(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Select the best observed quote-derived economic point, never extrapolate it."""
    normalized = []
    for row in rows:
        try:
            amount = int(row.get("amount") or 0)
            profit = float(row.get("after_cost_profit_usd") or 0.0)
        except (TypeError, ValueError, OverflowError):
            continue
        if amount > 0:
            normalized.append({"amount": amount, "after_cost_profit_usd": profit})
    best = max(normalized, key=lambda item: item["after_cost_profit_usd"], default=None)
    return {
        "points": normalized[:16],
        "best_observed": best,
        "model_source": "quote_observed",
        "extrapolated": False,
    }
