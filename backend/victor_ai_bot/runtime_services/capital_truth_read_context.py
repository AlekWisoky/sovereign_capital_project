from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict

from .capital_state_projection import build_capital_read_surface_payload
from .capital_truth_health_contract import runtime_capital_truth_health

if TYPE_CHECKING:
    from .auxiliary_state_service import AuxiliaryStateService, CapitalTruthSnapshot
    from .state_summary_service import StateSummaryService


@dataclass(frozen=True)
class CapitalTruthReadBaseContext:
    capital_truth: "CapitalTruthSnapshot"
    capital_truth_state: Dict[str, Any]


@dataclass(frozen=True)
class CapitalTruthReadContext:
    capital_truth: "CapitalTruthSnapshot"
    capital_truth_state: Dict[str, Any]
    capital_truth_health: Dict[str, Any]
    capital_surface: Dict[str, Any]

    @property
    def capital_summary(self) -> Dict[str, Any]:
        return dict(self.capital_surface.get("capitalSummary") or {})

    @property
    def capital_contract(self) -> Dict[str, Any]:
        return dict(self.capital_surface.get("capitalContract") or {})

    @property
    def capital_policy(self) -> Dict[str, Any]:
        return dict(self.capital_surface.get("capitalPolicy") or {})

    @property
    def capital_ledger_truth(self) -> Dict[str, Any]:
        return dict(self.capital_surface.get("capitalLedgerTruth") or {})

    @property
    def capital(self) -> Dict[str, Any]:
        return dict(self.capital_surface.get("capital") or {})


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _settlement_marker(runtime: Any) -> str:
    payload = getattr(runtime, "_last_settlement_sync", {}) or {}
    if isinstance(payload, dict):
        return str(
            payload.get("transactionId")
            or payload.get("receiptId")
            or payload.get("txHash")
            or ""
        )
    return ""


def _scope_key(runtime: Any) -> tuple[Any, ...]:
    thread_id = threading.get_ident()
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    task_id = id(task) if task is not None else 0
    metrics = getattr(runtime, "metrics", None)
    bankroll = getattr(runtime, "_bankroll", None)
    bankroll_state = getattr(bankroll, "state", None)
    return (
        thread_id,
        task_id,
        _safe_int(getattr(metrics, "last_block", 0)),
        _safe_int(getattr(bankroll_state, "updated_ts_ms", 0)),
        _safe_int(getattr(bankroll_state, "profit_updated_ts_ms", 0)),
        _safe_int(getattr(bankroll_state, "sizing_updated_ts_ms", 0)),
        _settlement_marker(runtime),
    )


def _base_cache_bucket(runtime: Any) -> Dict[str, Any]:
    attr = "_capital_truth_read_context_cache"
    current = getattr(runtime, attr, None)
    scope = _scope_key(runtime)
    if not isinstance(current, dict) or current.get("scope") != scope:
        current = {"scope": scope, "base": None, "contexts": {}}
        setattr(runtime, attr, current)
    return current


def _build_base_context(
    runtime: Any,
    *,
    auxiliary_state: Any,
    state_summary: Any,
) -> CapitalTruthReadBaseContext:
    cache = _base_cache_bucket(runtime)
    cached = cache.get("base")
    if isinstance(cached, CapitalTruthReadBaseContext):
        return cached
    capital_truth = auxiliary_state.capital_truth(runtime)
    capital_truth_state = dict(state_summary.capital_truth_state(runtime) or {})
    base = CapitalTruthReadBaseContext(
        capital_truth=capital_truth,
        capital_truth_state=capital_truth_state,
    )
    cache["base"] = base
    return base


def _capital_truth_payload_for_health(base: CapitalTruthReadBaseContext) -> Dict[str, Any]:
    state = dict(base.capital_truth_state or {})
    reason_code = str(state.get("reason_code") or "")
    if state and reason_code not in {"", "capital_truth_service_unavailable"}:
        return state
    return dict(base.capital_truth.capital_contract or {})


def build_capital_truth_read_context(
    runtime: Any,
    *,
    auxiliary_state: Any | None = None,
    state_summary: Any | None = None,
    fund_summary: Dict[str, Any] | None = None,
    include_operator_projection: bool = True,
) -> CapitalTruthReadContext:
    if auxiliary_state is None:
        from .auxiliary_state_service import AuxiliaryStateService

        auxiliary = AuxiliaryStateService()
    else:
        auxiliary = auxiliary_state
    if state_summary is None:
        from .state_summary_service import StateSummaryService

        state = StateSummaryService()
    else:
        state = state_summary
    base = _build_base_context(runtime, auxiliary_state=auxiliary, state_summary=state)
    cache = _base_cache_bucket(runtime)
    cache_key = None
    if fund_summary is None:
        cache_key = ("default", bool(include_operator_projection))
        cached_context = cache.get("contexts", {}).get(cache_key)
        if isinstance(cached_context, CapitalTruthReadContext):
            return cached_context
    health = runtime_capital_truth_health(
        runtime,
        capital_truth=_capital_truth_payload_for_health(base),
        fund_summary=fund_summary,
    )
    capital_surface = build_capital_read_surface_payload(
        capital_summary=base.capital_truth.capital_summary,
        capital_contract=base.capital_truth.capital_contract,
        capital_policy=base.capital_truth.capital_policy,
        capital_truth_health=health,
        capital_truth_state=base.capital_truth_state,
        include_operator_projection=include_operator_projection,
    )
    context = CapitalTruthReadContext(
        capital_truth=base.capital_truth,
        capital_truth_state=base.capital_truth_state,
        capital_truth_health=dict(health or {}),
        capital_surface=dict(capital_surface or {}),
    )
    if cache_key is not None:
        cache.setdefault("contexts", {})[cache_key] = context
    return context
