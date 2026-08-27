from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, List, Optional

from ..decision_engine import TradeDecision
from ..features import build_features
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

    OMAR is inserted here as the learning decision layer immediately before
    governance/execution. It can only veto or shrink an already executable
    opportunity; it cannot bypass governance or upsize capital.
    """

    cfg: Any
    metrics: Any
    _cb: Any
    _decision: Any
    _omar: Any
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
        return {"items": [], "capabilities": {}, "summary": {"engines": []}}

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
        capital_budget_remaining_wei = None
        family_capital_remaining_wei: dict[str, int] = {}
        try:
            capital_state = self.capital_engine_state() if hasattr(self, "capital_engine_state") else {}
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
            return self._decision.annotate_and_decide(
                opps,
                current_block=int(current_block),
                pending_txs=int(pending_txs),
                auto_enabled=bool(auto_enabled),
                cfg=self.cfg,
                gas_budget_remaining_wei=int(gas_budget_remaining_wei),
                capital_budget_remaining_wei=capital_budget_remaining_wei,
                family_capital_remaining_wei=family_capital_remaining_wei,
            )
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
                cand = next((o for o in self._opps if o.id == oid and self._opp_is_exec_ready(o)), None)
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

    def _wealth_goal_learning_context(self) -> dict[str, Any]:
        try:
            service = getattr(self, "_wealth_goal_service", None)
            if service is not None and hasattr(service, "state"):
                state = service.state(self)
                return dict(state.get("state") or {}) if isinstance(state, dict) else {}
        except _SAFE_DECISION_EXCEPTIONS:
            pass
        return {}

    def _omar_context(self, opp: Opportunity, *, p_success: float, ev_wei: int) -> dict[str, Any]:
        feats = build_features(opp)
        goal = self._wealth_goal_learning_context()
        regime = getattr(self, "_market_regime", {})
        return {
            "margin_ratio": float(feats.margin_ratio),
            "gas_ratio": float(feats.gas_ratio),
            "p_success": float(p_success),
            "drawdown_pct": float(goal.get("drawdownPct") or 0.0),
            "execution_realism": float(goal.get("executionRealismScore") or 0.0),
            "stability": float(goal.get("stabilityScore") or 0.0),
            "goal_gap_pct": max(0.0, float(goal.get("targetReturnPct") or 0.0) - float(goal.get("currentReturnPct") or 0.0)),
            "volatility": float(regime.get("volatility", 0.0) or 0.0) if isinstance(regime, dict) else 0.0,
            "legs": int(feats.legs),
            "ev_wei": int(ev_wei),
            "route_id": str(getattr(opp, "route_id", "") or ""),
            "strategy_family": str((getattr(opp, "meta", {}) or {}).get("strategy_family") or (getattr(opp, "meta", {}) or {}).get("route_family") or ""),
        }

    def _apply_omar_to_candidate(self, opp: Opportunity, decision: Any | None, *, current_block: int) -> tuple[Opportunity | None, Any | None]:
        omar = getattr(self, "_omar", None)
        if omar is None or not bool(getattr(omar, "enabled", False)):
            return opp, decision
        try:
            bm = (getattr(opp, "meta", {}) or {}).get("brain") or {}
            p_success = float(bm.get("p_success") or getattr(decision, "p_success", 0.0) or 0.0)
            ev_wei = int(bm.get("ev_wei") or getattr(decision, "ev_wei", 0) or 0)
            context = self._omar_context(opp, p_success=p_success, ev_wei=ev_wei)
            rec = omar.recommend(context)
            learning_action = str(rec.action) if str(rec.action) in {"WAIT", "DEFEND", "SEEK_OPP", "INCREASE_RISK", "DECREASE_RISK", "EXECUTE"} else "EXECUTE"
            decision_id = f"omar-{getattr(self.cfg.chain, 'name', 'chain')}-{int(current_block)}-{str(getattr(opp, 'id', '') or '')}-{time.time_ns()}"
            if isinstance(getattr(opp, "meta", None), dict):
                brain = dict(opp.meta.get("brain") or {})
                brain["omar_decision_id"] = decision_id
                brain["omar_action"] = learning_action
                brain["omar_state_key"] = rec.state_key
                brain["omar_confidence"] = float(rec.confidence)
                brain["omar_trained"] = bool(rec.trained)
                brain["omar_observations"] = int(rec.observations)
                brain["omar_reason"] = str(rec.reason)
                opp.meta["brain"] = brain
                opp.meta["omar"] = rec.to_dict()
            if rec.veto:
                omar.observe_decision(
                    decision_id=decision_id, opportunity_id=str(getattr(opp, "id", "") or ""), route_id=str(getattr(opp, "route_id", "") or ""),
                    action=learning_action, state_key=str(rec.state_key), context=context,
                    metadata={"current_block": int(current_block), "ev_wei": int(ev_wei), "p_success": float(p_success), "recommendation": rec.to_dict()},
                )
                return None, decision
            if decision is None:
                decision = TradeDecision(
                    action="trade", opp_id=str(getattr(opp, "id", "")), route_id=str(getattr(opp, "route_id", "")),
                    size_mult=float(rec.size_mult), borrow_mult=1.0, gas_mode=str(rec.gas_mode),
                    p_success=p_success, ev_wei=ev_wei, reason="omar_selected", rl_state="", rl_action_index=-1,
                    portfolio=[str(getattr(opp, "id", ""))],
                )
            else:
                decision.size_mult = min(float(getattr(decision, "size_mult", 1.0) or 1.0), float(rec.size_mult))
                decision.borrow_mult = min(float(getattr(decision, "borrow_mult", 1.0) or 1.0), 1.0)
                if str(rec.gas_mode) in {"standard", "fast", "instant"}:
                    decision.gas_mode = str(rec.gas_mode)
            if isinstance(getattr(opp, "meta", None), dict):
                brain = dict(opp.meta.get("brain") or {})
                brain["size_mult_omar"] = float(getattr(decision, "size_mult", 1.0) or 1.0)
                brain["gas_mode_omar"] = str(getattr(decision, "gas_mode", "standard") or "standard")
                opp.meta["brain"] = brain
            omar.observe_decision(
                decision_id=decision_id, opportunity_id=str(getattr(opp, "id", "") or ""), route_id=str(getattr(opp, "route_id", "") or ""),
                action=learning_action, state_key=str(rec.state_key), context=context,
                metadata={"current_block": int(current_block), "ev_wei": int(ev_wei), "p_success": float(p_success), "recommendation": rec.to_dict()},
            )
            return opp, decision
        except _SAFE_DECISION_EXCEPTIONS:
            return opp, decision

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

        chosen, decision = self._apply_omar_to_candidate(chosen, decision if brain_mode != "off" else None, current_block=int(current_block))
        if chosen is None:
            return False

        self._exec_task = asyncio.create_task(self._execute_auto(chosen, int(current_block), decision=decision))
        return True
