from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

import numpy as np

from ..learning.outcome_ledger import CanonicalOutcomeLedger
from ..pathing import canonical_data_dir
from .config import OmarConfig
from .metrics import compute_social_metrics, to_dict
from .operator_intent import OperatorIntentSnapshot
from .role_embedding import encode_role_vector
from .trainer import OmarTrainer


class OmarRuntime:
    """First-class OMAR learning runtime.

    OMAR remains downstream of execution truth: finalized outcomes are read from
    the canonical PnL ledger, joined to the transaction-linked learning context,
    and then used for bounded online policy updates. Governance/execution remain
    authoritative and are never bypassed by this subsystem.
    """

    def __init__(self, cfg: OmarConfig, chain_name: str = "default"):
        self.cfg = cfg
        self.chain_name = str(chain_name or "default")
        self._trainer: Optional[OmarTrainer] = None
        self._ledger: Optional[CanonicalOutcomeLedger] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self.last_social: Dict[str, Any] = {}
        self.last_train: Dict[str, Any] = {}
        self.last_real_learning: Dict[str, Any] = {}
        self.last_observation: Dict[str, Any] = {}
        self._observed_outcome_ids: set[str] = set()
        self._cycle = 0

        self.data_dir = canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))
        self.omar_dir = os.path.join(self.data_dir, "omar")
        os.makedirs(self.omar_dir, exist_ok=True)
        self.audit_path = os.path.join(self.omar_dir, f"omar_audit_{self.chain_name}.jsonl")
        self.policy_path = os.path.join(self.omar_dir, f"policy_{self.chain_name}.json")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def state(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.cfg.enabled),
            "policy_model": self.cfg.policy_model,
            "cycle": self._cycle,
            "last_social": self.last_social,
            "last_train": self.last_train,
            "real_learning": dict(self.last_real_learning),
            "last_observation": dict(self.last_observation),
            "ledger": self._ledger.state() if self._ledger is not None else {},
            "policy": self._trainer.policy.state() if self._trainer is not None else {},
        }

    def _ensure_trainer(self) -> OmarTrainer:
        if self._trainer is None:
            checkpoint = self.policy_path if self.cfg.policy_checkpoint_enabled else None
            self._trainer = OmarTrainer(self.cfg, checkpoint_path=checkpoint)
        return self._trainer

    def observe_outcome(
        self,
        *,
        decision_id: str,
        correlation_id: str,
        execution_id: str,
        settlement_id: str,
        action: str,
        tx_hash: str = "",
        reward_scaled: float = 0.0,
        state_key: str = "unknown",
        role: str = "ARBITRAGE_AGENT",
        latency_ms: float = 0.0,
        outcome_truth_verified: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Observe exactly one canonical settled outcome and update the policy.

        This is a learning sink, not an authority surface. It requires the full
        decision/correlation/execution/settlement identity and only learns from
        a canonical committed outcome. Duplicate settlement observations are
        idempotent by settlement identity.
        """
        if not bool(self.cfg.enabled):
            return {"ok": False, "eligible_for_learning": False, "reason_code": "omar_disabled"}
        required = {
            "decision_id": str(decision_id or "").strip(),
            "correlation_id": str(correlation_id or "").strip(),
            "execution_id": str(execution_id or "").strip(),
            "settlement_id": str(settlement_id or "").strip(),
        }
        if not all(required.values()):
            missing = [key for key, value in required.items() if not value]
            return {
                "ok": False,
                "eligible_for_learning": False,
                "reason_code": "incomplete_learning_identity",
                "missing": missing,
            }
        if not bool(outcome_truth_verified):
            return {
                "ok": False,
                "eligible_for_learning": False,
                "reason_code": "outcome_truth_unverified",
                **required,
            }
        if required["settlement_id"] in self._observed_outcome_ids:
            return {
                "ok": True,
                "eligible_for_learning": False,
                "duplicate": True,
                "reason_code": "duplicate_settlement_observation",
                **required,
            }

        trainer = self._ensure_trainer()
        role_name = str(role or "ARBITRAGE_AGENT").strip() or "ARBITRAGE_AGENT"
        role_vec = trainer._role_embeds.get(role_name)
        if role_vec is None:
            role_vec = encode_role_vector(role_name, self.cfg.role_vector_size)
        state_vec = trainer._state_vector(str(state_key or "unknown"), trainer.state_dim)
        reward = float(np.clip(float(reward_scaled or 0.0), -1_000_000.0, 1_000_000.0))
        action_key = str(action or "WAIT").strip().upper()
        if action_key not in trainer.policy.action_keys:
            action_key = "WAIT"
        action_index = trainer.policy.action_keys.index(action_key)
        stats = trainer.policy.update_from_real_outcome(
            role_vec=role_vec,
            state_vec=state_vec,
            action_index=action_index,
            reward_scaled=reward,
            learning_rate=float(self.cfg.learning_rate),
            clip_epsilon=float(self.cfg.clip_epsilon),
        )
        if self.cfg.policy_checkpoint_enabled:
            trainer.policy.save()

        operator_intent = OperatorIntentSnapshot()
        raw_intent = dict((metadata or {}).get("operator_intent") or {})
        if raw_intent:
            allowed = set(operator_intent.__dataclass_fields__.keys())
            operator_intent = OperatorIntentSnapshot(
                **{key: raw_intent[key] for key in raw_intent if key in allowed}
            )
        observation = {
            "ok": True,
            "eligible_for_learning": True,
            **required,
            "action": action_key,
            "tx_hash": str(tx_hash or ""),
            "reward_scaled": reward,
            "latency_ms": float(latency_ms or 0.0),
            "role": role_name,
            "operator_intent": operator_intent.to_dict(),
            "metadata": dict(metadata or {}),
            "policy_update": dict(stats),
        }
        self._observed_outcome_ids.add(required["settlement_id"])
        if len(self._observed_outcome_ids) > 10000:
            self._observed_outcome_ids = set(list(self._observed_outcome_ids)[-5000:])
        self.last_observation = observation
        self.last_real_learning = {
            "seen": int(self.last_real_learning.get("seen", 0)) + 1,
            "learned": int(self.last_real_learning.get("learned", 0)) + 1,
            "skipped": int(self.last_real_learning.get("skipped", 0)),
            "mean_reward_scaled": reward,
            "last_tx_hash": str(tx_hash or ""),
            "policy_updates": int(trainer.policy.updates),
            "last_settlement_id": required["settlement_id"],
        }
        self._log({"event": "omar_observe_outcome", **observation})
        return dict(observation)

    def _log(self, obj: Dict[str, Any]):
        payload = dict(obj)
        payload["ts"] = time.time()
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    def _learn_real_outcomes(self) -> None:
        if not self._ledger or not self._trainer:
            return
        outcomes = self._ledger.poll(limit=self.cfg.real_outcome_batch_size)
        if not outcomes:
            return
        stats = self._trainer.learn_from_real_outcomes(outcomes)
        self.last_real_learning = dict(stats)
        self._log(
            {
                "event": "omar_real_outcomes_learned",
                "outcome_count": len(outcomes),
                "learning": dict(stats),
                "tx_hashes": [str(x.tx_hash) for x in outcomes],
            }
        )

    def _loop(self):
        if self.cfg.enabled:
            self._ledger = CanonicalOutcomeLedger(
                data_dir=self.data_dir,
                chain=self.chain_name,
                bootstrap_history=self.cfg.outcome_bootstrap_history,
            )
            checkpoint = self.policy_path if self.cfg.policy_checkpoint_enabled else None
            self._trainer = OmarTrainer(self.cfg, checkpoint_path=checkpoint)

            if self.cfg.self_play_enabled:
                stats = self._trainer.train()
                if stats:
                    self.last_train = asdict(stats[-1])
                self._log(
                    {
                        "event": "omar_training_complete",
                        "last_train": self.last_train,
                        "policy": self._trainer.policy.state(),
                    }
                )

        coord_hist = []
        conflict_hist = []
        cap_alloc = {r: 1.0 for r in (self.cfg.roles or [])}
        next_learning_at = 0.0
        while not self._stop.is_set():
            if self._trainer and self._trainer.last_stats:
                st = self._trainer.last_stats
                coord_hist.append(st.mean_coordination)
                conflict_hist.append(st.mean_conflict)
                coord_hist[:] = coord_hist[-200:]
                conflict_hist[:] = conflict_hist[-200:]

            now = time.monotonic()
            if (
                self.cfg.enabled
                and self.cfg.real_outcome_learning_enabled
                and self._trainer
                and self._ledger
                and now >= next_learning_at
            ):
                self._learn_real_outcomes()
                next_learning_at = now + self.cfg.real_outcome_poll_seconds

            m = compute_social_metrics(
                coord_hist=np.array(coord_hist, dtype=float),
                conflict_hist=np.array(conflict_hist, dtype=float),
                capital_alloc=cap_alloc,
            )
            self.last_social = to_dict(m)
            self._log(
                {
                    "event": "omar_social_metrics",
                    **self.last_social,
                    "real_learning": dict(self.last_real_learning),
                }
            )

            self._cycle += 1
            self._stop.wait(1.0)
