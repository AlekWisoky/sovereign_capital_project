from __future__ import annotations

import asyncio
import os
from typing import Any

_SAFE_TICK_PREPARE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
)

_SAFE_TICK_PREPARE_BREAKER_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeTickPrepareFacade:
    """Compatibility facade for early per-block tick preparation.

    This isolates the block-number handling and per-block preparation path from
    RuntimeBundle._loop while preserving the same process-boundary containment
    and no-trade semantics.
    """

    async def _prepare_tick_iteration(self, *, rpc: Any) -> int | None:
        bn = await rpc.block_number()
        if bn is None:
            self.metrics.last_error = "block_number failed"
            # A block/RPC failure happens before _scan_primary_opportunities,
            # so without an explicit lifecycle record the market-pipeline API
            # looks like a healthy zero-opportunity scan. Preserve the actual
            # boundary and provider identity for diagnosis and failover.
            try:
                from urllib.parse import urlsplit
                rpc_url = str(getattr(rpc, "url", "") or "")
                host = str(urlsplit(rpc_url).hostname or "") if rpc_url else ""
                snapshot = {}
                manager = getattr(self, "rpc_manager", None)
                if manager is not None and hasattr(manager, "snapshot"):
                    snapshot = dict(manager.snapshot() or {})
                self._market_pipeline_telemetry = {
                    "last_scan": int(__import__("time").time() * 1000),
                    "last_block": int(getattr(self.metrics, "last_block", 0) or 0),
                    "scan_status": "blocked_before_scan",
                    "scan_error": "bootstrap_block_number_failed",
                    "rpc": {
                        "endpoint": rpc_url,
                        "provider": host,
                        "ok": False,
                    },
                    "quotes": {
                        "requests": 0,
                        "successes": 0,
                        "failure_reasons": {"bootstrap_block_number_failed": 1},
                    },
                    "discovery": {},
                    "route_universe": {},
                    "size_economic_matrix": [],
                    "adaptive_size_discovery": {},
                }
                if snapshot:
                    self._market_pipeline_telemetry["rpc"]["manager_snapshot"] = snapshot
            except _SAFE_TICK_PREPARE_EXCEPTIONS:
                pass
            try:
                self.metrics.failed_ticks += 1
            except _SAFE_TICK_PREPARE_BREAKER_EXCEPTIONS:
                pass
            try:
                storm = self._anomaly.observe_rpc_error(
                    ok=False,
                    threshold=int(os.environ.get("VICTOR_RPC_ERR_STREAK", "5")),
                )
                if storm and getattr(self, "_cc", None) is not None:
                    c = getattr(self._cc, "controls", None)
                    if c is not None and bool(getattr(c, "chaos_breakers_enabled", True)):
                        setattr(c, "paused", True)
                        setattr(c, "defensive_mode", True)
                        setattr(c, "reduce_exposure_half", True)
                        self._auto_trading = False
                        try:
                            self._cc.persist_controls()
                            self._cc.audit.append(
                                "breaker_trip",
                                {
                                    "kind": "rpc_error_storm",
                                    "threshold": int(
                                        os.environ.get("VICTOR_RPC_ERR_STREAK", "5")
                                    ),
                                },
                                actor="system",
                                reason="rpc_error_storm",
                            )
                        except _SAFE_TICK_PREPARE_BREAKER_EXCEPTIONS:
                            pass
            except _SAFE_TICK_PREPARE_BREAKER_EXCEPTIONS:
                pass
            await asyncio.sleep(1.0)
            return None

        try:
            self._anomaly.observe_rpc_error(ok=True)
        except _SAFE_TICK_PREPARE_EXCEPTIONS:
            pass

        if bn == self.metrics.last_block:
            await asyncio.sleep(0.4)
            return None

        self.metrics.last_block = bn
        try:
            self.cache.reset_if_new_block(int(self.cfg.chain.chain_id), int(bn))
        except _SAFE_TICK_PREPARE_EXCEPTIONS:
            pass

        try:
            control = getattr(self, "_runtime_control_service", None)
            if control is not None and hasattr(control, "apply_brain_mode_override"):
                control.apply_brain_mode_override(self)
        except _SAFE_TICK_PREPARE_EXCEPTIONS:
            pass

        return int(bn)
