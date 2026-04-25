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


def build_capital_truth_runtime_state_adapters(runtime: Any) -> CapitalTruthRuntimeStateAdapterBundle:
    treasury_state = safe_call(runtime, "treasury_state", default={})
    capital_state = safe_call(runtime, "capital_engine_state", default={})
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
