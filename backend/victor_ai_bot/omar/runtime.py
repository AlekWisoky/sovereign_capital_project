from __future__ import annotations
from dataclasses import asdict
from typing import Dict, Any, Optional
import threading
import time
import json
import os
import numpy as np

from .config import OmarConfig
from .trainer import OmarTrainer
from .metrics import compute_social_metrics, to_dict


class OmarRuntime:
    """Non-breaking OMAR runtime.

    - Runs self-play training (offline style) only when enabled.
    - Exposes social intelligence metrics on a 1s loop.
    - Writes audit logs to JSONL.
    """

    def __init__(self, cfg: OmarConfig, chain_name: str = "default"):
        self.cfg = cfg
        self.chain_name = chain_name
        self._trainer: Optional[OmarTrainer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        self.last_social: Dict[str, Any] = {}
        self.last_train: Dict[str, Any] = {}
        self._cycle = 0

        self.data_dir = os.path.join("data", "superstructure")
        os.makedirs(self.data_dir, exist_ok=True)
        self.audit_path = os.path.join(self.data_dir, f"omar_audit_{chain_name}.jsonl")

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
        }

    def _log(self, obj: Dict[str, Any]):
        obj = dict(obj)
        obj["ts"] = time.time()
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    def _loop(self):
        # training first (if enabled)
        if self.cfg.enabled and self.cfg.self_play_enabled:
            self._trainer = OmarTrainer(self.cfg)
            stats = self._trainer.train()
            if stats:
                self.last_train = asdict(stats[-1])
            self._log({"event": "omar_training_complete", "last_train": self.last_train})

        # social metrics loop
        coord_hist = []
        conflict_hist = []
        cap_alloc = {r: 1.0 for r in (self.cfg.roles or [])}
        while not self._stop.is_set():
            # best-effort: update from last training stats
            if self._trainer and self._trainer.last_stats:
                st = self._trainer.last_stats
                coord_hist.append(st.mean_coordination)
                conflict_hist.append(st.mean_conflict)
                coord_hist[:] = coord_hist[-200:]
                conflict_hist[:] = conflict_hist[-200:]

            m = compute_social_metrics(
                coord_hist=np.array(coord_hist, dtype=float),
                conflict_hist=np.array(conflict_hist, dtype=float),
                capital_alloc=cap_alloc,
            )
            self.last_social = to_dict(m)
            self._log({"event": "omar_social_metrics", **self.last_social})

            self._cycle += 1
            time.sleep(1.0)
