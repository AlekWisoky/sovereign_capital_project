from __future__ import annotations

from dataclasses import asdict
import json
import os
import threading
import time
from typing import Any, Dict, Mapping, Optional

import numpy as np

from ..learning.outcome_ledger import CanonicalOutcomeLedger
from ..pathing import canonical_data_dir
from .config import OmarConfig
from .metrics import compute_social_metrics, to_dict
from .operator_intent import OperatorIntentSnapshot
from .real_learning import ActionAttribution, OmarRealLearningLoop
from .trainer import DEFAULT_ACTION_KEYS, OmarTrainer


class OmarRuntime:
    """First-class OMAR learning runtime.

    OMAR is downstream of execution truth. Governance, capital authority, and
    execution remain authoritative; OMAR only observes settled results and
    updates its policy from attributable outcomes.
    """

    def __init__(self, cfg: OmarConfig, chain_name: str = "default"):
        self.cfg = cfg
        self.chain_name = str(chain_name or "default")
        self._trainer: Optional[OmarTrainer] = None
        self._ledger: Optional[CanonicalOutcomeLedger] = None
        self._real_learning: Optional[OmarRealLearningLoop] = None
        self._bound_runtime: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.last_social: Dict[str, Any] = {}
        self.last_train: Dict[str, Any] = {}
        self.last_real_learning: Dict[str, Any] = {}
        self._cycle = 0
        self.data_dir = canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))
        self.omar_dir = os.path.join(self.data_dir, "omar")
        os.makedirs(self.omar_dir, exist_ok=True)
        self.audit_path = os.path.join(self.omar_dir, f"omar_audit_{self.chain_name}.jsonl")
        self.policy_path = os.path.join(self.omar_dir, f"policy_{self.chain_name}.json")

    def bind_runtime(self, runtime: Any) -> None:
        """Bind the production runtime as a read-only capital authority provider."""
        self._bound_runtime = runtime
        self._real_learning = OmarRealLearningLoop(
            chain_name=self.chain_name,
            data_dir=self.omar_dir,
            policy_updater=self._apply_real_learning_update,
            capital_authority_reader=self._read_capital_authority,
        )

    def _read_capital_authority(self) -> Dict[str, Any]:
        runtime = self._bound_runtime
        reader = getattr(runtime, "capital_engine_state", None) if runtime is not None else None
        if not callable(reader):
            return {
                "authority_id": "unavailable",
                "status": "unavailable",
                "freshness_class": "unavailable",
                "source": "capital_engine_state",
                "reason_codes": ["capital_authority_reader_unavailable"],
            }
        raw = reader()
        return dict(raw) if isinstance(raw, Mapping) else {}

    @staticmethod
    def _action_index(action: str) -> int:
        text = str(action or "").strip().upper()
        text = {"TRADE": "EXECUTE"}.get(text, text)
        try:
            return DEFAULT_ACTION_KEYS.index(text)
        except ValueError:
            return -1

    def _apply_real_learning_update(self, attribution: ActionAttribution) -> Dict[str, Any]:
        trainer = self._trainer
        loop = self._real_learning
        if trainer is None or loop is None:
            return {"updated": False, "reason_code": "omar_trainer_not_ready"}
        decision = loop._decisions.get(attribution.decision_id)
        if decision is None:
            return {"updated": False, "reason_code": "decision_context_missing"}
        rl_state = str(decision.state.get("rl_state") or decision.state.get("state") or "")
        if not rl_state:
            return {"updated": False, "reason_code": "learning_state_missing"}
        action_index = self._action_index(attribution.action)
        if action_index < 0:
            return {"updated": False, "reason_code": "action_unmapped"}
        role_name = "ARBITRAGE_AGENT"
        role_vec = trainer._role_embeds.get(role_name)
        if role_vec is None:
            from .role_embedding import encode_role_vector

            role_vec = encode_role_vector(role_name, trainer.cfg.role_vector_size)
        authority = decision.capital_authority
        denominator = max(1, int(authority.allocatable_wei or authority.available_wei or 1))
        reward_scaled = float(attribution.reward_wei) / float(denominator) * 1_000_000.0
        stats = trainer.policy.update_from_real_outcome(
            role_vec=role_vec,
            state_vec=trainer._state_vector(rl_state, trainer.state_dim),
            action_index=action_index,
            reward_scaled=reward_scaled,
            learning_rate=float(trainer.cfg.learning_rate),
            clip_epsilon=float(trainer.cfg.clip_epsilon),
        )
        if bool(stats.get("updated", 0.0)) and trainer.cfg.policy_checkpoint_enabled:
            trainer.policy.save()
        return {
            **dict(stats),
            "updated": bool(stats.get("updated", 0.0)),
            "decision_id": attribution.decision_id,
            "correlation_id": attribution.correlation_id,
            "execution_id": attribution.execution_id,
            "settlement_id": attribution.settlement_id,
            "capital_authority_source": authority.source,
        }

    def observe_decision(self, *, decision_id: str, correlation_id: str, action: str, opp_id: str = "", route_id: str = "", policy_version: str = "", state: Optional[Dict[str, Any]] = None, operator_intent: Optional[OperatorIntentSnapshot] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.cfg.enabled or self._real_learning is None:
            return {"ok": False, "reason_code": "omar_real_learning_disabled"}
        record = self._real_learning.record_decision(
            decision_id=decision_id, correlation_id=correlation_id, action=action,
            opp_id=opp_id, route_id=route_id, policy_version=policy_version,
            state=state or {}, operator_intent=operator_intent, metadata=metadata or {},
        )
        return {"ok": True, "decision_id": record.decision_id, "correlation_id": record.correlation_id}

    def observe_execution(self, *, decision_id: str, correlation_id: str, execution_id: str, status: str, action: str, tx_hash: str = "", fill_quantity: float = 0.0, fill_price: float = 0.0, slippage_bps: float = 0.0, gas_wei: int = 0, latency_ms: float = 0.0, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.cfg.enabled or self._real_learning is None:
            return {"ok": False, "reason_code": "omar_real_learning_disabled"}
        record = self._real_learning.bind_execution(
            decision_id=decision_id, correlation_id=correlation_id, execution_id=execution_id,
            status=status, action=action, tx_hash=tx_hash, fill_quantity=fill_quantity,
            fill_price=fill_price, slippage_bps=slippage_bps, gas_wei=gas_wei,
            latency_ms=latency_ms, metadata=metadata or {},
        )
        return {"ok": True, "execution_id": record.execution_id, "decision_id": record.decision_id}

    def observe_settled_ledger_record(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not self.cfg.enabled or self._real_learning is None:
            return {"ok": False, "eligible_for_learning": False, "reason_code": "omar_real_learning_disabled"}
        from .settled_ledger_bridge import ingest_settled_ledger_record

        result = ingest_settled_ledger_record(self._real_learning, row)
        self.last_real_learning = {
            "source": "phase2_canonical_outcome_ledger",
            "lineage": dict(result.get("lineage") or {}),
            "eligible_for_learning": bool(result.get("eligible_for_learning", False)),
            "policy_update": dict(result.get("policy_update") or {}),
            "reason_code": str(result.get("reason_code") or "ok"),
        }
        self._log({"event": "omar_canonical_settled_outcome", **self.last_real_learning})
        return dict(result)

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
            "ledger": self._ledger.state() if self._ledger is not None else {},
            "policy": self._trainer.policy.state() if self._trainer is not None else {},
        }

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

    def _loop(self):
        if self.cfg.enabled:
            self._ledger = CanonicalOutcomeLedger(data_dir=self.data_dir, chain=self.chain_name, bootstrap_history=self.cfg.outcome_bootstrap_history)
            checkpoint = self.policy_path if self.cfg.policy_checkpoint_enabled else None
            self._trainer = OmarTrainer(self.cfg, checkpoint_path=checkpoint)
            if self.cfg.self_play_enabled:
                stats = self._trainer.train()
                if stats:
                    self.last_train = asdict(stats[-1])
                self._log({"event": "omar_training_complete", "last_train": self.last_train, "policy": self._trainer.policy.state()})

        coord_hist, conflict_hist = [], []
        next_learning_at = 0.0
        while not self._stop.is_set():
            if self._trainer and self._trainer.last_stats:
                st = self._trainer.last_stats
                coord_hist.append(st.mean_coordination)
                conflict_hist.append(st.mean_conflict)
                coord_hist[:] = coord_hist[-200:]
                conflict_hist[:] = conflict_hist[-200:]
            now = time.monotonic()
            if self.cfg.enabled and self.cfg.real_outcome_learning_enabled and self._trainer and self._ledger and now >= next_learning_at:
                self._learn_real_outcomes()
                next_learning_at = now + self.cfg.real_outcome_poll_seconds
            m = compute_social_metrics(coord_hist=np.array(coord_hist, dtype=float), conflict_hist=np.array(conflict_hist, dtype=float), capital_alloc={r: 1.0 for r in (self.cfg.roles or [])})
            self.last_social = to_dict(m)
            self._log({"event": "omar_social_metrics", **self.last_social, "real_learning": dict(self.last_real_learning)})
            self._cycle += 1
            self._stop.wait(1.0)
