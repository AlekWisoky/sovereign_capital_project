from __future__ import annotations

"""Superstructure configuration (add-only).

The organizational superstructure is **disabled by default** and must be
explicitly enabled under:

  execution.superstructure

Hard constraints:
  - Must not change core command semantics.
  - Only gates/overrides execution when enabled.
"""

from dataclasses import dataclass


@dataclass
class SuperstructureConfig:
    # Master toggle
    enabled: bool = False

    # Mandatory gates when enabled
    require_negotiation: bool = True
    require_capital_auction: bool = True
    require_path_planning: bool = True

    # Negotiation scoring weights
    lambda_risk: float = 1.0
    lambda_latency: float = 0.05
    lambda_funding: float = 0.5
    lambda_reliability: float = 0.6
    lambda_graph_conf: float = 0.4

    # Capital pool configuration
    capital_total_wei: str = "0"  # 0 means derive from task size
    max_capital_fraction_per_task: float = 0.60

    # Stability & risk overrides
    risk_override_drawdown: float = 0.15
    entropy_spike_th: float = 0.25

    # Human authority
    human_enabled: bool = True
    human_high_risk_threshold: float = 0.80
    human_require_approval_for_high_risk: bool = True

    # Phase 18
    enable_stability_monitor: bool = True
    instability_trip_threshold: float = 0.75
    instability_cooldown_s: float = 120.0

    # -------------------------
    # Phase 19+: GMAO Governance overlay (add-only)
    # -------------------------
    gmao_enabled: bool = True

    # Trilemma weights (autonomy vs decentralization vs efficiency)
    gmao_trilemma_autonomy_weight: float = 0.65
    gmao_trilemma_decentralization_weight: float = 0.55
    gmao_trilemma_efficiency_weight: float = 0.75

    # Power distribution & rotation
    gmao_power_decay_rate: float = 0.02
    gmao_max_agent_power: float = 0.40
    gmao_power_rotation_interval: int = 500

    # Reputation / relational contract
    gmao_reputation_decay_rate: float = 0.01
    gmao_reputation_min_threshold: float = 0.30

    # Centralized risk governor
    gmao_risk_threshold_drawdown: float = 0.15
    gmao_risk_threshold_volatility: float = 0.30

    # Decision authority layering
    gmao_risk_human_verified: float = 0.80
    gmao_risk_supervised: float = 0.50

    # Health loop cadence
    gmao_health_interval_s: float = 1.0
