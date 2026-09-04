from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

from ..learning.net_economics import resolve_net_economics
from .advantage import compute_gae, hierarchical_advantage
from .config import OmarConfig
from .env import SelfPlayEnv
from .policy import UnifiedRolePolicy
from .role_embedding import encode_role_vector

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
    def __init__(
        self,
        cfg: OmarConfig,
        state_dim: int = 96,
        checkpoint_path: str | None = None,
    ):
        self.cfg = cfg
        self.state_dim = int(state_dim)
        self.env = SelfPlayEnv(state_dim=self.state_dim, seed=123)
        self.rng = np.random.default_rng(999)
        self.policy = UnifiedRolePolicy(
            state_dim=self.state_dim,
            role_dim=cfg.role_vector_size,
            action_keys=DEFAULT_ACTION_KEYS,
            checkpoint_path=checkpoint_path,
        )

        self._role_names = list(cfg.roles or [])
        self._role_embeds = {
            r: encode_role_vector(r, cfg.role_vector_size) for r in self._role_names
        }
        self.last_stats: OmarTrainStats | None = None
        self.last_real_learning: Dict[str, Any] = {
            "seen": 0,
            "learned": 0,
            "skipped": 0,
            "mean_reward_scaled": 0.0,
            "mean_net_profit_after_costs_usd": 0.0,
            "mean_latency_quality": 0.0,
            "last_tx_hash": "",
        }

    def rotate_roles(self, episode: int):
        if episode % self.cfg.role_rotation_interval == 0:
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

            for role in self._role_names:
                rv = self._role_embeds[role]
                out = self.policy.forward(rv, s)
                a = self.policy.sample_action(out, self.rng)
                actions[role] = a
                values[role] = out.value
                probs[role] = out.action

            step = self.env.step(actions)
            r_team = step.reward
            exec_frac = sum(1 for a in actions.values() if a == "EXECUTE") / max(1, len(actions))
            _r_token = r_team * (0.5 + exec_frac)

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
                R_rows.append(float(r_team))

            coord_hist.append(step.info.get("coordination", 0.0))
            conflict_hist.append(step.info.get("conflict", 0.0))
            s = step.state_vec
            if step.done:
                break

        rewards = np.array(R_rows, dtype=np.float32)
        values = np.array(V_rows, dtype=np.float32)
        adv_turn = compute_gae(rewards, values, gamma=self.cfg.discount_factor)
        adv_token = adv_turn * 0.8
        adv = hierarchical_advantage(
            adv_turn, adv_token, self.cfg.turn_level_weight, self.cfg.token_level_weight
        )
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

    @staticmethod
    def _state_vector(rl_state: str, state_dim: int) -> np.ndarray:
        key = str(rl_state or "unknown")
        return encode_role_vector(f"OMAR_STATE:{key}", state_dim).astype(np.float32)

    @staticmethod
    def _target_action_index(outcome: Any) -> int:
        """Prefer the exact recorded policy action; heuristics are fallback only."""
        try:
            exact = int(getattr(outcome, "rl_action_index", -1))
            if 0 <= exact < len(DEFAULT_ACTION_KEYS):
                return exact
        except (TypeError, ValueError):
            pass

        action = str(getattr(outcome, "action", "") or "").upper()
        if action in DEFAULT_ACTION_KEYS:
            return DEFAULT_ACTION_KEYS.index(action)

        reward = float(getattr(outcome, "reward_scaled_float", 0.0) or 0.0)
        if bool(getattr(outcome, "ok", False)) and reward > 0.0:
            return DEFAULT_ACTION_KEYS.index("EXECUTE")
        context = getattr(outcome, "context", {}) or {}
        brain = context.get("brain") if isinstance(context, dict) else {}
        if isinstance(brain, dict):
            try:
                if float(brain.get("borrow_mult") or 1.0) > 1.0:
                    return DEFAULT_ACTION_KEYS.index("DECREASE_RISK")
            except (TypeError, ValueError):
                pass
        return DEFAULT_ACTION_KEYS.index("WAIT")

    def learn_from_real_outcomes(self, outcomes: Sequence[Any]) -> Dict[str, Any]:
        """Train only from settled economic truth using net profit after costs.

        Gas, financing/prime, slippage and execution costs are included when
        authoritative USD amounts exist. Latency is a bounded delivery-quality
        multiplier on the learning reward; it never changes accounting truth.
        """
        seen = learned = skipped = 0
        rewards: List[float] = []
        net_profits: List[float] = []
        latency_quality: List[float] = []
        last_tx_hash = ""

        for outcome in list(outcomes or []):
            seen += 1
            rl_state = str(getattr(outcome, "rl_state", "") or "")
            if not rl_state:
                skipped += 1
                continue

            economics = resolve_net_economics(outcome)
            if not economics.complete:
                skipped += 1
                continue

            action_index = self._target_action_index(outcome)
            role_name = "ARBITRAGE_AGENT"
            context = getattr(outcome, "context", {}) or {}
            brain = context.get("brain") if isinstance(context, dict) else {}
            if isinstance(brain, dict):
                role_name = str(brain.get("role") or role_name)

            role_vec = self._role_embeds.get(role_name)
            if role_vec is None:
                role_vec = encode_role_vector(role_name, self.cfg.role_vector_size)
            state_vec = self._state_vector(rl_state, self.state_dim)

            stats = self.policy.update_from_real_outcome(
                role_vec=role_vec,
                state_vec=state_vec,
                action_index=action_index,
                reward_scaled=float(economics.learning_reward),
                learning_rate=float(self.cfg.learning_rate),
                clip_epsilon=float(self.cfg.clip_epsilon),
            )
            if float(stats.get("updated", 0.0)) > 0.0:
                learned += 1
                rewards.append(float(economics.learning_reward))
                net_profits.append(float(economics.net_profit_after_costs_usd))
                latency_quality.append(float(economics.latency_quality))
                last_tx_hash = str(getattr(outcome, "tx_hash", "") or "")
            else:
                skipped += 1

        if learned and self.cfg.policy_checkpoint_enabled:
            self.policy.save()

        self.last_real_learning = {
            "seen": int(seen),
            "learned": int(learned),
            "skipped": int(skipped),
            "mean_reward_scaled": float(np.mean(rewards)) if rewards else 0.0,
            "mean_net_profit_after_costs_usd": float(np.mean(net_profits)) if net_profits else 0.0,
            "mean_latency_quality": float(np.mean(latency_quality)) if latency_quality else 0.0,
            "last_tx_hash": last_tx_hash,
            "policy_updates": int(self.policy.updates),
        }
        return dict(self.last_real_learning)

    def train(self) -> List[OmarTrainStats]:
        all_stats = []
        for ep in range(1, self.cfg.self_play_episodes + 1):
            st = self.run_episode(ep)
            all_stats.append(st)
        if self.cfg.policy_checkpoint_enabled:
            self.policy.save()
        return all_stats
