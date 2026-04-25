from __future__ import annotations

import asyncio
from typing import Any, Optional

from .summary_read_contract import build_summary_read_contract


class RuntimeMultiruntimeStateFacade:
    _runtimes: dict[str, Any]
    _active_chain: str
    ALLOW_AUTO_ALL: bool
    SNAPSHOT_TIMEOUT_S: float
    _pnl: Any

    """Non-hot-path multichain state/control compatibility helpers.

    These wrappers mirror the active-chain RuntimeBundle interface for
    multichain operator routes and dashboard reads. They are additive shell
    helpers and do not belong in the legacy runtime monolith.
    """

    def chains(self) -> list[str]:
        return list(self._runtimes.keys())

    def set_settings(self, **kwargs) -> None:
        return self._runtimes[self._active_chain].set_settings(**kwargs)

    def set_settings_for(self, chain_name: str, **kwargs) -> bool:
        rt = self._runtimes.get(chain_name)
        if not rt:
            return False
        if (
            (not self.ALLOW_AUTO_ALL)
            and (chain_name != self._active_chain)
            and ("auto_trading" in kwargs)
        ):
            kwargs["auto_trading"] = False
        rt.set_settings(**kwargs)
        return True

    async def snapshot(self) -> dict:
        return await self._runtimes[self._active_chain].snapshot()

    async def admin_snapshot(self) -> dict:
        snap = await self._runtimes[self._active_chain].admin_snapshot()
        snap["multichain"] = {"active": self._active_chain, "chains": self.chains()}
        return snap

    async def snapshot_all(self) -> dict:
        async def one(name, rt):
            try:
                return name, await asyncio.wait_for(rt.snapshot(), timeout=self.SNAPSHOT_TIMEOUT_S)
            except (asyncio.TimeoutError, AttributeError, RuntimeError, TypeError, ValueError) as e:
                return name, {"ok": False, "error": f"snapshot_failed:{e}"}

        pairs = await asyncio.gather(*[one(n, r) for n, r in self._runtimes.items()])
        return {"active": self._active_chain, "chains": {k: v for k, v in pairs}}

    async def execute_opportunity_by_id(
        self,
        opp_id: str,
        *,
        mode: str = "manual",
        amount_in_override: Optional[str] = None,
        force_dry_run: bool = False,
    ):
        return await self._runtimes[self._active_chain].execute_opportunity_by_id(
            opp_id,
            mode=mode,
            amount_in_override=amount_in_override,
            force_dry_run=force_dry_run,
        )

    async def poll_and_update_receipt(self, tx_hash: str) -> dict:
        return await self._runtimes[self._active_chain].poll_and_update_receipt(tx_hash)

    async def pnl_summary(self, window: int = 50) -> dict:
        return await self._runtimes[self._active_chain].pnl_summary(window=window)

    async def pnl_income(self, window: int = 3600) -> dict:
        try:
            return await self._pnl.income_breakdown(window=window)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return {"ok": False, "error": "income_breakdown_failed"}

    def brain_state(self) -> dict:
        return self._runtimes[self._active_chain].brain_state()

    async def summary_all(self) -> dict:
        """Return a lightweight per-chain summary (bounded, fast)."""

        async def one(name, rt):
            try:
                return name, await asyncio.wait_for(rt.summary(), timeout=self.SNAPSHOT_TIMEOUT_S)
            except (asyncio.TimeoutError, AttributeError, RuntimeError, TypeError, ValueError) as e:
                return name, {"ok": False, "error": f"summary_failed:{e}"}

        pairs = await asyncio.gather(*[one(n, r) for n, r in self._runtimes.items()])
        payload: dict[str, Any] = {"active": self._active_chain, "chains": {k: v for k, v in pairs}}
        payload["summaryContract"] = build_summary_read_contract(
            family="multichain_runtime",
            payload=payload,
            source_contracts={
                name: value for name, value in payload["chains"].items() if isinstance(value, dict)
            },
            phase="multichain_runtime_summary",
            read_model="multichain_runtime_summary_projection_v1",
        )
        return payload
