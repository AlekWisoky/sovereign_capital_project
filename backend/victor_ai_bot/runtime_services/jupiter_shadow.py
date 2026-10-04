from __future__ import annotations

import asyncio
import os
import statistics
from typing import Any

import httpx

from .solana_jupiter import JupiterNotConfigured, JupiterSwapV2Client
from .solana_raydium import RaydiumQuoteClient


SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
JUP_MINT = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
RAY_MINT = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

_DEFAULT_PAIRS = (
    (USDC_MINT, SOL_MINT, 6, 9, "SOL/USDC"),
    (USDC_MINT, USDT_MINT, 6, 6, "USDT/USDC"),
    (USDC_MINT, JUP_MINT, 6, 6, "JUP/USDC"),
    (USDC_MINT, RAY_MINT, 6, 6, "RAY/USDC"),
)


class JupiterShadowService:
    """Read-only Solana discovery bridge; never execution authority.

    Jupiter is one venue/router in the discovery graph. Raydium supplies an
    independent venue quote so a price differential can be tested as an
    actual two-venue round trip rather than treating a Jupiter route as an
    arbitrage opportunity.
    """

    def __init__(self) -> None:
        self.enabled = bool(int(os.getenv("VICTOR_SOLANA_JUPITER_ENABLED", "0") or 0))
        self.max_pairs = max(1, int(os.getenv("VICTOR_SOLANA_JUPITER_MAX_PAIRS", "4") or 4))
        self.max_sizes = max(1, int(os.getenv("VICTOR_SOLANA_JUPITER_MAX_SIZES", "5") or 5))
        self.base_notional_usd = max(10.0, float(os.getenv("VICTOR_SOLANA_JUPITER_BASE_NOTIONAL_USD", "1000") or 1000))
        self.discovery_concurrency = max(1, int(os.getenv("VICTOR_SOLANA_JUPITER_CONCURRENCY", "4") or 4))
        self.client = JupiterSwapV2Client()
        self.raydium = RaydiumQuoteClient()
        self._last = {
            "enabled": self.enabled,
            "configured": self.client.configured,
            "status": "disabled" if not self.enabled else ("configured" if self.client.configured else "unconfigured"),
            "quotes": {"requests": 0, "successes": 0, "failures": 0},
            "opportunities": {"authoritative": 0, "diagnostic": 0},
            "economic_frontier": None,
            "discovery": {"universe_pairs": 0, "cross_venue_routes": 0, "candidates": 0, "quote_failures": 0},
            "candidates": [],
            "execution_authority": False,
        }

    def snapshot(self) -> dict[str, Any]:
        return dict(self._last)

    async def quote_pairs(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()
        bounded = list(requests[: self.max_pairs * self.max_sizes])
        results = await self.client.quote_matrix(bounded, concurrency=4)
        successes = sum(item is not None for item in results)
        self._last = {
            **self._last,
            "quotes": {
                "requests": len(bounded),
                "successes": successes,
                "failures": len(bounded) - successes,
            },
            "status": "healthy" if successes else "quote_unavailable",
            "execution_authority": False,
        }
        return self.snapshot()

    def _pair_universe(self) -> list[tuple[str, str, int, int, str]]:
        raw = str(os.getenv("VICTOR_SOLANA_JUPITER_PAIRS", "") or "").strip()
        if not raw:
            return list(_DEFAULT_PAIRS[: self.max_pairs])
        out = []
        for item in raw.split(","):
            parts = [p.strip() for p in item.split(":")]
            if len(parts) != 5:
                continue
            try:
                out.append((parts[0], parts[1], int(parts[2]), int(parts[3]), parts[4]))
            except (TypeError, ValueError):
                continue
        return out[: self.max_pairs]

    def _sizes(self) -> list[float]:
        multipliers = (0.25, 0.5, 1.0, 2.0, 4.0)
        return [self.base_notional_usd * x for x in multipliers[: self.max_sizes]]

    async def _sol_price_usd(self) -> float | None:
        # Keep network-cost accounting independent of Jupiter availability.
        try:
            quote = await self.raydium.quote(input_mint=SOL_MINT, output_mint=USDC_MINT, amount=1_000_000_000)
            if quote.in_amount > 0 and quote.out_amount > 0:
                return float(quote.out_amount) / 1_000_000.0
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        return None

    async def _network_cost_usd(self, sol_price_usd: float | None) -> dict[str, Any]:
        rpc_url = str(os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com") or "").strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "getRecentPrioritizationFees", "params": [[]]},
                )
                response.raise_for_status()
                payload = response.json()
            rows = payload.get("result") if isinstance(payload, dict) else None
            fees = [int(x.get("prioritizationFee") or 0) for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []
            median_priority_lamports = int(statistics.median(fees)) if fees else 0
            signatures = max(1, int(os.getenv("VICTOR_SOLANA_TX_SIGNATURES", "1") or 1))
            tx_count = max(1, int(os.getenv("VICTOR_SOLANA_DISCOVERY_TX_COUNT", "2") or 2))
            base_lamports = 5000 * signatures * tx_count
            compute_units = max(1, int(os.getenv("VICTOR_SOLANA_DISCOVERY_COMPUTE_UNITS", "200000") or 200000))
            # getRecentPrioritizationFees returns a recent absolute fee for a
            # writable account set; using the median as a discovery estimate is
            # conservative telemetry, not execution truth.
            priority_lamports = median_priority_lamports * tx_count
            lamports = base_lamports + priority_lamports
            usd = (lamports / 1_000_000_000.0) * float(sol_price_usd or 0.0)
            return {
                "available": bool(sol_price_usd and rows),
                "usd": usd,
                "lamports": lamports,
                "base_lamports": base_lamports,
                "priority_lamports": priority_lamports,
                "median_priority_lamports": median_priority_lamports,
                "compute_units_assumed": compute_units,
                "source": "solana_rpc_recent_prioritization_fees",
                "verified": False,
            }
        except (httpx.HTTPError, TypeError, ValueError, KeyError):
            return {
                "available": False,
                "usd": 0.0,
                "lamports": 0,
                "source": "unavailable",
                "verified": False,
            }

    async def _discover_direction(
        self,
        *,
        input_mint: str,
        output_mint: str,
        input_decimals: int,
        symbol: str,
        usd: float,
        network: dict[str, Any],
        jupiter_first: bool,
    ) -> tuple[dict[str, Any] | None, int, int, str | None]:
        amount = int(round(usd * (10 ** input_decimals)))
        attempts = 0
        successes = 0
        try:
            if jupiter_first:
                attempts += 1
                first = await self.client.quote(input_mint=input_mint, output_mint=output_mint, amount=amount)
                successes += 1
                attempts += 1
                second = await self.raydium.quote(input_mint=output_mint, output_mint=input_mint, amount=int(first.out_amount))
                successes += 1
            else:
                attempts += 1
                first = await self.raydium.quote(input_mint=input_mint, output_mint=output_mint, amount=amount)
                successes += 1
                attempts += 1
                second = await self.client.quote(input_mint=output_mint, output_mint=input_mint, amount=int(first.out_amount))
                successes += 1
            if int(first.out_amount) <= 0 or int(second.out_amount) <= 0:
                return None, attempts, successes, "zero_output"
            final_raw = int(second.out_amount)
            profit_usd = (final_raw - amount) / float(10 ** input_decimals)
            after_cost_usd = profit_usd - float(network.get("usd") or 0.0)
            route_name = "jupiter-to-raydium" if jupiter_first else "raydium-to-jupiter"
            row = {
                "id": f"solana:{symbol}:{route_name}:{amount}",
                "route_id": f"solana:{symbol}:{route_name}",
                "chain": "solana", "strategy": "cross_venue_arb_shadow", "symbol": symbol,
                "amount_in": str(amount), "amount_in_usd": usd,
                "gross_profit_usd": profit_usd, "after_cost_profit_usd": after_cost_usd,
                "after_cost_profit_usd_micro": int(round(after_cost_usd * 1_000_000.0)),
                "network_cost_usd": float(network.get("usd") or 0.0), "network_cost": dict(network),
                "quote_derived": True, "economic_model_source": "quote_derived_cross_venue",
                "observed": True, "extrapolated": False, "authoritative": False,
                "diagnostic_only": True, "execution_authority": False,
                "reason": "awaiting_canonical_solana_revalidation",
            }
            if jupiter_first:
                row.update({
                    "jupiter_out_amount": str(first.out_amount), "raydium_final_amount": str(final_raw),
                    "jupiter_router": first.router, "jupiter_fee_bps": first.fee_bps,
                    "jupiter_platform_fee_bps": first.platform_fee_bps, "raydium_price_impact_pct": second.price_impact_pct,
                })
            else:
                row.update({
                    "raydium_out_amount": str(first.out_amount), "jupiter_final_amount": str(final_raw),
                    "jupiter_router": second.router, "jupiter_fee_bps": second.fee_bps,
                    "jupiter_platform_fee_bps": second.platform_fee_bps, "raydium_price_impact_pct": first.price_impact_pct,
                })
            return row, attempts, successes, None
        except (httpx.HTTPError, JupiterNotConfigured, TypeError, ValueError) as exc:
            return None, attempts, successes, type(exc).__name__

    async def discover(self) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()
        if not self.client.configured:
            self._last = {**self._last, "status": "unconfigured", "execution_authority": False}
            return self.snapshot()
        if not self.client.default_taker:
            self._last = {
                **self._last, "status": "taker_unconfigured",
                "discovery": {**self._last.get("discovery", {}), "reason": "VICTOR_SOLANA_JUPITER_TAKER_required_by_live_order_boundary"},
                "execution_authority": False,
            }
            return self.snapshot()

        pairs = self._pair_universe()
        sizes = self._sizes()
        sol_price = await self._sol_price_usd()
        network = await self._network_cost_usd(sol_price)
        candidates: list[dict[str, Any]] = []
        quote_attempts = quote_successes = quote_failures = 0
        failure_reasons: dict[str, int] = {}
        sem = asyncio.Semaphore(self.discovery_concurrency)

        async def one(pair: tuple[str, str, int, int, str], usd: float):
            async with sem:
                input_mint, output_mint, input_decimals, _output_decimals, symbol = pair
                return await asyncio.gather(
                    self._discover_direction(input_mint=input_mint, output_mint=output_mint, input_decimals=input_decimals, symbol=symbol, usd=usd, network=network, jupiter_first=True),
                    self._discover_direction(input_mint=input_mint, output_mint=output_mint, input_decimals=input_decimals, symbol=symbol, usd=usd, network=network, jupiter_first=False),
                )

        results = await asyncio.gather(*[one(pair, usd) for pair in pairs for usd in sizes])
        for pair_results in results:
            for row, attempted, successes, reason in pair_results:
                quote_attempts += attempted
                quote_successes += successes
                if row is not None:
                    candidates.append(row)
                else:
                    quote_failures += attempted - successes
                    if reason:
                        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        candidates.sort(key=lambda row: float(row.get("after_cost_profit_usd") or 0.0), reverse=True)
        frontier_points = [
            {"amount": int(row["amount_in"]), "amount_in_usd": float(row["amount_in_usd"]), "after_cost_profit_usd": float(row["after_cost_profit_usd"]), "route_id": str(row["route_id"])}
            for row in candidates[:16]
        ]
        best = frontier_points[0] if frontier_points else None
        frontier = {
            "points": frontier_points, "best_observed": best,
            "optimal_observed_amount": int(best["amount"]) if best else None,
            "optimal_observed_notional_usd": float(best["amount_in_usd"]) if best else None,
            "optimal_observed_after_cost_profit_usd": float(best["after_cost_profit_usd"]) if best else None,
            "model_source": "quote_derived_cross_venue_observed_only", "extrapolated": False,
        }
        self._last = {
            **self._last,
            "status": "healthy" if candidates else ("quote_unavailable" if quote_failures else "no_cross_venue_edges"),
            "quotes": {"requests": quote_attempts, "successes": quote_successes, "failures": quote_failures, "failure_reasons": failure_reasons},
            "opportunities": {"authoritative": 0, "diagnostic": sum(1 for row in candidates if float(row["after_cost_profit_usd"]) > 0.0)},
            "economic_frontier": frontier,
            "discovery": {
                "universe_pairs": len(pairs), "sizes": sizes, "cross_venue_routes": len(candidates),
                "candidates": len(candidates), "quote_failures": quote_failures, "failure_reasons": failure_reasons,
                "network_cost": network, "concurrency": self.discovery_concurrency,
            },
            "candidates": candidates[:32], "execution_authority": False,
        }
        return self.snapshot()
