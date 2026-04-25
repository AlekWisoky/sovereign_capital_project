from __future__ import annotations


class PlatformError(Exception):
    reason_code = "platform_error"

    def __init__(self, message: str = "", *, reason_code: str | None = None):
        super().__init__(message or reason_code or self.reason_code)
        if reason_code:
            self.reason_code = reason_code


class ExecutionError(PlatformError):
    reason_code = "execution_error"


class AdmissionError(ExecutionError):
    reason_code = "admission_error"


class LaneSelectionError(ExecutionError):
    reason_code = "lane_selection_error"


class SizingError(ExecutionError):
    reason_code = "sizing_error"


class CompetitionRiskError(ExecutionError):
    reason_code = "competition_risk"


class SettlementRiskError(ExecutionError):
    reason_code = "settlement_risk"


class LoanError(ExecutionError):
    reason_code = "loan_error"


class RouteUnavailableError(ExecutionError):
    reason_code = "route_unavailable"


class LedgerConsistencyError(PlatformError):
    reason_code = "ledger_consistency_error"


class ReconciliationError(PlatformError):
    reason_code = "reconciliation_error"


class BorrowLimitError(PlatformError):
    reason_code = "borrow_limit_error"


class CollateralInsufficiencyError(PlatformError):
    reason_code = "collateral_insufficiency"


class CapitalAllocationError(PlatformError):
    reason_code = "capital_allocation_error"


class PrimeNettingError(PlatformError):
    reason_code = "prime_netting_error"


class LaunchStateError(PlatformError):
    reason_code = "launch_state_error"


class InvalidTransitionError(LaunchStateError):
    reason_code = "invalid_transition"


class GovernanceMutationError(PlatformError):
    reason_code = "governance_mutation_error"


class ResearchPromotionError(PlatformError):
    reason_code = "research_promotion_error"
