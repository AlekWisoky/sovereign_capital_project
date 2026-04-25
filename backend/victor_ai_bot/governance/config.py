from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GovernanceConfig:
    enabled: bool = True
    # enforce governance gate on auto trading
    enforce_on_auto: bool = True
    # enforce gate on manual endpoints
    enforce_on_manual: bool = True

    # Human approval controls
    admin_key_env: str = "VICTOR_ADMIN_KEY"
    require_human_for_tier5: bool = True
    require_human_for_maximum_aggressiveness: bool = True

    # Security thresholds
    z_score_limit: float = 6.0
    anomaly_score_limit: float = 0.85

    # Determinism
    deterministic_ids: bool = True
