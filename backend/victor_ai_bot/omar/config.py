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

    # self-play
    self_play_enabled: bool = True
    max_turns_per_episode: int = 50
    self_play_episodes: int = 200
    discount_factor: float = 0.97

    # PPO-ish update (lightweight)
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
        # clamp
        self.role_vector_size = max(8, int(self.role_vector_size))
        self.max_turns_per_episode = max(5, int(self.max_turns_per_episode))
        self.self_play_episodes = max(1, int(self.self_play_episodes))
