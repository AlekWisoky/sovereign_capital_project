from __future__ import annotations

from dataclasses import asdict
from typing import Dict, Any, Optional, Mapping
import threading
import time
import json
import os
import numpy as np

from .config import OmarConfig
from .trainer import OmarTrainer
from .metrics import compute_social_metrics, to_dict
from .real_learning import OmarRealLearner, OmarRecommendation, ACTIONS
from .learning_quality_runtime import live_influence_quality
from .performance_promotion_runtime import live_performance_promotion


class OmarRuntime:
    """First-class OMAR learning subsystem.

    Production learning is closed-loop:
      real decision -> real execution -> settled outcome -> OMAR -> next decision

    OMAR never signs or executes a transaction and never overrides governance.
    Its live recommendation is bounded to veto/downsizing/gas preference.
    Offline self-play remains available as an explicit bootstrap experiment.

    Live policy influence requires two independent gates:
      1. learning-data quality / lineage integrity;
      2. out-of-sample performance versus an explicit baseline.
    """

    def __init__(self, cfg: OmarConfig, chain_name: str = "default"):
        self.cfg = cfg
        self.chain_name = chain_name
        self._trainer: Optional[OmarTrainer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()

        self.last_social: Dict[str, Any] = {}
        self.last_train: Dict[str, Any] = {}
        self.last_decision: Dict[str, Any] = {}
        self.last_outcome: Dict[str, Any] = {}
        self.last_learning_quality: Dict[str, Any] = {}
        self.last_performance_promotion: Dict[str, Any] = {}
        self._cycle = 0

        base_data_dir = str(os.environ.get("VICTOR_DATA_DIR", "data") or "data")
        self.data_dir = os.path.join(base_data_dir, "superstructure")
        os.makedirs(self.data_dir, exist_ok=True)
        self.audit_path = os.path.join(self.data_dir, f"omar_audit_{chain_name}.jsonl")
        self.learning_path = os.path.join(
            self.data_dir, "omar_learning", f"real_policy_{chain_name}.json"
        )
        self._real_learner: Optional[OmarRealLearner] = None
        if bool(getattr(cfg, "real_learning_enabled", True)):
            self._real_learner = OmarRealLearner(
                path=self.learning_path,
                alpha=float(getattr(cfg, "real_learning_alpha", 0.12)),
                epsilon=float(getattr(cfg, "live_exploration_epsilon", 0.0)),
                min_observations=int(getattr(cfg, "real_learning_min_observations", 20)),
            )
        self._pending_decisions: Dict[str, Dict[str, Any]] = {}
        self._learning_cursor_path = os.path.join(
            self.data_dir, "omar_learning", f"cursor_{chain_name}.json"
        )
        self._learning_cursor = self._load_learning_cursor()

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.enabled)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": bool(self.cfg.enabled),
                "policy_model": self.cfg.policy_model,
                "cycle": self._cycle,
                "real_learning": self._real_learner.summary() if self._real_learner else {"enabled": False},
                "last_decision": dict(self.last_decision),
                "last_outcome": dict(self.last_outcome),
                "last_learning_quality": dict(self.last_learning_quality),
                "last_performance_promotion": dict(self.last_performance_promotion),
                "last_social": dict(self.last_social),
                "last_train": dict(self.last_train),
            }

    def learning_quality(self) -> dict[str, Any]:
        result = live_influence_quality(self)
        with self._lock:
            self.last_learning_quality = dict(result)
        return result

    def performance_promotion(self) -> dict[str, Any]:
        result = live_performance_promotion(self)
        with self._lock:
            self.last_performance_promotion = dict(result)
        return result

    def _live_influence_gate(self) -> tuple[bool, str]:
        quality = self.learning_quality()
        if not bool(quality.get("live_influence_allowed", False)):
            return False, f"learning_quality_gate:{quality.get('reason', 'not_ready')}"
        if bool(getattr(self.cfg, "performance_promotion_enabled", True)):
            performance = self.performance_promotion()
            if not bool(performance.get("promotion_allowed", False)):
                return False, f"performance_promotion_gate:{performance.get('reason', 'not_ready')}"
        return True, "promotion_verified"

    def recommend(self, context: Mapping[str, Any]) -> OmarRecommendation:
        """Return a bounded recommendation for the next real decision.

        A trained model is not enough for live influence: both the canonical
        learning-data quality gate and the independent OOS performance gate must
        pass. Governance remains the final authority.
        """
        if not self.enabled or not bool(getattr(self.cfg, "live_influence_enabled", True)):
            return OmarRecommendation("", "DISABLED", 0.0, False, 1.0, "standard", False, 0, "omar_disabled")
        if self._real_learner is None:
            return OmarRecommendation("", "UNAVAILABLE", 0.0, False, 1.0, "standard", False, 0, "real_learner_unavailable")

        allowed, gate_reason = self._live_influence_gate()
        if not allowed:
            obs = int(getattr(self._real_learner, "total_observations", 0))
            rec = OmarRecommendation("", "UNTRAINED", 0.0, False, 1.0, "standard", False, obs, gate_reason)
            with self._lock:
                self.last_decision = rec.to_dict()
            return rec

        rec = self._real_learner.recommend(context)
        with self._lock:
            self.last_decision = rec.to_dict()
        return rec

    def observe_decision(
        self,
        *,
        decision_id: str,
        opportunity_id: str,
        route_id: str,
        action: str,
        state_key: str,
        context: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not self.enabled or not bool(getattr(self.cfg, "real_learning_enabled", True)):
            return
        row = {
            "decision_id": str(decision_id),
            "opportunity_id": str(opportunity_id),
            "route_id": str(route_id),
            "action": str(action),
            "state_key": str(state_key),
            "context": dict(context or {}),
            "metadata": dict(metadata or {}),
            "ts_ms": int(time.time() * 1000),
        }
        with self._lock:
            self._pending_decisions[str(decision_id)] = row
            if len(self._pending_decisions) > 512:
                oldest = sorted(self._pending_decisions.items(), key=lambda item: item[1].get("ts_ms", 0))[:64]
                for key, _ in oldest:
                    self._pending_decisions.pop(key, None)
        self._log({"event": "omar_real_decision", **row})

    def observe_outcome(
        self,
        *,
        decision_id: str,
        ok: bool,
        realized_net_usd: float,
        expected_net_usd: float,
        amount_in_wei: int,
        gas_cost_usd: float = 0.0,
        slippage_bps: float = 0.0,
        latency_ms: int = 0,
        route_id: str = "",
        tx_hash: str = "",
        outcome_truth_verified: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not self.enabled or self._real_learner is None or not bool(getattr(self.cfg, "real_learning_enabled", True)):
            return {"ok": False, "reason": "omar_real_learning_disabled"}
        with self._lock:
            pending = dict(self._pending_decisions.pop(str(decision_id), {}) or {})
        state_key = str(pending.get("state_key") or "")
        action = str(pending.get("action") or "")
        if not state_key or action not in ACTIONS:
            return {"ok": False, "reason": "missing_decision_link", "decision_id": str(decision_id)}
        reward = float(realized_net_usd) - 0.25 * max(0.0, float(expected_net_usd) - float(realized_net_usd))
        reward -= max(0.0, float(slippage_bps)) * 0.01
        reward -= max(0.0, float(latency_ms)) * 0.0001
        if not ok:
            reward -= 1.0
        if not outcome_truth_verified:
            reward -= 2.0
        reward = float(np.clip(reward, -50.0, 50.0))
        outcome = {
            "decision_id": str(decision_id), "route_id": str(route_id or pending.get("route_id") or ""),
            "tx_hash": str(tx_hash), "ok": bool(ok), "realized_net_usd": float(realized_net_usd),
            "expected_net_usd": float(expected_net_usd), "amount_in_wei": int(amount_in_wei),
            "gas_cost_usd": float(gas_cost_usd), "slippage_bps": float(slippage_bps),
            "latency_ms": int(latency_ms), "outcome_truth_verified": bool(outcome_truth_verified),
            "metadata": dict(metadata or {}),
        }
        result = self._real_learner.observe(state_key=state_key, action=action, reward=reward, outcome=outcome)
        with self._lock:
            self.last_outcome = {**dict(result), "decision_id": str(decision_id), "action": action}
        self._log({"event": "omar_real_learning_update", **dict(result), "outcome": outcome})
        return result

    def _load_learning_cursor(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self._learning_cursor_path):
                with open(self._learning_cursor_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                    if isinstance(payload, dict):
                        return payload
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
        return {"offset": 0, "seen": []}

    def _save_learning_cursor(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._learning_cursor_path), exist_ok=True)
            tmp = self._learning_cursor_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(self._learning_cursor, handle, sort_keys=True)
            os.replace(tmp, self._learning_cursor_path)
        except (OSError, TypeError, ValueError):
            return

    def _ingest_real_training_log(self) -> None:
        if not self.enabled or self._real_learner is None:
            return
        base_data_dir = str(os.environ.get("VICTOR_DATA_DIR", "data") or "data")
        candidates = [
            os.path.join(base_data_dir, "training", f"rl_training_{self.chain_name}.jsonl"),
            os.path.join("backend", "data", "training", f"rl_training_{self.chain_name}.jsonl"),
            os.path.join("data", "training", f"rl_training_{self.chain_name}.jsonl"),
        ]
        training_path = next((path for path in candidates if os.path.exists(path)), candidates[0])
        try:
            offset = max(0, int(self._learning_cursor.get("offset") or 0))
            seen = set(str(x) for x in list(self._learning_cursor.get("seen") or []))
            with open(training_path, "r", encoding="utf-8") as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    offset = handle.tell()
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
                    brain = extra.get("brain") if isinstance(extra.get("brain"), dict) else {}
                    action = str(brain.get("omar_action") or "")
                    state_key = str(brain.get("omar_state_key") or "")
                    tx_hash = str(row.get("tx_hash") or "")
                    decision_id = str(brain.get("omar_decision_id") or tx_hash)
                    if not state_key or action not in ACTIONS or decision_id in seen:
                        continue
                    try:
                        amount_in = int(row.get("amount_in_wei") or 0)
                    except (TypeError, ValueError):
                        amount_in = 0
                    expected = float(row.get("expected_after_costs_wei") or 0.0)
                    realized = float(row.get("realized_after_gas_wei") or 0.0)
                    reward_trace = row.get("reward_trace") if isinstance(row.get("reward_trace"), dict) else {}
                    reward = reward_trace.get("reward_scaled_float")
                    if reward is None:
                        denom = max(1.0, float(abs(amount_in)))
                        reward = (realized - expected) / denom * 1_000_000.0
                    result = self._real_learner.observe(
                        state_key=state_key,
                        action=action,
                        reward=float(reward),
                        outcome={
                            "tx_hash": tx_hash,
                            "amount_in_wei": amount_in,
                            "expected_after_costs_wei": expected,
                            "realized_after_gas_wei": realized,
                            "ok": bool(row.get("ok", False)),
                            "reward_trace": reward_trace,
                            "route_id": str(row.get("route_id") or ""),
                            "metadata": extra,
                        },
                    )
                    if result.get("ok"):
                        seen.add(decision_id)
                        self.last_outcome = {**dict(result), "decision_id": decision_id, "tx_hash": tx_hash}
            self._learning_cursor = {"offset": offset, "seen": list(sorted(seen))[-2048:]}
            self._save_learning_cursor()
        except OSError:
            return

    def _log(self, obj: Dict[str, Any]):
        obj = dict(obj)
        obj["ts"] = time.time()
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError):
            pass

    def _loop(self):
        if self.cfg.enabled and self.cfg.self_play_enabled:
            self._trainer = OmarTrainer(self.cfg)
            stats = self._trainer.train()
            if stats:
                self.last_train = asdict(stats[-1])
            self._log({"event": "omar_training_complete", "last_train": self.last_train})

        coord_hist = []
        conflict_hist = []
        cap_alloc = {r: 1.0 for r in (self.cfg.roles or [])}
        while not self._stop.is_set():
            self._ingest_real_training_log()
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
