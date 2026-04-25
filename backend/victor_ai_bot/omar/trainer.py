from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any, List
import numpy as np

from .config import OmarConfig
from .role_embedding import encode_role_vector
from .policy import UnifiedRolePolicy
from .env import SelfPlayEnv
from .advantage import compute_gae, hierarchical_advantage

DEFAULT_ACTION_KEYS = (
    "WAIT",
    "DEFEND",
    "SEEK_OPP",
    "INCREASE_RISK",
    "DECREASE_RISK",
    "EXECUTE",
)


@dataclass
class OmarTrainStats:
    episode: int
    mean_reward: float
    mean_coordination: float
    mean_conflict: float
    ppo: Dict[str, float]


class OmarTrainer:
    def __init__(self, cfg: OmarConfig, state_dim: int = 96):
        self.cfg = cfg
        self.state_dim = state_dim
        self.env = SelfPlayEnv(state_dim=state_dim, seed=123)
        self.rng = np.random.default_rng(999)
        self.policy = UnifiedRolePolicy(
            state_dim=state_dim, role_dim=cfg.role_vector_size, action_keys=DEFAULT_ACTION_KEYS
        )

        self._role_names = list(cfg.roles)
        self._role_embeds = {
            r: encode_role_vector(r, cfg.role_vector_size) for r in self._role_names
        }

        self.last_stats: OmarTrainStats | None = None

    def rotate_roles(self, episode: int):
        if episode % self.cfg.role_rotation_interval == 0:
            # shuffle embeddings among roles (role-swap rotation)
            keys = list(self._role_names)
            vals = [self._role_embeds[k].copy() for k in keys]
            self.rng.shuffle(vals)
            self._role_embeds = {k: v for k, v in zip(keys, vals)}

    def run_episode(self, episode: int) -> OmarTrainStats:
        self.rotate_roles(episode)
        s = self.env.reset()

        X_rows = []
        A_rows = []
        OLD_P_rows = []
        V_rows = []
        R_rows = []
        coord_hist = []
        conflict_hist = []

        for _turn in range(self.cfg.max_turns_per_episode):
            actions = {}
            values = {}
            probs = {}

            # generate actions for each role using the same policy
            for role in self._role_names:
                rv = self._role_embeds[role]
                out = self.policy.forward(rv, s)
                a = self.policy.sample_action(out, self.rng)
                actions[role] = a
                values[role] = out.value
                probs[role] = out.action

            step = self.env.step(actions)
            # global reward (team-level)
            r_team = step.reward
            # token-level advantage proxy: reward per "EXECUTE" frequency
            exec_frac = sum(1 for a in actions.values() if a == "EXECUTE") / max(1, len(actions))
            r_token = r_team * (0.5 + exec_frac)

            # store per-role transitions as separate samples
            for role in self._role_names:
                rv = self._role_embeds[role]
                x = np.concatenate([rv, s.astype(np.float32)], axis=0)
                a_key = actions[role]
                a_idx = DEFAULT_ACTION_KEYS.index(a_key)
                old_p = float(probs[role][a_key])
                X_rows.append(x)
                A_rows.append(a_idx)
                OLD_P_rows.append(old_p)
                V_rows.append(values[role])
                # reward: blended
                R_rows.append(float(r_team))

            coord_hist.append(step.info.get("coordination", 0.0))
            conflict_hist.append(step.info.get("conflict", 0.0))
            s = step.state_vec
            if step.done:
                break

        rewards = np.array(R_rows, dtype=np.float32)
        values = np.array(V_rows, dtype=np.float32)
        adv_turn = compute_gae(rewards, values, gamma=self.cfg.discount_factor)
        adv_token = adv_turn * 0.8  # proxy placeholder (can be upgraded)
        adv = hierarchical_advantage(
            adv_turn, adv_token, self.cfg.turn_level_weight, self.cfg.token_level_weight
        )

        # normalize adv
        adv = (adv - adv.mean()) / (adv.std() + 1e-6)

        batch = {
            "X": np.stack(X_rows).astype(np.float32),
            "A": np.array(A_rows, dtype=np.int64),
            "ADV": adv.astype(np.float32),
            "OLD_P": np.array(OLD_P_rows, dtype=np.float32),
            "RET": (adv + values).astype(np.float32),
        }

        ppo = self.policy.update_ppo(
            batch, lr=self.cfg.learning_rate, clip_eps=self.cfg.clip_epsilon
        )

        stats = OmarTrainStats(
            episode=episode,
            mean_reward=float(np.mean(rewards)) if len(rewards) else 0.0,
            mean_coordination=float(np.mean(coord_hist)) if len(coord_hist) else 0.0,
            mean_conflict=float(np.mean(conflict_hist)) if len(conflict_hist) else 0.0,
            ppo=ppo,
        )
        self.last_stats = stats
        return stats

    def train(self) -> List[OmarTrainStats]:
        all_stats = []
        for ep in range(1, self.cfg.self_play_episodes + 1):
            st = self.run_episode(ep)
            all_stats.append(st)
        return all_stats
