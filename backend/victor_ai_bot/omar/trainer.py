from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

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
            "last_tx_hash": "",
            "mean_expectation_error_wei": "0",
            "mean_expectation_error_pct": 0.0,
            "mean_latency_error_ms": 0.0,
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
        """Translate a settled trade into OMAR's action vocabulary."""
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

    @staticmethod
    def _real_learning_reward(outcome: Any) -> tuple[float, float, float, int]:
        """Build a bounded reward that teaches profitability and calibration."""
        amount = max(1, int(getattr(outcome, "amount_in_wei", 0) or 0))
        expected = int(getattr(outcome, "expected_profit_after_costs_wei", 0) or 0)
        realized = int(getattr(outcome, "realized_profit_after_gas_wei", 0) or 0)
        base = float(getattr(outcome, "reward_scaled_float", 0.0) or 0.0)
        error = realized - expected
        error_pct = (float(error) / abs(expected) * 100.0) if expected else 0.0
        latency = float(getattr(outcome, "latency_ms", 0.0) or 0.0)
        context = getattr(outcome, "context", {}) or {}
        decision_context = context.get("decisionContext") if isinstance(context, dict) else {}
        if not isinstance(decision_context, dict):
            decision_context = context.get("decision_context") if isinstance(context, dict) else {}
        economic = (
            decision_context.get("economic_context") if isinstance(decision_context, dict) else {}
        )
        if not isinstance(economic, dict):
            economic = context.get("economicContext") if isinstance(context, dict) else {}
        if not isinstance(economic, dict):
            economic = context.get("economic_context") if isinstance(context, dict) else {}
        # The canonical execution path currently stores the snapshot under
        # brain.economic_context so the existing receipt-learning envelope can
        # carry it without widening the ledger schema.
        if not isinstance(economic, dict) or not economic:
            economic = brain.get("economic_context") if isinstance(brain, dict) else {}
        expected_latency = float((economic or {}).get("expected_latency_ms") or 0.0)
        latency_error = latency - expected_latency
        overestimate_penalty = max(0.0, -float(error) / float(amount) * 1_000_000.0)
        calibrated = base - 0.25 * overestimate_penalty
        return float(calibrated), float(error_pct), float(latency_error), int(error)

    def learn_from_real_outcomes(self, outcomes: Sequence[Any]) -> Dict[str, Any]:
        """Train OMAR from finalized real-market outcomes."""
        seen = learned = skipped = 0
        rewards: List[float] = []
        errors: List[int] = []
        error_pcts: List[float] = []
        latency_errors: List[float] = []
        last_tx_hash = ""
        for outcome in list(outcomes or []):
            seen += 1
            rl_state = str(getattr(outcome, "rl_state", "") or "")
            if not rl_state:
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
            reward, error_pct, latency_error, error = self._real_learning_reward(outcome)
            stats = self.policy.update_from_real_outcome(
                role_vec=role_vec,
                state_vec=state_vec,
                action_index=action_index,
                reward_scaled=float(reward),
                learning_rate=float(self.cfg.learning_rate),
                clip_epsilon=float(self.cfg.clip_epsilon),
            )
            if float(stats.get("updated", 0.0)) > 0.0:
                learned += 1
                rewards.append(float(stats.get("reward_scaled", 0.0) or 0.0))
                errors.append(int(error))
                error_pcts.append(float(error_pct))
                latency_errors.append(float(latency_error))
                last_tx_hash = str(getattr(outcome, "tx_hash", "") or "")
            else:
                skipped += 1

        if learned and self.cfg.policy_checkpoint_enabled:
            self.policy.save()
        mean_reward = float(np.mean(rewards)) if rewards else 0.0
        mean_error = float(np.mean(errors)) if errors else 0.0
        mean_error_pct = float(np.mean(error_pcts)) if error_pcts else 0.0
        mean_latency_error = float(np.mean(latency_errors)) if latency_errors else 0.0
        self.last_real_learning = {
            "seen": int(seen),
            "learned": int(learned),
            "skipped": int(skipped),
            "mean_reward_scaled": mean_reward,
            "last_tx_hash": last_tx_hash,
            "policy_updates": int(self.policy.updates),
            "mean_expectation_error_wei": str(int(round(mean_error))),
            "mean_expectation_error_pct": mean_error_pct,
            "mean_latency_error_ms": mean_latency_error,
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
