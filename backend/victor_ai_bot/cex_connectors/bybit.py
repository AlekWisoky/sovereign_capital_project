from __future__ import annotations
from typing import Any, Dict


def normalize_orderbook(payload: Dict[str, Any]) -> Dict[str, Any]:
    bids = list((payload or {}).get("b") or (payload or {}).get("bids") or [])
    asks = list((payload or {}).get("a") or (payload or {}).get("asks") or [])
    best_bid = float(bids[0][0]) if bids else 0.0
    best_ask = float(asks[0][0]) if asks else 0.0
    return {
        "venue": "bybit",
        "symbol": str((payload or {}).get("symbol") or ""),
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "mid": round((best_bid + best_ask) / 2.0, 8) if best_bid and best_ask else 0.0,
    }
