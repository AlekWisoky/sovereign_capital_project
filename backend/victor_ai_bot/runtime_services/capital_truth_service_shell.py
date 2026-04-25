from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict

from .capital_truth_summary_assembly import CapitalTruthSummaryAssemblyBundle
from .capital_truth_summary_coordination import (
    CapitalTruthSummaryCoordinationBundle,
    assemble_capital_truth_summary,
    build_capital_truth_summary_coordination,
)
from .capital_truth_summary_finalization import (
    CapitalTruthSummaryFinalizationBundle,
    finalize_capital_truth_summary,
)


@dataclass(frozen=True)
class CapitalTruthServiceShellBundle:
    coordination: CapitalTruthSummaryCoordinationBundle
    initial_bundle: CapitalTruthSummaryAssemblyBundle
    finalization: CapitalTruthSummaryFinalizationBundle
    truth: Dict[str, Any]


def summarize_capital_truth(
    *,
    service: Any,
    runtime: Any,
    now_ms: int | None = None,
) -> Dict[str, Any]:
    shell = build_capital_truth_service_summary(
        service=service,
        runtime=runtime,
        now_ms=int(time.time() * 1000) if now_ms is None else int(now_ms),
    )
    return dict(shell.truth or {})


def build_capital_truth_service_summary(
    *,
    service: Any,
    runtime: Any,
    now_ms: int,
) -> CapitalTruthServiceShellBundle:
    coordination = build_capital_truth_summary_coordination(
        service=service,
        runtime=runtime,
        now_ms=int(now_ms),
    )
    initial_bundle = assemble_capital_truth_summary(
        runtime=runtime,
        coordination=coordination,
    )
    finalization = finalize_capital_truth_summary(
        runtime=runtime,
        coordination=coordination,
        initial_bundle=initial_bundle,
        recovery_repo=service._capital_recovery_repo(runtime),
    )
    return CapitalTruthServiceShellBundle(
        coordination=coordination,
        initial_bundle=initial_bundle,
        finalization=finalization,
        truth=dict(finalization.final_bundle.truth or {}),
    )
