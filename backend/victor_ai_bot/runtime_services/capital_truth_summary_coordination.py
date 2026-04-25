from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .capital_truth_service_adapters import (
    CapitalTruthServiceAdapterBundle,
    build_capital_truth_service_adapters,
)
from .capital_truth_summary_assembly import (
    CapitalTruthSummaryAssemblyBundle,
    build_capital_truth_summary_assembly,
)


@dataclass(frozen=True)
class CapitalTruthSummaryCoordinationBundle:
    now_ms: int
    receipt_outcome_truth: Dict[str, Any]
    recovery_history: Dict[str, Any]
    adapters: CapitalTruthServiceAdapterBundle


def build_capital_truth_summary_coordination(
    *,
    service: Any,
    runtime: Any,
    now_ms: int,
) -> CapitalTruthSummaryCoordinationBundle:
    receipt_outcome_truth = service._capital_recovery_state(
        runtime, component="receipt_outcome_truth"
    )
    recovery_history = service._capital_recovery_state(runtime, component="capital_truth")
    adapters = build_capital_truth_service_adapters(service=service, runtime=runtime)
    return CapitalTruthSummaryCoordinationBundle(
        now_ms=int(now_ms),
        receipt_outcome_truth=dict(receipt_outcome_truth or {}),
        recovery_history=dict(recovery_history or {}),
        adapters=adapters,
    )


def assemble_capital_truth_summary(
    *,
    runtime: Any,
    coordination: CapitalTruthSummaryCoordinationBundle,
    recovery_history: Dict[str, Any] | None = None,
) -> CapitalTruthSummaryAssemblyBundle:
    return build_capital_truth_summary_assembly(
        runtime=runtime,
        now_ms=int(coordination.now_ms),
        receipt_outcome_truth=dict(coordination.receipt_outcome_truth or {}),
        recovery_history=dict(
            coordination.recovery_history if recovery_history is None else (recovery_history or {})
        ),
        receipt_settlement_builder=coordination.adapters.receipt_settlement_builder,
        prime_ledger_reconciliation_builder=coordination.adapters.prime_ledger_reconciliation_builder,
        convergence_builder=coordination.adapters.convergence_builder,
    )
