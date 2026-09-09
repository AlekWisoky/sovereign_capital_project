from __future__ import annotations

import copy
import json
import math
import os
import threading
import time
from dataclasses import asdict
from typing import Any, Dict, Mapping, Optional, cast

from .config import OmarConfig
from .learning_integrity import validate_learning_transition
from .metrics import compute_social_metrics, to_dict
from .real_learning import OmarRealLearner, OmarRecommendation
from .trainer import OmarTrainer

class OmarRuntime:
    """Bounded OMAR runtime: decision snapshot -> canonical settlement -> gate -> learner."""
    def __init__(self, cfg: OmarConfig, chain_name: str = "default"):
        self.cfg = cfg; self.chain_name = chain_name
        self._trainer: Optional[OmarTrainer] = None; self._thread: Optional[threading.Thread] = None; self._stop = threading.Event(); self._lock = threading.RLock()
        self.last_social: Dict[str, Any] = {}; self.last_train: Dict[str, Any] = {}; self.last_decision: Dict[str, Any] = {}; self.last_outcome: Dict[str, Any] = {}; self._cycle = 0
        base_data_dir = str(os.environ.get("VICTOR_DATA_DIR", "data") or "data"); self.data_dir = os.path.join(base_data_dir, "superstructure"); os.makedirs(self.data_dir, exist_ok=True)
        self.audit_path = os.path.join(self.data_dir, f"omar_audit_{chain_name}.jsonl"); self.learning_path = os.path.join(self.data_dir, "omar_learning", f"real_policy_{chain_name}.json")
        self._real_learner: Optional[OmarRealLearner] = None
        if bool(getattr(cfg, "real_learning_enabled", True)):
            self._real_learner = OmarRealLearner(path=self.learning_path, alpha=float(getattr(cfg, "real_learning_alpha", 0.12)), epsilon=float(getattr(cfg, "live_exploration_epsilon", 0.0)), min_observations=int(getattr(cfg, "real_learning_min_observations", 20)))
        self._pending_decisions: Dict[str, Dict[str, Any]] = {}

    @property
    def enabled(self) -> bool: return bool(self.cfg.enabled)
    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear(); self._thread = threading.Thread(target=self._loop, daemon=True); self._thread.start()
    def stop(self) -> None: self._stop.set()
    def state(self) -> Dict[str, Any]:
        with self._lock:
            return {"enabled": self.enabled, "policy_model": self.cfg.policy_model, "cycle": self._cycle, "real_learning": self._real_learner.summary() if self._real_learner else {"enabled": False}, "last_decision": dict(self.last_decision), "last_outcome": dict(self.last_outcome), "last_social": dict(self.last_social), "last_train": dict(self.last_train)}

    def recommend(self, context: Mapping[str, Any]) -> OmarRecommendation:
        if not self.enabled or not bool(getattr(self.cfg, "live_influence_enabled", True)) or self._real_learner is None:
            return OmarRecommendation("", "DISABLED", 0.0, False, 1.0, "standard", False, 0, "omar_disabled")
        rec = self._real_learner.recommend(context)
        with self._lock: self.last_decision = rec.to_dict()
        return rec

    def observe_decision(self, *, decision_id: str, opportunity_id: str, route_id: str, action: str, state_key: str, context: Mapping[str, Any], metadata: Mapping[str, Any] | None = None, expected_net_usd: Any = None) -> None:
        if not self.enabled or not bool(getattr(self.cfg, "real_learning_enabled", True)): return
        metadata_row = copy.deepcopy(dict(metadata or {})); lineage = cast(dict[str, Any], metadata_row.get("canonical_lineage") or {})
        correlation_id = str(lineage.get("correlation_id") or metadata_row.get("correlation_id") or "").strip()
        expected = expected_net_usd if expected_net_usd is not None else metadata_row.get("expected_net_usd", context.get("expected_net_usd"))
        row = {"decision_id": str(decision_id), "correlation_id": correlation_id, "opportunity_id": str(opportunity_id), "route_id": str(route_id), "action": str(action), "state_key": str(state_key), "context": copy.deepcopy(dict(context or {})), "metadata": metadata_row, "canonical_lineage": {"decision_id": str(decision_id), "correlation_id": correlation_id}, "ts_ms": int(time.time() * 1000)}
        if expected is not None:
            row["expected_net_usd"] = expected
        with self._lock:
            self._pending_decisions[str(decision_id)] = row
            if len(self._pending_decisions) > 512:
                for key, _ in sorted(self._pending_decisions.items(), key=lambda item: item[1].get("ts_ms", 0))[:64]: self._pending_decisions.pop(key, None)
        self._log({"event": "omar_real_decision", **copy.deepcopy(row)})

    def observe_outcome(self, *, decision_id: str, ok: bool, realized_net_usd: Any, expected_net_usd: Any, amount_in_wei: Any, gas_cost_usd: Any = None, slippage_bps: Any = None, latency_ms: Any = None, route_id: str = "", tx_hash: str = "", outcome_truth_verified: bool = False, metadata: Mapping[str, Any] | None = None) -> Dict[str, Any]:
        if not self.enabled or self._real_learner is None or not bool(getattr(self.cfg, "real_learning_enabled", True)):
            return {"ok": False, "learned": False, "reason": "omar_real_learning_disabled"}
        with self._lock: pending = copy.deepcopy(self._pending_decisions.get(str(decision_id), {}) or {})
        metadata_row = copy.deepcopy(dict(metadata or {})); settlement = cast(dict[str, Any], metadata_row.get("settlement") or {}); lineage = cast(dict[str, Any], metadata_row.get("canonical_lineage") or {})
        outcome = dict(settlement)
        outcome.update({"status": str(settlement.get("status") or metadata_row.get("status") or "").strip(), "source": str(settlement.get("source") or metadata_row.get("source") or "").strip(), "decision_id": str(settlement.get("decision_id") or lineage.get("decision_id") or decision_id).strip(), "correlation_id": str(settlement.get("correlation_id") or lineage.get("correlation_id") or pending.get("correlation_id") or "").strip(), "opportunity_id": str(settlement.get("opportunity_id") or pending.get("opportunity_id") or "").strip(), "action": str(settlement.get("action") or pending.get("action") or "").strip(), "route_id": str(settlement.get("route_id") or route_id or pending.get("route_id") or "").strip(), "truth_verified": bool(settlement.get("truth_verified", settlement.get("outcome_truth_verified", outcome_truth_verified))), "settlement_verified": bool(settlement.get("settlement_verified", settlement.get("truth_verified", outcome_truth_verified))), "execution_id": str(settlement.get("execution_id") or "").strip(), "outcome_id": str(settlement.get("outcome_id") or "").strip(), "sizing_id": str(settlement.get("sizing_id") or "").strip(), "canonical_lineage": {"decision_id": str(lineage.get("decision_id") or settlement.get("decision_id") or decision_id).strip(), "correlation_id": str(lineage.get("correlation_id") or settlement.get("correlation_id") or pending.get("correlation_id") or "").strip()}})
        outcome["expected_net_usd"] = expected_net_usd if expected_net_usd is not None else settlement.get("expected_net_usd", pending.get("expected_net_usd"))
        outcome["realized_net_usd"] = realized_net_usd if realized_net_usd is not None else settlement.get("realized_net_usd")
        expected = pending.get("expected_net_usd")
        realized = outcome.get("realized_net_usd")
        if expected is not None and realized is not None:
            try:
                if math.isfinite(float(expected)) and math.isfinite(float(realized)):
                    outcome["expectation_error"] = float(realized) - float(expected)
            except (TypeError, ValueError, OverflowError):
                pass
        gate = validate_learning_transition(pending, outcome, decision_id=str(decision_id))
        if not gate.allowed:
            result = {"ok": False, "learned": False, "reason": gate.reason, "decision_id": str(decision_id)}; self._log({"event": "omar_learning_gate_rejected", **result}); return result
        action = str(pending.get("action") or ""); state_key = str(pending.get("state_key") or "")
        expected = float(pending["expected_net_usd"]); realized = float(outcome["realized_net_usd"]); expectation_error = realized - expected
        reward = realized - 0.25 * max(0.0, -expectation_error) - max(0.0, float(outcome.get("slippage_bps") or 0.0)) * 0.01 - max(0.0, float(outcome.get("latency_ms") or 0.0)) * 0.0001
        if not ok: reward -= 1.0
        reward = max(-50.0, min(50.0, reward))
        learner_outcome = {"decision_id": str(decision_id), "correlation_id": str(outcome.get("correlation_id") or ""), "route_id": str(outcome.get("route_id") or ""), "tx_hash": str(tx_hash), "ok": bool(ok), "expected_net_usd": expected, "realized_net_usd": realized, "expectation_error": expectation_error, "settlement_verified": True, "amount_in_wei": int(amount_in_wei), "gas_cost_usd": float(gas_cost_usd or 0.0), "slippage_bps": float(slippage_bps or 0.0), "latency_ms": int(latency_ms or 0), "outcome_truth_verified": True, "metadata": metadata_row}
        result = self._real_learner.observe(state_key=state_key, action=action, reward=reward, outcome=learner_outcome)
        with self._lock: self._pending_decisions.pop(str(decision_id), None); self.last_outcome = {**dict(result), "decision_id": str(decision_id), "action": action, "expected_net_usd": expected, "realized_net_usd": realized, "expectation_error": expectation_error}
        self._log({"event": "omar_real_learning_update", **dict(result), "outcome": learner_outcome, "decision_snapshot": pending}); return result

    def _log(self, obj: Dict[str, Any]) -> None:
        try:
            with open(self.audit_path, "a", encoding="utf-8") as handle: handle.write(json.dumps({**dict(obj), "ts": time.time()}, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError): pass

    def _loop(self) -> None:
        if self.enabled and self.cfg.self_play_enabled:
            self._trainer = OmarTrainer(self.cfg); stats = self._trainer.train(); self.last_train = asdict(stats[-1]) if stats else {}; self._log({"event": "omar_training_complete", "last_train": self.last_train})
        while not self._stop.is_set():
            self._cycle += 1; time.sleep(1.0)
