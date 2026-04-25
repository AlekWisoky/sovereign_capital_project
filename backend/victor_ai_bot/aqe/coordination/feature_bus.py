from __future__ import annotations

"""SharedFeatureBus.

Bridges the global CAQ-KDS BUS and the UnifiedMarketState. All agents may read
from this bus without creating tight couplings.

This module is additive and must not crash startup.
"""

import time
from typing import Any, Dict

from victor_ai_bot.caq_kds.bus import BUS

from ..unified import UnifiedMarketState

_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


class SharedFeatureBus:
    def __init__(self):
        self.market = UnifiedMarketState()
        self.last_update: Dict[str, Any] = {}
        self.status: Dict[str, Any] = {
            "busRead": "ok",
            "marketIngest": "ok",
            "degraded": False,
        }

    def _refresh_degraded(self) -> None:
        self.status["degraded"] = any(
            self.status.get(key) != "ok" for key in ("busRead", "marketIngest")
        )

    def _set_status(self, key: str, value: str) -> None:
        self.status[key] = str(value or "ok")
        self._refresh_degraded()

    def update_from_bus(self) -> Dict[str, Any]:
        """Ingest the latest BUS snapshot."""
        snap: Dict[str, Any] = {}
        self._set_status("busRead", "ok")
        self._set_status("marketIngest", "ok")
        try:
            bus_snapshot = BUS.snapshot()
        except _SAFE_BUS_EXCEPTIONS:
            self._set_status("busRead", "bus_snapshot_failed")
            bus_snapshot = {}
        if isinstance(bus_snapshot, dict):
            snap = bus_snapshot
        else:
            self._set_status("busRead", "bus_snapshot_invalid")
        try:
            self.market.ingest_bus_snapshot(snap)
        except _SAFE_BUS_EXCEPTIONS:
            self._set_status("marketIngest", "market_ingest_failed")
        self.last_update = {
            "ts": int(time.time()),
            "keys": sorted(list(snap.keys())),
            "status": dict(self.status),
        }
        return self.last_update

    def snapshot(self) -> Dict[str, Any]:
        market = self.market.snapshot()
        status = dict(self.status)
        status["degraded"] = bool(status.get("degraded") or (market.get("status") or {}).get("degraded"))
        return {
            "ts": int(time.time()),
            "market": market,
            "last_update": dict(self.last_update),
            "status": status,
        }
