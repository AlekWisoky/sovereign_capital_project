from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .models import ArbitrageOpportunity, MarketQuote, OrderBook, ArbType


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except (OverflowError, TypeError, ValueError):
        return 0.5


@dataclass
class LifetimeTracker:
    first_seen_ms: int
    last_seen_ms: int


class ArbitrageScreener:
    """Cross-venue arbitrage screener.

    Phase 5 focuses on *spot-futures*, *futures-futures*, and *futures-spot* pricing.

    This module is additive and can be run in observe-only mode.
    """

    def __init__(self):
        self._lifetimes: Dict[str, LifetimeTracker] = {}

    def _lifetime_sec(self, key: str) -> float:
        lt = self._lifetimes.get(key)
        if not lt:
            return 0.0
        return max(0.0, (lt.last_seen_ms - lt.first_seen_ms) / 1000.0)

    def _touch(self, key: str) -> None:
        now = _now_ms()
        lt = self._lifetimes.get(key)
        if lt is None:
            self._lifetimes[key] = LifetimeTracker(first_seen_ms=now, last_seen_ms=now)
        else:
            lt.last_seen_ms = now

    def screen(
        self,
        *,
        symbol: str,
        quotes: List[MarketQuote],
        orderbooks: Dict[Tuple[str, str], OrderBook] | None,
        latency_seconds: Dict[str, float] | None,
        min_spread_bps: int,
        min_net_profit_usd: float,
        max_notional_usd: float,
        taker_fee_bps: int,
        leverage: float,
    ) -> List[ArbitrageOpportunity]:
        """Return arbitrage opportunities for this symbol."""

        latency_seconds = latency_seconds or {}
        orderbooks = orderbooks or {}
        out: List[ArbitrageOpportunity] = []

        # Partition quotes by product
        spot = [q for q in quotes if q.product == "spot"]
        fut = [q for q in quotes if q.product == "futures"]

        def depth_usd(q: MarketQuote, side: str) -> float:
            ob = orderbooks.get((q.venue, q.product))
            if not ob:
                return 0.0
            return ob.depth_usd(side="ask" if side == "buy" else "bid", levels=10)

        # 1) spot-futures
        for s in spot:
            for f in fut:
                # Buy spot (ask), sell futures (bid)
                if s.ask <= 0 or f.bid <= 0:
                    continue
                spread = (f.bid - s.ask) / s.ask
                spread_bps = spread * 10_000
                if spread_bps < float(min_spread_bps):
                    continue

                notional = float(min(max_notional_usd, depth_usd(s, "buy"), depth_usd(f, "sell")))
                if notional <= 0:
                    notional = float(max_notional_usd) * 0.25

                fees = notional * (float(taker_fee_bps) / 10_000.0) * 2.0
                gross = notional * spread * float(leverage)

                # Funding: if we are short futures, we receive funding when funding_rate > 0 (typical convention)
                # We treat funding as a bonus estimate (one period), conservative: clamp to 0 if unknown.
                funding_bonus = float(max(0.0, float(f.funding_rate))) * notional

                # Latency risk penalty
                lat = float(latency_seconds.get(s.venue, 120.0) + latency_seconds.get(f.venue, 120.0))
                risk = _sigmoid((lat - 180.0) / 120.0)  # 0..1
                risk_penalty = risk * 0.20 * abs(gross)  # up to 20% haircut

                net = gross - fees + funding_bonus - risk_penalty
                if net < float(min_net_profit_usd):
                    continue

                opp = ArbitrageOpportunity(
                    arb_type="spot_futures",
                    symbol=symbol,
                    buy_venue=s.venue,
                    sell_venue=f.venue,
                    buy_product="spot",
                    sell_product="futures",
                    entry_buy=float(s.ask),
                    entry_sell=float(f.bid),
                    spread_pct=float(spread * 100.0),
                    funding_rate_buy=0.0,
                    funding_rate_sell=float(f.funding_rate),
                    est_net_profit_usd=float(net),
                    liquidity_depth_usd=float(notional),
                    transfer_latency_risk_score=float(risk),
                    created_at_ms=_now_ms(),
                    confidence=float(min(0.95, 0.5 + 0.4 * max(0.0, spread_bps / 100.0))),
                    meta={"fees_usd": fees, "funding_bonus_usd": funding_bonus, "risk_penalty_usd": risk_penalty},
                )
                k = opp.key()
                self._touch(k)
                opp.pair_lifetime_sec = self._lifetime_sec(k)
                out.append(opp)

                # Also consider reverse: buy futures (ask), sell spot (bid) — for futures_spot
                if f.ask > 0 and s.bid > 0:
                    spread2 = (s.bid - f.ask) / f.ask
                    spread2_bps = spread2 * 10_000
                    if spread2_bps >= float(min_spread_bps):
                        notional2 = float(min(max_notional_usd, depth_usd(f, "buy"), depth_usd(s, "sell")))
                        if notional2 <= 0:
                            notional2 = float(max_notional_usd) * 0.25
                        fees2 = notional2 * (float(taker_fee_bps) / 10_000.0) * 2.0
                        gross2 = notional2 * spread2 * float(leverage)
                        # If we are long futures, we pay funding when funding_rate > 0 (conservative: treat as penalty)
                        funding_pen = float(max(0.0, float(f.funding_rate))) * notional2
                        lat2 = float(latency_seconds.get(f.venue, 120.0) + latency_seconds.get(s.venue, 120.0))
                        risk2 = _sigmoid((lat2 - 180.0) / 120.0)
                        risk_penalty2 = risk2 * 0.20 * abs(gross2)
                        net2 = gross2 - fees2 - funding_pen - risk_penalty2
                        if net2 >= float(min_net_profit_usd):
                            opp2 = ArbitrageOpportunity(
                                arb_type="futures_spot",
                                symbol=symbol,
                                buy_venue=f.venue,
                                sell_venue=s.venue,
                                buy_product="futures",
                                sell_product="spot",
                                entry_buy=float(f.ask),
                                entry_sell=float(s.bid),
                                spread_pct=float(spread2 * 100.0),
                                funding_rate_buy=float(f.funding_rate),
                                funding_rate_sell=0.0,
                                est_net_profit_usd=float(net2),
                                liquidity_depth_usd=float(notional2),
                                transfer_latency_risk_score=float(risk2),
                                created_at_ms=_now_ms(),
                                confidence=float(min(0.95, 0.5 + 0.4 * max(0.0, spread2_bps / 100.0))),
                                meta={"fees_usd": fees2, "funding_penalty_usd": funding_pen, "risk_penalty_usd": risk_penalty2},
                            )
                            k2 = opp2.key()
                            self._touch(k2)
                            opp2.pair_lifetime_sec = self._lifetime_sec(k2)
                            out.append(opp2)

        # 2) futures-futures
        for a in fut:
            for b in fut:
                if a.venue == b.venue:
                    continue
                # Buy a (ask) sell b (bid)
                if a.ask <= 0 or b.bid <= 0:
                    continue
                spread = (b.bid - a.ask) / a.ask
                spread_bps = spread * 10_000
                if spread_bps < float(min_spread_bps):
                    continue

                notional = float(max_notional_usd) * 0.25
                fees = notional * (float(taker_fee_bps) / 10_000.0) * 2.0
                gross = notional * spread * float(leverage)

                # Funding differential: long a, short b
                # If funding positive, longs pay, shorts receive (typical); use differential conservatively.
                fund = float(max(0.0, float(b.funding_rate) - float(a.funding_rate))) * notional

                lat = float(latency_seconds.get(a.venue, 120.0) + latency_seconds.get(b.venue, 120.0))
                risk = _sigmoid((lat - 180.0) / 120.0)
                risk_penalty = risk * 0.20 * abs(gross)
                net = gross - fees + fund - risk_penalty
                if net < float(min_net_profit_usd):
                    continue

                opp = ArbitrageOpportunity(
                    arb_type="futures_futures",
                    symbol=symbol,
                    buy_venue=a.venue,
                    sell_venue=b.venue,
                    buy_product="futures",
                    sell_product="futures",
                    entry_buy=float(a.ask),
                    entry_sell=float(b.bid),
                    spread_pct=float(spread * 100.0),
                    funding_rate_buy=float(a.funding_rate),
                    funding_rate_sell=float(b.funding_rate),
                    est_net_profit_usd=float(net),
                    liquidity_depth_usd=float(notional),
                    transfer_latency_risk_score=float(risk),
                    created_at_ms=_now_ms(),
                    confidence=float(min(0.95, 0.55 + 0.35 * max(0.0, spread_bps / 100.0))),
                    meta={"fees_usd": fees, "funding_bonus_usd": fund, "risk_penalty_usd": risk_penalty},
                )
                k = opp.key()
                self._touch(k)
                opp.pair_lifetime_sec = self._lifetime_sec(k)
                out.append(opp)

        # Sort best-first
        out.sort(key=lambda o: float(o.est_net_profit_usd), reverse=True)
        return out
