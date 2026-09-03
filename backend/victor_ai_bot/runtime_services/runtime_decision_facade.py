from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, List, Optional

from ..canonical_decision_context import CanonicalDecisionContext
from ..decision_context_bridge import build_decision_context
from ..models import Opportunity
from ..portfolio_optimizer import opportunity_route_ready
from ..rpc import JsonRpcClient
from .profitability_truth import inspect_profit_after_costs_truth, opportunity_profit_sort_key

_SAFE_DECISION_EXCEPTIONS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _coerce_nonnegative_int(value: Any, default: int | None = 0) -> int | None:
    if value in (None, ""):
        return default
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default
    if not amount.is_finite():
        return default
    try:
        return max(0, int(amount))
    except (OverflowError, ValueError):
        return default


class RuntimeDecisionFacade:
    """Execution-safety wrapper compatibility facade.

    This isolates small, non-loop execution-adjacent wrappers away from
    RuntimeBundle's orchestration monolith while preserving the existing
    compatibility surface used by admission, auto-execution, and runtime tick
    failure accounting.
    """

    cfg: Any
    metrics: Any
    _cb: Any
    _decision: Any
    _errors: list[str]
    _opps: list[Opportunity]
    _pending: dict[str, Any]
    _auto_queue: list[str]
    _auto_trading: bool
    _exec_task: asyncio.Task[Any] | None
    _spread_opps: list[Any]
    _spread_last: dict[str, Any]
    _engine_last: dict[str, Any]
    _state_lock: Any

    def capital_engine_state(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _execute_auto(self, opp: Opportunity, bn: int, decision: Any = None) -> Any:
        raise NotImplementedError

    async def _annotate_can_execute(self, rpc: JsonRpcClient, opps: List[Opportunity]) -> None:
        raise NotImplementedError

    @staticmethod
    def _empty_engine_snapshot() -> dict[str, Any]:
        return {
            "items": [],
            "capabilities": {},
            "summary": {"engines": []},
        }

    @staticmethod
    def _opp_is_exec_ready(opp: Opportunity) -> bool:
        if not bool(getattr(opp, "can_execute", False)):
            return False
        safety = (getattr(opp, "meta", None) or {}).get("safety") or {}
        if not bool(safety.get("exec_ready", False)):
            return False
        route_ready, _route_reason, _route_reason_codes = opportunity_route_ready(opp)
        if not bool(route_ready):
            return False
        truth = inspect_profit_after_costs_truth(opp)
        return bool(truth.verified and truth.positive)

    def _scale_opportunity(self, opp: Opportunity, size_mult: float) -> Opportunity:
        service = getattr(self, "_execution_service", None)
        return service.scale_opportunity(opp, size_mult) if service is not None else opp

    def _record_tick_failure(self, error: Exception) -> None:
        self.metrics.last_error = str(error)
        self._errors.append(str(error))
        try:
            self.metrics.failed_ticks += 1
        except (AttributeError, asyncio.QueueFull, RuntimeError, TypeError, ValueError):
            pass

    async def _clear_tick_state_after_failure(self) -> None:
        lock = getattr(self, "_state_lock", None)
        if lock is None:
            self._opps = []
        else:
            async with lock:
                self._opps = []
        self._spread_opps = []
        self._spread_last = {}
        self._engine_last = self._empty_engine_snapshot()

    async def _contain_tick_failure(self, error: Exception) -> None:
        self._record_tick_failure(error)
        await self._clear_tick_state_after_failure()

    def _safe_decide_opportunities(
        self,
        opps: List[Opportunity],
        *,
        current_block: int,
        pending_txs: int,
        auto_enabled: bool,
        gas_budget_remaining_wei: int,
    ) -> Optional[Any]:
        capital_state: dict[str, Any] = {}
        capital_budget_remaining_wei = None
        family_capital_remaining_wei: dict[str, int] = {}
        try:
            capital_state = (
                self.capital_engine_state() if hasattr(self, "capital_engine_state") else {}
            )
            capital_engine = dict((capital_state or {}).get("capital_engine") or {})
            raw_capital_budget = capital_engine.get("deployable_bankroll_wei")
            if raw_capital_budget not in (None, ""):
                capital_budget_remaining_wei = _coerce_nonnegative_int(raw_capital_budget, None)
            family_capital_remaining_wei = {
                str(k): int(parsed_value)
                for k, raw_value in dict(capital_engine.get("family_allocations_wei") or {}).items()
                if str(k or "")
                if (parsed_value := _coerce_nonnegative_int(raw_value, None)) is not None
            }
        except _SAFE_DECISION_EXCEPTIONS:
            capital_budget_remaining_wei = None
            family_capital_remaining_wei = {}
        try:
            decision = self._decision.annotate_and_decide(
                opps,
                current_block=int(current_block),
                pending_txs=int(pending_txs),
                auto_enabled=bool(auto_enabled),
                cfg=self.cfg,
                gas_budget_remaining_wei=int(gas_budget_remaining_wei),
                capital_budget_remaining_wei=capital_budget_remaining_wei,
                family_capital_remaining_wei=family_capital_remaining_wei,
            )

            # Phase 7: create the canonical context exactly at the runtime
            # decision boundary, after capital authority has been read.
            chosen = None
            if decision is not None and getattr(decision, "opp_id", ""):
                chosen = next(
                    (o for o in opps if str(getattr(o, "id", "")) == str(decision.opp_id)),
                    None,
                )
            if chosen is not None:
                context = build_decision_context(
                    opportunity=chosen,
                    current_block=int(current_block),
                    capital_engine_state=capital_state,
                    ai_recommendation={
                        "action": str(getattr(decision, "action", "") or ""),
                        "confidence": float(getattr(decision, "p_success", 0.0) or 0.0),
                        "rationale": str(getattr(decision, "reason", "") or ""),
                        "model": str(getattr(self.cfg.execution, "brain_mode", "") or ""),
                    },
                    latency={
                        "gas_mode": str(getattr(decision, "gas_mode", "standard") or "standard"),
                    },
                )
                if isinstance(getattr(chosen, "meta", None), dict):
                    chosen.meta["decision_context"] = context.to_dict()
                # TradeDecision is intentionally an open dataclass, so retain
                # the object itself for execution without changing old callers.
                decision.decision_context = context
                decision.decision_lineage = context.lineage()
            return decision
        except _SAFE_DECISION_EXCEPTIONS as e:
            self._errors.append(f"decision_engine_failed:{e}")
            return None

    async def _safe_annotate_can_execute(self, rpc: JsonRpcClient, opps: List[Opportunity]) -> None:
        try:
            await self._annotate_can_execute(rpc, opps)
        except _SAFE_DECISION_EXCEPTIONS as e:
            self._errors.append(f"annotate_can_execute_failed:{e}")

    def _simple_auto_trade_candidate(self) -> Optional[Opportunity]:
        try:
            max_pending = int(getattr(self.cfg.execution, "max_pending_txs", 1) or 1)
        except _SAFE_DECISION_EXCEPTIONS:
            max_pending = 1
        if max_pending > 0 and len(self._pending) >= max_pending:
            return None

        ready_candidates = [o for o in self._opps if self._opp_is_exec_ready(o)]
        if not ready_candidates:
            return None
        ready_candidates.sort(key=opportunity_profit_sort_key, reverse=True)
        return ready_candidates[0]

    def _decision_auto_trade_candidate(self, decision: Any) -> Optional[Opportunity]:
        chosen = None
        try:
            for oid in list(getattr(decision, "portfolio", []) or self._auto_queue):
                cand = next(
                    (o for o in self._opps if o.id == oid and self._opp_is_exec_ready(o)),
                    None,
                )
                if cand is not None:
                    chosen = cand
                    break
        except _SAFE_DECISION_EXCEPTIONS:
            chosen = None
        if chosen is None:
            chosen = next(
                (o for o in self._opps if o.id == decision.opp_id and self._opp_is_exec_ready(o)),
                None,
            )
        return chosen

    def _maybe_dispatch_auto_trade(self, *, current_block: int, decision: Any = None) -> bool:
        if not self._auto_trading or not self._opps or not self._cb.allow_auto_trading():
            return False
        if self._exec_task is not None and not self._exec_task.done():
            return False

        brain_mode = str(getattr(self.cfg.execution, "brain_mode", "off") or "off")
        chosen = None
        if brain_mode == "off":
            chosen = self._simple_auto_trade_candidate()
        elif decision is not None and getattr(decision, "action", "skip") == "trade":
            chosen = self._decision_auto_trade_candidate(decision)

        if chosen is None:
            return False

        self._exec_task = asyncio.create_task(
            self._execute_auto(
                chosen, int(current_block), decision=decision if brain_mode != "off" else None
            )
        )
        return True
