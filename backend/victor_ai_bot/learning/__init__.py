"""Canonical learning-data interfaces."""

from .borrowing_truth import BorrowingTruth, resolve_borrowing_truth
from .outcome_ledger import CanonicalOutcomeLedger, LearningOutcome

__all__ = [
    "BorrowingTruth",
    "CanonicalOutcomeLedger",
    "LearningOutcome",
    "resolve_borrowing_truth",
]
