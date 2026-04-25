from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..execution_capture.universal_actions import UniversalAction


def _id(symbol: str, buy_venue: str, sell_venue: str) -> str:
    return hashlib.sha256(f"{symbol}|{buy_venue}|{sell_venue}".encode()).hexdigest()[:16]


def detect_cross_exchange_arbitrage(
    *, books: List[Dict[str, Any]], capital_usd: float
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for buy in books:
        for sell in books:
            if buy is sell or str((buy or {}).get("venue")) == str((sell or {}).get("venue")):
                continue
            buy_ask = float((buy or {}).get("bestAsk") or 0.0)
            sell_bid = float((sell or {}).get("bestBid") or 0.0)
            if buy_ask <= 0 or sell_bid <= 0 or sell_bid <= buy_ask:
                continue
            spread_bps = ((sell_bid - buy_ask) / buy_ask) * 10_000.0
            if spread_bps < 2.0:
                continue
            action = UniversalAction(
                action_id=_id(
                    str((buy or {}).get("symbol") or ""),
                    str((buy or {}).get("venue") or ""),
                    str((sell or {}).get("venue") or ""),
                ),
                family="cex_cex_arb",
                action_type="cross_exchange_spread",
                route_family="cex_cex_arb",
                engine_type="cross_exchange_engine",
                chain="offchain",
                venues=[str((buy or {}).get("venue") or ""), str((sell or {}).get("venue") or "")],
                token_path=[str((buy or {}).get("symbol") or "")],
                expected_profit_usd=round(float(capital_usd) * spread_bps / 10_000.0, 8),
                expected_realized_profit_usd=round(
                    float(capital_usd) * max(0.0, spread_bps - 1.5) / 10_000.0, 8
                ),
                capital_required_usd=float(capital_usd),
                confidence=min(0.95, 0.45 + spread_bps / 50.0),
                lifecycle_stage="paper",
                metadata={
                    "spreadBps": round(spread_bps, 6),
                    "buyVenue": buy.get("venue"),
                    "sellVenue": sell.get("venue"),
                },
            )
            out.append(action.to_dict())
    return out
