from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .adapters import (
    ExchangeAdapter,
    VenueConfig,
    BinanceSpotAdapter,
    BinanceUsdMFuturesAdapter,
    BybitLinearPerpAdapter,
    OKXSwapAdapter,
    KrakenSpotAdapter,
    KuCoinSpotAdapter,
    KuCoinPerpAdapter,
)


def build_adapter(venue: Dict[str, Any]) -> ExchangeAdapter:
    """Factory for built-in adapters.

    Extensible design:
    - Add new adapters under `aqe/arbitrage/adapters/` and register here.

    Safe default: raises ValueError if venue is unknown.
    """

    name = str(venue.get("name") or "").lower().strip()
    product = str(venue.get("product") or "spot").lower().strip()
    base_url = str(venue.get("base_url") or "")
    fee_bps = int(venue.get("fee_bps") or 10)
    cfg = VenueConfig(name=name, product=product, base_url=base_url, fee_bps=fee_bps, meta=dict(venue))

    # Built-ins
    if name in ("binance", "binance_spot") and product == "spot":
        return BinanceSpotAdapter(cfg)
    if name in ("binance", "binance_futures", "binance_usdm") and product == "futures":
        return BinanceUsdMFuturesAdapter(cfg)
    if name in ("bybit", "bybit_linear") and product == "futures":
        return BybitLinearPerpAdapter(cfg)
    if name in ("okx", "okx_swap") and product == "futures":
        return OKXSwapAdapter(cfg)
    if name in ("kraken", "kraken_spot") and product == "spot":
        return KrakenSpotAdapter(cfg)
    if name in ("kucoin", "kucoin_spot") and product == "spot":
        return KuCoinSpotAdapter(cfg)
    if name in ("kucoin", "kucoin_futures", "kucoin_perp") and product == "futures":
        return KuCoinPerpAdapter(cfg)

    raise ValueError(f"unknown venue adapter: name={name} product={product}")


def list_builtin_venues() -> List[Dict[str, str]]:
    return [
        {"name": "binance", "product": "spot"},
        {"name": "binance", "product": "futures"},
        {"name": "bybit", "product": "futures"},
        {"name": "okx", "product": "futures"},
        {"name": "kraken", "product": "spot"},
        {"name": "kucoin", "product": "spot"},
        {"name": "kucoin", "product": "futures"},
    ]
