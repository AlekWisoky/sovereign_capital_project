from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BehaveAgentConfig:
    """BehaveAgent configuration.

    This layer is a non-destructive overlay:
    - can influence scoring and risk posture (scoring only)
    - cannot override hard risk limits
    - cannot execute trades
    - must remain deterministic for the same input state
    """

    enabled: bool = False
    mode: str = "observe"  # observe|suggest

    # Unknown regime fallback behavior
    unknown_regime_fallback: str = "conservative"

    # --- Deterministic regime similarity / clustering ---
    # Confidence floor used by governance/threat escalation. Below this, BehaveAgent
    # recommends conservative fallback and may escalate.
    regime_confidence_floor: float = 0.45

    # If similarity to known regimes is below this threshold, the regime is treated as unknown
    # (or optionally learned into a stable custom regime label when enable_regime_memory is true).
    similarity_threshold: float = 0.72

    # Enable basic similarity clustering / auto-regime memory (deterministic, local-only).
    enable_similarity_clustering: bool = True
    enable_regime_memory: bool = True
    regime_memory_max: int = 200
    regime_memory_path: str = "backend/data/behaveagent/regime_memory.json"

    # --- Deterministic learning loop (strategy↔regime outcomes) ---
    enable_learning_loop: bool = True
    strategy_memory_path: str = "backend/data/behaveagent/strategy_memory.json"
    min_samples_for_boost: int = 8
    max_weight_boost: float = 1.15
    max_weight_penalty: float = 0.85

    # Exploration is deterministic via hashing and capped by capital fraction
    exploration_capital_fraction: float = 0.10

    # Governance transparency requirements
    require_reasoning_log: bool = True
    transparency_min_score: float = 0.60

    # Where to store append-only reasoning logs (relative paths allowed).
    reasoning_log_dir: str = "backend/data/behaveagent"
