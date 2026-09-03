from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, Optional

import numpy as np

from ..learning.outcome_ledger import CanonicalOutcomeLedger
from ..learning.phase9_outcome_gate import (
    CanonicalSettlementIndex,
    prepare_real_outcome_for_omar,
)
from ..pathing import canonical_data_dir
from .config import OmarConfig
from .metrics import compute_social_metrics, to_dict
from .phase7_context_store import Phase7ContextStore
from .trainer import OmarTrainer


class OmarRuntime:
    """First-class OMAR learning runtime.

    OMAR remains downstream of execution truth: finalized outcomes are read from
    the canonical PnL ledger, joined with Phase 7 decision context and canonical
    receipt-settlement identity, checked for complete identity/action lineage,
    and only then used for bounded online policy updates.
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
        self._cycle = 0

        self.data_dir = canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))
        self.omar_dir = os.path.join(self.data_dir, "omar")
        os.makedirs(self.omar_dir, exist_ok=True)
        self.audit_path = os.path.join(self.omar_dir, f"omar_audit_{self.chain_name}.jsonl")
        self.policy_path = os.path.join(self.omar_dir, f"policy_{self.chain_name}.json")
        self._phase7_context_store = Phase7ContextStore(
            data_dir=self.data_dir,
            chain=self.chain_name,
        )
        self._settlement_index = CanonicalSettlementIndex(
            data_dir=self.data_dir,
            chain=self.chain_name,
        )

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
            "phase7_context": self._phase7_context_store.state(),
            "settlement_index": {"path": self._settlement_index.path},
            "policy": self._trainer.policy.state() if self._trainer is not None else {},
        }

    def _log(self, obj: Dict[str, Any]):
        payload = dict(obj)
        payload["ts"] = time.time()
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    def _learn_real_outcomes(self) -> None:
        if not self._ledger or not self._trainer:
            return
        outcomes = self._ledger.poll(limit=self.cfg.real_outcome_batch_size)
        if not outcomes:
            return

        eligible_outcomes = []
        rejected = []
        for outcome in outcomes:
            eligible, reason_codes = prepare_real_outcome_for_omar(
                outcome,
                store=self._phase7_context_store,
                settlement_index=self._settlement_index,
            )
            if eligible:
                eligible_outcomes.append(outcome)
            else:
                rejected.append(
                    {
                        "tx_hash": str(getattr(outcome, "tx_hash", "") or ""),
                        "reason_codes": list(reason_codes),
                    }
                )

        if eligible_outcomes:
            stats = self._trainer.learn_from_real_outcomes(eligible_outcomes)
        else:
            stats = {
                "seen": 0,
                "learned": 0,
                "skipped": 0,
                "mean_reward_scaled": 0.0,
                "last_tx_hash": "",
                "policy_updates": int(self._trainer.policy.updates),
            }
        stats = dict(stats)
        stats["phase9_seen"] = int(len(outcomes))
        stats["phase9_eligible"] = int(len(eligible_outcomes))
        stats["phase9_rejected"] = int(len(rejected))
        stats["phase9_rejections"] = rejected[-25:]
        self.last_real_learning = stats
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
