from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .capital_truth_dependency_reads import safe_call


@dataclass(frozen=True)
class CapitalTruthRuntimeStateAdapterBundle:
    treasury_state: Dict[str, Any]
    capital_state: Dict[str, Any]
    internal_prime_state: Dict[str, Any]
    launch_state: Dict[str, Any]
    bankroll: Any
    bankroll_state: Any


def _materialized_treasury_state(runtime: Any) -> Dict[str, Any]:
    treasury = getattr(runtime, "_treasury", None)
    repo = getattr(treasury, "_state_repo", None)
    if repo is not None and hasattr(repo, "latest"):
        try:
            latest = repo.latest(state_type="capital_snapshot")
            payload = latest.get("payload") if isinstance(latest, dict) else {}
            if isinstance(payload, dict):
                return dict(payload)
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            pass
    if treasury is not None and hasattr(treasury, "snapshot"):
        try:
            snapshot = treasury.snapshot()
            if isinstance(snapshot, dict):
                return dict(snapshot)
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            pass
    return {}


def _materialized_capital_state(runtime: Any) -> Dict[str, Any]:
    state = getattr(runtime, "_capital_engine_state", None)
    if isinstance(state, dict) and state:
        return dict(state)

    # The treasury capital snapshot is the persisted materialized fallback when the
    # runtime bundle has not yet populated its convenience capital-engine cache.
    # Never fall back to the RuntimeStateFacade: that projection can re-enter canonical
    # capital truth and recreate the dependency cycle this adapter is designed to break.
    treasury_state = _materialized_treasury_state(runtime)
    capital_engine = treasury_state.get("capital_engine")
    if isinstance(capital_engine, dict) and capital_engine:
        return {"capital_engine": dict(capital_engine)}
    return {}


def build_capital_truth_runtime_state_adapters(runtime: Any) -> CapitalTruthRuntimeStateAdapterBundle:
    # Canonical truth assembly must read materialized treasury/capital state rather than
    # their RuntimeStateFacade projections. Those projections can depend on capital truth.
    treasury_state = _materialized_treasury_state(runtime)
    capital_state = _materialized_capital_state(runtime)
    # Internal Prime's facade is an established normalization boundary for its persisted
    # loan state; retain it here because its snapshot does not re-enter capital truth.
    internal_prime_state = safe_call(runtime, "internal_prime_state", default={})
    launch_state = safe_call(runtime, "launch_state", default={})
    bankroll = getattr(runtime, "_bankroll", None)
    bankroll_state = getattr(bankroll, "state", None)
    return CapitalTruthRuntimeStateAdapterBundle(
        treasury_state=dict(treasury_state or {}),
        capital_state=dict(capital_state or {}),
        internal_prime_state=dict(internal_prime_state or {}),
        launch_state=dict(launch_state or {}),
        bankroll=bankroll,
        bankroll_state=bankroll_state,
    )