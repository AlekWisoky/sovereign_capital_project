"""OMAR learning subsystem.

OMAR may learn from simulated and settled real outcomes, but it never
bypasses governance, execution, or capital authority.
"""

from .config import OmarConfig
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

try:
    from .production_learning_hook import install_production_learning_hooks

    install_production_learning_hooks()
except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
    pass

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
    "install_production_learning_hooks",
]
