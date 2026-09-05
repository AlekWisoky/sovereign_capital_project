from __future__ import annotations
from dataclasses import dataclass
from typing import List

DEFAULT_ROLES = [
    "ARBITRAGE_AGENT",
    "MEV_AGENT",
    "PORTFOLIO_MANAGER",
    "RISK_GOVERNOR",
    "FUNDING_SCOUT",
    "GOVERNANCE_AGENT",
]


@dataclass
class OmarConfig:
    enabled: bool = False
    policy_model: str = "UNIFIED_ROLE_POLICY_V1"
    role_embedding_enabled: bool = True
    role_vector_size: int = 64

    # Self-play is an offline bootstrap only. Real learning is the production path.
    self_play_enabled: bool = False
    max_turns_per_episode: int = 50
    self_play_episodes: int = 200
    discount_factor: float = 0.97

    # real-market closed-loop learning
    real_learning_enabled: bool = True
    live_influence_enabled: bool = True
    real_learning_min_observations: int = 20
    real_learning_alpha: float = 0.12
    live_exploration_epsilon: float = 0.0

    # Production promotion is a second, independent gate after data quality.
    performance_promotion_enabled: bool = True
    performance_min_evaluation_observations: int = 50
    performance_min_unique_states: int = 10
    performance_min_mean_advantage_usd: float = 0.0
    performance_min_mean_advantage_bps: float = 5.0
    performance_min_win_rate: float = 0.55
    performance_min_lower_confidence_advantage_usd: float = 0.0

    # PPO-ish update (lightweight offline/self-play)
    learning_rate: float = 3e-4
    clip_epsilon: float = 0.2

    # hierarchical advantage
    token_level_weight: float = 0.4
    turn_level_weight: float = 0.6

    # role rotation
    role_rotation_interval: int = 10

    # human-in-the-loop injection (for training only)
    human_role_enabled: bool = True

    roles: List[str] = None

    def __post_init__(self):
        if self.roles is None:
            self.roles = list(DEFAULT_ROLES)
        self.role_vector_size = max(8, int(self.role_vector_size))
        self.max_turns_per_episode = max(5, int(self.max_turns_per_episode))
        self.self_play_episodes = max(1, int(self.self_play_episodes))
        self.real_learning_min_observations = max(1, int(self.real_learning_min_observations))
        self.real_learning_alpha = max(0.001, min(1.0, float(self.real_learning_alpha)))
        self.live_exploration_epsilon = max(0.0, min(0.25, float(self.live_exploration_epsilon)))
        self.performance_min_evaluation_observations = max(
            1, int(self.performance_min_evaluation_observations)
        )
        self.performance_min_unique_states = max(1, int(self.performance_min_unique_states))
        self.performance_min_mean_advantage_usd = float(self.performance_min_mean_advantage_usd)
        self.performance_min_mean_advantage_bps = float(self.performance_min_mean_advantage_bps)
        self.performance_min_win_rate = max(0.0, min(1.0, float(self.performance_min_win_rate)))
        self.performance_min_lower_confidence_advantage_usd = float(
            self.performance_min_lower_confidence_advantage_usd
        )
