from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..deploy_mode import is_public_mode, public_broadcast_override_enabled

_SAFE_OPERATOR_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeOperatorFacade:
    _pnl: Any
    _ws_clients: list[asyncio.Queue]
    _auto_trading: bool
    _fioa: Any
    cfg: Any
    metrics: Any
    _bankroll: Any
    _decision: Any
    _state_lock: Any
    _state_service: Any
    _eff: Any
    """Operator/runtime control compatibility facade.

    This isolates non-hot-path operator controls, websocket subscription
    helpers, and state snapshot accessors away from RuntimeBundle's
    orchestration loop while preserving the public method surface.
    """

    async def pnl_summary(self, window: int = 50) -> dict:
        return await self._pnl.summary(window=window)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._ws_clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._ws_clients.remove(q)
        except ValueError:
            pass

    def set_settings(
        self,
        *,
        auto_trading: Optional[bool] = None,
        gas_mode: Optional[str] = None,
        send_mode: Optional[str] = None,
        auto_reinvest_enabled: Optional[bool] = None,
        reinvest_rate: Optional[int] = None,
        brain_mode: Optional[str] = None,
        base_borrow_amount: Optional[str] = None,
        dry_run: Optional[bool] = None,
    ) -> None:
        if is_public_mode() and not public_broadcast_override_enabled():
            self._auto_trading = False
            try:
                self.cfg.execution.auto_trading = False
                self.cfg.execution.dry_run = True
                self.cfg.execution.withdraw_mode = "txdata"
            except _SAFE_OPERATOR_EXCEPTIONS:
                pass
        if auto_trading is not None:
            try:
                if (
                    bool(auto_trading)
                    and getattr(self, "_fioa", None) is not None
                    and bool(getattr(self._fioa, "safe_mode", False))
                ):
                    auto_trading = False
            except _SAFE_OPERATOR_EXCEPTIONS:
                pass
            if is_public_mode() and not public_broadcast_override_enabled():
                self._auto_trading = False
            else:
                self._auto_trading = bool(auto_trading)
            try:
                self.cfg.execution.auto_trading = bool(self._auto_trading)
            except _SAFE_OPERATOR_EXCEPTIONS:
                pass
        if gas_mode:
            self.cfg.execution.gas_mode = gas_mode
            self.metrics.gas_mode = gas_mode
        if send_mode:
            self.cfg.execution.send_mode = send_mode
            self.metrics.send_mode = send_mode
        if auto_reinvest_enabled is not None:
            self.cfg.execution.auto_reinvest_enabled = bool(auto_reinvest_enabled)
            self._bankroll.cfg.auto_reinvest_enabled = bool(auto_reinvest_enabled)
        if reinvest_rate is not None:
            rr = max(0, min(100, int(reinvest_rate)))
            self.cfg.execution.reinvest_rate = rr
            self._bankroll.cfg.reinvest_rate_pct = rr
        if base_borrow_amount is not None:
            try:
                v = int(str(base_borrow_amount))
                if v < 0:
                    v = 0
            except _SAFE_OPERATOR_EXCEPTIONS:
                v = 0
            self.cfg.execution.base_borrow_amount = str(v)
            try:
                self._bankroll.cfg.base_borrow_amount_wei = int(v)
            except _SAFE_OPERATOR_EXCEPTIONS:
                pass
        if brain_mode is not None:
            bm = str(brain_mode)
            if bm not in {"off", "shadow", "suggest", "auto"}:
                bm = "off"
            self.cfg.execution.brain_mode = bm
            self._decision.set_mode(bm)

        if dry_run is not None:
            if is_public_mode() and not public_broadcast_override_enabled():
                self.cfg.execution.dry_run = True
            else:
                self.cfg.execution.dry_run = bool(dry_run)

    async def snapshot(self) -> dict:
        async with self._state_lock:
            return await self._state_service.snapshot(self)

    async def summary(self) -> dict:
        async with self._state_lock:
            return await self._state_service.summary(self)

    async def admin_snapshot(self) -> dict:
        async with self._state_lock:
            return await self._state_service.admin_snapshot(self)

    def set_safety(self, **patch) -> None:
        """Update safety config with schema-preserving coercions."""
        s = self.cfg.safety
        for k, v in (patch or {}).items():
            if not hasattr(s, k):
                continue
            if k in ("minProfitAbs", "max_borrow_amount"):
                setattr(s, k, str(v))
            elif k in ("minProfitBps", "slippage_bps"):
                setattr(s, k, int(v))
            elif k in ("require_estimate_gas", "require_simulation"):
                setattr(s, k, bool(v))
            else:
                setattr(s, k, v)

    def efficiency_state(self) -> dict:
        try:
            return self._eff.snapshot()
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            return {}
