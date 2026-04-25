from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .intent_schema import TransactionIntent


TIERS = [
    "TIER_1_READ_ONLY",
    "TIER_2_SIMULATION",
    "TIER_3_DELEGATED_EXECUTION",
    "TIER_4_FULL_AUTONOMOUS",
    "TIER_5_MULTI_AGENT_COORDINATED",
]


@dataclass
class WorkflowClassifierConfig:
    capital_threshold_pct: float = 15.0


def classify_workflow_tier(
    intent: TransactionIntent,
    *,
    multi_agent_bundle_detected: bool = False,
    cfg: WorkflowClassifierConfig | None = None,
) -> str:
    cfg = cfg or WorkflowClassifierConfig()
    risk_profile = str(intent.risk_profile or "conservative").lower()
    cap = float(intent.capital_allocation or 0.0)
    if bool(multi_agent_bundle_detected):
        return "TIER_5_MULTI_AGENT_COORDINATED"
    if risk_profile == "aggressive":
        return "TIER_3_DELEGATED_EXECUTION"
    if cap > float(cfg.capital_threshold_pct):
        return "TIER_3_DELEGATED_EXECUTION"
    return "TIER_2_SIMULATION"
