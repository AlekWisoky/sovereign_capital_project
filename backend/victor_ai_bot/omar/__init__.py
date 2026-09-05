"""OMAR learning subsystem.

OMAR may learn from simulated and settled real outcomes, but it never
bypasses governance, execution, or capital authority.
"""

from .config import OmarConfig
from .goal_evidence import GoalEvidenceSnapshot, build_goal_evidence_snapshot
from .operator_intent import OperatorIntentSnapshot, capture_operator_intent
from .real_learning import (
    ActionAttribution,
    CapitalAuthoritySnapshot,
    DecisionLearningRecord,
    ExecutionLearningRecord,
    OmarRealLearningLoop,
    SettledOutcomeRecord,
)
from .runtime import OmarRuntime

__all__ = [
    "OmarConfig",
    "OmarRuntime",
    "OmarRealLearningLoop",
    "CapitalAuthoritySnapshot",
    "DecisionLearningRecord",
    "ExecutionLearningRecord",
    "SettledOutcomeRecord",
    "ActionAttribution",
    "OperatorIntentSnapshot",
    "capture_operator_intent",
    "GoalEvidenceSnapshot",
    "build_goal_evidence_snapshot",
]
