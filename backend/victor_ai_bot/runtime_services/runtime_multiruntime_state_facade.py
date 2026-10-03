from __future__ import annotations

import asyncio
from typing import Any, Optional

from .summary_read_contract import build_summary_read_contract
from .multiruntime_opportunity_selector import MultiRuntimeOpportunitySelector


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

    async def market_pipeline_telemetry_readonly(self) -> dict:
        """Return per-runtime market-pipeline telemetry without changing active state."""
        async def one(name: str, rt: Any):
            try:
                telemetry = dict(rt.market_pipeline_telemetry_state())
                summary = await asyncio.wait_for(rt.summary(), timeout=self.SNAPSHOT_TIMEOUT_S)
                gate = dict(summary.get("auto_trade_gate") or {}) if isinstance(summary, dict) else {}
                recovery = dict(summary.get("auto_trade_recovery") or {}) if isinstance(summary, dict) else {}
                telemetry["admission"] = {
                    "capital": None,
                    "family": str(gate.get("stage") or ""),
                    "treasury": None,
                    "flashloan": None,
                    "execution": {"allowed": bool(gate.get("allowed", False)), "reason_code": str(gate.get("reason_code") or "")},
                    "auto_trade_gate": gate,
                    "recovery": recovery,
                }
                return name, telemetry
            except (asyncio.TimeoutError, AttributeError, RuntimeError, TypeError, ValueError) as exc:
                return name, {"ok": False, "status": "unavailable", "reason_code": "market_pipeline_telemetry_unavailable", "error": str(exc)}
        pairs = await asyncio.gather(*[one(name, rt) for name, rt in self._runtimes.items()])
        jupiter = {"status": "unavailable", "execution_authority": False}
        if hasattr(self, "_solana_jupiter"):
            try:
                jupiter = await asyncio.wait_for(self._solana_jupiter.discover(), timeout=90.0)
            except (asyncio.TimeoutError, AttributeError, RuntimeError, TypeError, ValueError):
                jupiter = self._solana_jupiter.snapshot()
        return {
            "ok": True,
            "active": self._active_chain,
            "chains": {k: v for k, v in pairs},
            "solana_jupiter": jupiter,
            "active_chain_changed": False,
        }

    async def select_best_opportunity_readonly(self) -> dict:
        """Return global opportunity-selection evidence without changing runtime state."""
        selector = MultiRuntimeOpportunitySelector()
        return await selector.select(self._runtimes)

    async def dispatch_selected_auto_trade(self, *, current_block: int) -> bool:
        """Dispatch the globally selected candidate to its owning runtime.

        This is the only bridge from global selection to execution authority.
        It is disabled by default, never changes the active chain, and delegates
        the selected candidate through that runtime's canonical decision and
        execution-preparation path.
        """
        if not bool(getattr(self, "GLOBAL_AUTO_SELECT", False)):
            return False

        selection = await self.select_best_opportunity_readonly()
        runtime_name = str(selection.get("selected_runtime") or "")
        opportunity_id = str(selection.get("selected_opportunity_id") or "")
        if not runtime_name or not opportunity_id:
            return False

        target = self._runtimes.get(runtime_name)
        if target is None:
            return False

        # In global-selection mode, the selected runtime does not need to be
        # the active runtime. Global authority is established by the active
        # runtime's canonical auto-trade control and the selector has already
        # required the selected runtime's gate/recovery/admission/execution
        # evidence. Keep the selected runtime's defensive callback as a final
        # execution-preparation control.
        try:
            if not bool(target._cb.allow_auto_trading()):
                return False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

        try:
            existing_task = getattr(target, "_exec_task", None)
            if existing_task is not None and not existing_task.done():
                return False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

        candidate = next(
            (
                opp
                for opp in list(getattr(target, "_opps", []) or [])
                if str(getattr(opp, "id", "") or "") == opportunity_id
            ),
            None,
        )
        if candidate is None:
            return False

        # Re-enter the canonical decision engine on the selected runtime so
        # decision identity, portfolio policy, and downstream sizing context
        # belong to the runtime that will actually execute.
        try:
            decision = target._safe_decide_opportunities(
                [candidate],
                current_block=int(current_block),
                pending_txs=int(len(getattr(target, "_pending", {}) or {})),
                # Global selection is the auto-trading authority for the
                # selected runtime; the selected runtime itself may remain
                # inactive because active-chain state is not execution
                # ownership in global-selection mode.
                auto_enabled=True,
                gas_budget_remaining_wei=int(target._gas_budget_remaining_wei()),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

        if decision is None or str(getattr(decision, "action", "skip")) != "trade":
            return False

        try:
            candidate, decision = target._apply_omar_to_candidate(
                candidate, decision, current_block=int(current_block)
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        if candidate is None or decision is None:
            return False
        if str(getattr(decision, "action", "skip")) != "trade":
            return False

        target._exec_task = asyncio.create_task(
            target._execute_auto(candidate, int(current_block), decision=decision)
        )
        return True

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
