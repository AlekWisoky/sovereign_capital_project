from __future__ import annotations

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


_REENTRY_GUARD = "_capital_truth_read_context_building"


def _reentrant_base_context() -> CapitalTruthReadBaseContext:
    # Canonical capital-truth assembly may request treasury state, which may in
    # turn request this read context. Do not recurse into the canonical snapshot.
    from .auxiliary_state_service import CapitalTruthSnapshot

    capital_truth = CapitalTruthSnapshot(
        capital_summary={},
        capital_contract={},
        capital_policy={},
        capital_economic_model={},
        authority={"ok": False, "reason_code": "capital_truth_reentrant_read"},
    )
    return CapitalTruthReadBaseContext(capital_truth=capital_truth, capital_truth_state={})


def _build_base_context(
    runtime: Any,
    *,
    auxiliary_state: Any,
    state_summary: Any,
) -> CapitalTruthReadBaseContext:
    del state_summary
    if bool(getattr(runtime, _REENTRY_GUARD, False)):
        return _reentrant_base_context()

    try:
        setattr(runtime, _REENTRY_GUARD, True)
        capital_truth = auxiliary_state.capital_truth(runtime)
        return CapitalTruthReadBaseContext(
            capital_truth=capital_truth,
            # The canonical snapshot already owns this projection. Do not route
            # through the higher-level state-summary facade from this dependency.
            capital_truth_state=dict(capital_truth.capital_summary or {}),
        )
    finally:
        try:
            setattr(runtime, _REENTRY_GUARD, False)
        except (AttributeError, TypeError, RuntimeError):
            pass


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
    return CapitalTruthReadContext(
        capital_truth=base.capital_truth,
        capital_truth_state=base.capital_truth_state,
        capital_truth_health=dict(health or {}),
        capital_surface=dict(capital_surface or {}),
    )
