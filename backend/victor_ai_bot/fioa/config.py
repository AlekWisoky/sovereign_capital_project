from __future__ import annotations

"""FIOA configuration.

FIOA is intentionally a *non-breaking overlay*. When disabled (default), the
runtime behaves exactly as before.
"""

from dataclasses import dataclass, field
from typing import Dict, List


def _default_agent_scope() -> Dict[str, str]:
    # Mirrors the user-provided spec. Human operator is treated as a privileged
    # identity (optional) to preserve operability in emergencies.
    return {
        "ARBITRAGE_AGENT": "TRADE_EXECUTION",
        "MEV_AGENT": "BUNDLE_OPTIMIZATION",
        "PORTFOLIO_MANAGER": "CAPITAL_ALLOCATION",
        "RISK_GOVERNOR": "RISK_LIMIT_ENFORCEMENT",
        "GOVERNANCE_AGENT": "POLICY_MONITORING",
        # Not in the spec, but useful to avoid breaking existing admin flows.
        "HUMAN_OPERATOR": "*",
    }


@dataclass
class FIOAConfig:
    # Master toggle
    enabled: bool = False

    # Global mode flags (metadata / observability)
    system_mode: str = "AUTONOMOUS_MULTI_AGENT"
    architecture_lock: bool = True
    core_commands_immutable: bool = True

    # Section 1: Operational independence scopes
    agent_scope: Dict[str, str] = field(default_factory=_default_agent_scope)

    # Section 2: Resource autonomy caps (fractions and ratios)
    max_capital_per_agent: float = 0.25
    max_risk_exposure: float = 0.18
    max_leverage: float = 3.0

    # Section 3: Strategy Director
    strategy_director_enabled: bool = True
    strategy_review_interval: int = 300  # cycles (≈ seconds) by default

    # Optional: dynamic sizing (profit-optimized but conservative). Disabled by default.
    enable_dynamic_sizing: bool = False
    target_success_rate: float = 0.75
    sizing_up_step_pct: float = 5.0
    sizing_down_step_pct: float = 10.0
    sizing_min_step_interval_s: float = 60.0

    # Section 4: Confidentiality & segmentation
    confidentiality_enabled: bool = True
    # If strict, CONFIDENTIAL_SIGNAL access is blocked unless agent is GOVERNANCE_AGENT.
    confidentiality_strict: bool = False
    data_access_levels: List[str] = field(default_factory=lambda: [
        "PUBLIC_ANALYTICS",
        "INTERNAL_STRATEGY",
        "CONFIDENTIAL_SIGNAL",
    ])

    # Section 6: Escalation & protection protocol
    escalation_threshold: float = 0.85
    safe_mode_default_ttl_s: float = 120.0

    # Section 7: Audit
    audit_enabled: bool = True
    audit_max_bytes: int = 25_000_000

    # Stress model weights (best-effort heuristic)
    stress_w_fail_streak: float = 0.35
    stress_w_mev: float = 0.25
    stress_w_gas: float = 0.20
    stress_w_rpc: float = 0.10
    stress_w_pending: float = 0.10
