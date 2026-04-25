from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RBACConfig:
    """Role-based access control for analytics endpoints.

    This is intentionally lightweight and offline-friendly. It does *not* replace
    proper authn/authz, but provides a deterministic permission gating layer
    suitable for local dashboards.
    """

    enabled: bool = False

    # Optional: map role -> shared secret token for that role.
    # When enabled, requests should provide headers:
    #   X-Role: <ROLE_NAME>
    #   X-Role-Token: <TOKEN>
    role_tokens: Dict[str, str] = field(default_factory=dict)

    # Default role if none is provided.
    default_role: str = "EXECUTIVE_VIEW"

    # Request headers used by the API layer (FastAPI).
    header_role: str = "X-Role"
    header_token: str = "X-Role-Token"


@dataclass
class ReportAutomationConfig:
    """Automated reporting + alerting triggers (advisory)."""

    enabled: bool = True

    # triggers (fractions 0..1 unless otherwise noted)
    drawdown_threshold: float = 0.70
    aggressiveness_escalation_level: str = "HIGH"  # if reached or exceeded -> alert
    threat_monitor_breach: float = 0.85  # generic breach score

    # epoch review cadence (seconds)
    epoch_review_seconds: int = 3600


@dataclass
class QuickSightAnalyticsConfig:
    """QuickSight / Generative BI governance layer config.

    This is a non-destructive observability module:
      - exports BI-compatible datasets (JSONL/CSV)
      - generates dashboard models (JSON)
      - supports deterministic natural-language analytics
      - runs scenario simulations (advisory only)
    """

    enabled: bool = False
    mode: str = "observe"  # observe|suggest

    # cadence and storage
    tick_seconds: float = 10.0
    export_dir: str = "backend/data/analytics"
    export_format: str = "jsonl"  # jsonl|csv
    export_on_tick: bool = False
    max_rows_per_dataset: int = 5000

    # which datasets to maintain
    datasets: List[str] = field(
        default_factory=lambda: [
            "TRADING_METRICS",
            "TREASURY_METRICS",
            "GOVERNANCE_METRICS",
            "REGIME_CONTEXT",
        ]
    )

    # role-based access control
    rbac: RBACConfig = field(default_factory=RBACConfig)

    # report automation
    automation: ReportAutomationConfig = field(default_factory=ReportAutomationConfig)

    # Optional: if true, include recent trades in state snapshots (bounded).
    include_recent_trades: bool = True

    # Safety: analytics cannot trigger execution
    analytics_guardrails: Dict[str, Any] = field(
        default_factory=lambda: {
            "cannot_execute": True,
            "scenario_advisory_only": True,
            "no_secrets": True,
        }
    )
