from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .capital_truth_summary_assembly import CapitalTruthSummaryAssemblyBundle
from .capital_truth_summary_coordination import (
    CapitalTruthSummaryCoordinationBundle,
    assemble_capital_truth_summary,
)


@dataclass(frozen=True)
class CapitalTruthSummaryFinalizationBundle:
    recovery_history: Dict[str, Any]
    final_bundle: CapitalTruthSummaryAssemblyBundle


def finalize_capital_truth_summary(
    *,
    runtime: Any,
    coordination: CapitalTruthSummaryCoordinationBundle,
    initial_bundle: CapitalTruthSummaryAssemblyBundle,
    recovery_repo: Any,
) -> CapitalTruthSummaryFinalizationBundle:
    recovery_history = dict(coordination.recovery_history or {})
    if recovery_repo is None:
        return CapitalTruthSummaryFinalizationBundle(
            recovery_history=recovery_history,
            final_bundle=initial_bundle,
        )

    try:
        recovery_history = recovery_repo.observe(
            component="capital_truth",
            degraded=bool(str(initial_bundle.reconciliation_payload.get("status") or "ok") != "ok"),
            ts_ms=int(coordination.now_ms),
            reason_code=str(initial_bundle.reconciliation_payload.get("status_reason_code") or "ok"),
        )
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
        recovery_history = dict(recovery_history or {})
        return CapitalTruthSummaryFinalizationBundle(
            recovery_history=recovery_history,
            final_bundle=initial_bundle,
        )

    final_bundle = assemble_capital_truth_summary(
        runtime=runtime,
        coordination=coordination,
        recovery_history=recovery_history,
    )
    return CapitalTruthSummaryFinalizationBundle(
        recovery_history=dict(recovery_history or {}),
        final_bundle=final_bundle,
    )
