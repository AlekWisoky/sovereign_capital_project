from __future__ import annotations

"""Compatibility surface for legacy single-chain reporting/view typed slices.

This module preserves the declared mypy slice target while the runtime's
single-chain summary/read surfaces now live in dedicated services.
"""

from .runtime_services.capital_truth_service import CapitalTruthService
from .runtime_services.operator_summary_service import OperatorSummaryService
from .runtime_services.state_service import StateService
from .runtime_services.state_summary_service import StateSummaryService

__all__ = [
    "CapitalTruthService",
    "OperatorSummaryService",
    "StateService",
    "StateSummaryService",
]
