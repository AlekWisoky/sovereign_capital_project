from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ...jsonsafe import to_json_safe
from ...config import ArbitrageConfig
from ...caq_kds.bus import BUS
from .models import ArbitrageOpportunity, MarketQuote, OrderBook
from .registry import build_adapter, list_builtin_venues
from .screener import ArbitrageScreener

_SAFE_ARBITRAGE_STOP_EXCEPTIONS = (asyncio.TimeoutError, RuntimeError)
_SAFE_ADAPTER_CLOSE_EXCEPTIONS = (OSError, RuntimeError, ValueError)
_SAFE_ADAPTER_INIT_EXCEPTIONS = (KeyError, TypeError, ValueError)
_SAFE_SCAN_LOOP_EXCEPTIONS = (OSError, RuntimeError, ValueError, TypeError, asyncio.TimeoutError)
_SAFE_QUOTE_GATHER_EXCEPTIONS = (RuntimeError, OSError, asyncio.TimeoutError)
_SAFE_ORDERBOOK_GATHER_EXCEPTIONS = (RuntimeError, OSError, asyncio.TimeoutError)
_SAFE_BUS_UPDATE_EXCEPTIONS = (TypeError, ValueError)


class ArbitrageRuntime:
    """Phase 5 arbitrage runtime.

    Observe-only by default.

    This runtime runs *alongside* the core DeFi arb runtime (no structural mutation).
    """

    def __init__(self, cfg: ArbitrageConfig):
        self.cfg = cfg
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        self._adapters = []
        self._screener = ArbitrageScreener()

        # State
        self._opps: List[ArbitrageOpportunity] = []
        self._quotes: List[MarketQuote] = []
        self._errors: List[str] = []
        self._last_scan_ms: int = 0

    def enabled(self) -> bool:
        return bool(getattr(self.cfg, "enabled", False))

    def start(self) -> None:
        if not self.enabled():
            return
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except _SAFE_ARBITRAGE_STOP_EXCEPTIONS:
                pass
        for adapter in list(self._adapters):
            try:
                await adapter.close()
            except _SAFE_ADAPTER_CLOSE_EXCEPTIONS:
                pass

    def state(self) -> Dict[str, Any]:
        d = {
            "ok": True,
            "enabled": self.enabled(),
            "mode": str(getattr(self.cfg, "mode", "observe")),
            "last_scan_ms": int(self._last_scan_ms),
            "opp_count": int(len(self._opps)),
            "opps": [asdict(o) for o in self._opps[: int(getattr(self.cfg, "max_opps", 25) or 25)]],
            "quotes": [asdict(q) for q in self._quotes[:200]],
            "errors": list(self._errors[-30:]),
            "builtin_venues": list_builtin_venues(),
        }
        return to_json_safe(d)

    def _record_adapter_result_errors(self, *, label: str, results: Iterable[Any]) -> None:
        for result in results:
            if isinstance(result, Exception):
                self._errors.append(f"{label}:{type(result).__name__}:{result}")

    async def _init_adapters(self) -> None:
        if self._adapters:
            return
        venues = list(getattr(self.cfg, "venues", []) or [])
        if not venues:
            return
        for venue in venues:
            try:
                self._adapters.append(build_adapter(dict(venue)))
            except _SAFE_ADAPTER_INIT_EXCEPTIONS as exc:
                self._errors.append(f"adapter_init_failed:{type(exc).__name__}:{exc}")

    async def _loop(self) -> None:
        await self._init_adapters()
        poll = float(getattr(self.cfg, "poll_seconds", 2.0) or 2.0)
        if poll < 0.5:
            poll = 0.5

        while not self._stop.is_set():
            t0 = time.time()
            try:
                await self._scan_once()
            except _SAFE_SCAN_LOOP_EXCEPTIONS as exc:
                self._errors.append(f"scan_failed:{type(exc).__name__}:{exc}")
            dt = time.time() - t0
            await asyncio.sleep(max(0.0, poll - dt))

    async def _scan_once(self) -> None:
        if not self._adapters:
            await self._init_adapters()
        if not self._adapters:
            self._last_scan_ms = int(time.time() * 1000)
            return

        pairs = list(getattr(self.cfg, "pairs", []) or [])
        if not pairs:
            pairs = ["BTCUSDT", "ETHUSDT"]

        opps: List[ArbitrageOpportunity] = []
        all_quotes: List[MarketQuote] = []
        for symbol in pairs:
            quote_tasks = [adapter.fetch_quote(symbol=symbol) for adapter in self._adapters]
            quote_results: List[Any] = []
            try:
                quote_results = list(await asyncio.gather(*quote_tasks, return_exceptions=True))
            except _SAFE_QUOTE_GATHER_EXCEPTIONS:
                quote_results = []
            self._record_adapter_result_errors(label=f"quote_failed:{symbol}", results=quote_results)
            quotes = [result for result in quote_results if isinstance(result, MarketQuote)]
            all_quotes.extend(list(quotes))

            ob_map: Dict[Tuple[str, str], OrderBook] = {}
            ob_results: List[Any] = []
            try:
                ob_tasks = [adapter.fetch_orderbook(symbol=symbol, depth=10) for adapter in self._adapters]
                ob_results = list(await asyncio.gather(*ob_tasks, return_exceptions=True))
            except _SAFE_ORDERBOOK_GATHER_EXCEPTIONS:
                ob_results = []
            self._record_adapter_result_errors(label=f"orderbook_failed:{symbol}", results=ob_results)
            for adapter, result in zip(self._adapters, ob_results):
                if isinstance(result, OrderBook):
                    ob_map[(adapter.name, adapter.product)] = result

            opps.extend(
                self._screener.screen(
                    symbol=symbol,
                    quotes=quotes,
                    orderbooks=ob_map,
                    latency_seconds=dict(getattr(self.cfg, "latency_seconds", {}) or {}),
                    min_spread_bps=int(getattr(self.cfg, "min_spread_bps", 8) or 8),
                    min_net_profit_usd=float(getattr(self.cfg, "min_net_profit_usd", 2.0) or 2.0),
                    max_notional_usd=float(getattr(self.cfg, "max_notional_usd", 2500.0) or 2500.0),
                    taker_fee_bps=int(getattr(self.cfg, "taker_fee_bps", 10) or 10),
                    leverage=float(getattr(self.cfg, "leverage", 1.0) or 1.0),
                )
            )

        opps.sort(key=lambda opportunity: float(opportunity.est_net_profit_usd), reverse=True)
        max_opps = int(getattr(self.cfg, "max_opps", 25) or 25)
        opps = opps[: max(1, max_opps)]

        async with self._lock:
            self._opps = opps
            self._quotes = all_quotes
            self._last_scan_ms = int(time.time() * 1000)

        self._publish_top_opp_summary(opps)

    def _publish_top_opp_summary(self, opps: List[ArbitrageOpportunity]) -> None:
        if not opps:
            return
        top = opps[0]
        payload = {
            "spread_bps": float(getattr(top, "spread_bps", 0.0) or 0.0),
            "depth_usd": float(getattr(top, "depth_usd", 0.0) or 0.0),
            "imbalance": float(getattr(top, "orderbook_imbalance", 0.0) or 0.0),
            "funding_bps": float(getattr(top, "funding_rate_bps", 0.0) or 0.0),
            "funding_change_bps": float(getattr(top, "funding_rate_change_bps", 0.0) or 0.0),
            "mid": float(getattr(top, "mid_price", 0.0) or 0.0),
        }
        try:
            BUS.update("cex", payload)
        except _SAFE_BUS_UPDATE_EXCEPTIONS:
            pass
