from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from typing import Any, Dict, List

from ..persistence.db import PersistenceDB
from ..persistence.repositories.edge_model_repository import EdgeModelRepository
from .edge_features import build_edge_features, feature_key
from .edge_predictions import EdgePrediction
from .learning_policy import LearningPolicy


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _ewma(prev: float, value: float, alpha: float) -> float:
    return float(prev) * (1.0 - alpha) + float(value) * alpha


class ExecutionLearningEngine:
    def __init__(self, *, data_dir: str, chain: str, policy: LearningPolicy | None = None):
        self.path = os.path.join(data_dir, "execution_capture", f"edge_learning_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.policy = policy or LearningPolicy()
        self._state = self._load()
        self._db = PersistenceDB(os.path.join(data_dir, "state", "xdv_runtime_state.sqlite3"))
        self._repo = EdgeModelRepository(self._db, chain=chain)

    def _blank(self) -> Dict[str, Any]:
        return {"priors": {}, "quarantine": {}}

    def _coerce_prior_item(self, key: str, payload: Any) -> Dict[str, Any] | None:
        if not isinstance(key, str) or not key or not isinstance(payload, dict):
            return None
        return {
            "key": key,
            "family": str(payload.get("family") or ""),
            "route_family": str(payload.get("route_family") or ""),
            "venue": str(payload.get("venue") or ""),
            "lane": str(payload.get("lane") or ""),
            "regime": str(payload.get("regime") or ""),
            "count": max(0, int(payload.get("count") or 0)),
            "success_ewma": float(payload.get("success_ewma") or 0.0),
            "competition_ewma": float(payload.get("competition_ewma") or 0.0),
            "quality_ewma": float(payload.get("quality_ewma") or 0.0),
            "freshness_ewma": float(payload.get("freshness_ewma") or 0.0),
            "slippage_bias_ewma": float(payload.get("slippage_bias_ewma") or 0.0),
            "failure_risk_ewma": float(payload.get("failure_risk_ewma") or 0.0),
            "updated_ts_ms": max(0, int(payload.get("updated_ts_ms") or 0)),
        }

    def _coerce_quarantine_item(self, key: str, payload: Any) -> Dict[str, Any] | None:
        if not isinstance(key, str) or not key or not isinstance(payload, dict):
            return None
        return {
            "recent_failures": max(0, int(payload.get("recent_failures") or 0)),
            "until_ts_ms": max(0, int(payload.get("until_ts_ms") or 0)),
        }

    def _coerce_state(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("edge learning state must be a dict")
        priors = {}
        for key, value in (payload.get("priors") or {}).items():
            item = self._coerce_prior_item(key, value)
            if item is not None:
                priors[key] = item
        quarantine = {}
        for key, value in (payload.get("quarantine") or {}).items():
            item = self._coerce_quarantine_item(key, value)
            if item is not None:
                quarantine[key] = item
        return {"priors": priors, "quarantine": quarantine}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return self._coerce_state(data)
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def predict(
        self,
        *,
        envelope: Any,
        regime: str,
        lane_hint: str,
        telemetry: Dict[str, float],
        context: Dict[str, Any] | None = None,
    ) -> EdgePrediction:
        features = build_edge_features(
            envelope=envelope,
            regime=regime,
            lane_hint=lane_hint,
            telemetry=telemetry,
            context=context,
        )
        key = feature_key(features)
        state = dict(self._state.get("priors", {}).get(key) or self._repo.get_prior(key=key) or {})
        count = int(state.get("count") or 0)
        venue_q = float(features.get("venue_reliability_score") or 0.6)
        success = float(
            state.get("success_ewma")
            or (
                (0.55 + 0.25 * venue_q + 0.20 * float(features.get("simulation_confidence") or 0.5))
                if count == 0
                else 0.6
            )
        )
        stale = float(features.get("telemetry_stale_rate") or 0.05)
        competition = float(
            state.get("competition_ewma")
            or (
                0.45 * float(features.get("mempool_copy_risk") or 0.0)
                + 0.35 * stale
                + (0.12 if str(lane_hint).upper() == "PUBLIC" else -0.08)
            )
        )
        quality = float(state.get("quality_ewma") or 1.0)
        freshness = float(
            state.get("freshness_ewma") or float(features.get("freshness_score") or 0.7)
        )
        slip_bias = float(state.get("slippage_bias_ewma") or 0.0)
        failure_risk = float(state.get("failure_risk_ewma") or max(0.0, 1.0 - success))
        suff = _clip(count / max(1.0, float(self.policy.min_live_observations)), 0.0, 1.0)
        reasons: List[str] = []
        if count < self.policy.min_live_observations:
            reasons.append("sparse_data_fallback")
        q = self._state.get("quarantine", {}).get(key) or {}
        if q and int(q.get("until_ts_ms") or 0) > int(time.time() * 1000):
            reasons.append("route_quarantined")
            competition = min(0.98, competition + self.policy.quarantine_penalty)
            success = max(0.05, success - self.policy.quarantine_penalty)
        if float(features.get("projected_realized_profit_usd") or 0.0) <= float(
            features.get("borrow_cost_usd") or 0.0
        ):
            reasons.append("borrow_cost_pressure")
        return EdgePrediction(
            success_probability=_clip(success, 0.05, 0.995),
            competition_probability=_clip(competition, 0.0, 0.995),
            quality_adjustment_factor=_clip(quality, 0.55, 1.25),
            freshness_decay_factor=_clip(freshness, 0.25, 1.05),
            reliability_factor=_clip(0.55 + 0.45 * venue_q, 0.35, 1.1),
            expected_slippage_bias=_clip(slip_bias, -1.0, 1.0),
            failure_mode_risk=_clip(failure_risk, 0.0, 1.0),
            route_fragility=_clip(float(features.get("liquidity_fragility") or 0.0), 0.0, 1.0),
            data_sufficiency=suff,
            reason_codes=reasons,
        )

    def confidence_to_size_scale(self, prediction: EdgePrediction) -> float:
        conf = 0.5 * float(prediction.data_sufficiency) + 0.5 * float(
            prediction.success_probability
        ) * (1.0 - float(prediction.competition_probability))
        return _clip(
            self.policy.confidence_size_floor
            + conf * (self.policy.confidence_size_cap - self.policy.confidence_size_floor),
            self.policy.confidence_size_floor,
            self.policy.confidence_size_cap,
        )

    def exploration_budget(self) -> Dict[str, float]:
        return {
            "capital_share_cap": float(self.policy.safe_exploration_capital_share),
            "daily_cost_cap_usd": float(self.policy.safe_exploration_daily_cost_usd),
        }

    def observe(
        self,
        *,
        envelope: Any,
        regime: str,
        lane: str,
        telemetry: Dict[str, float],
        prediction: EdgePrediction | Dict[str, Any],
        actual_success: bool,
        actual_realized_edge_usd: float,
        actual_competed_out: bool = False,
        actual_stale: bool = False,
        actual_slippage_bias: float = 0.0,
    ) -> None:
        if isinstance(prediction, dict):
            prediction = EdgePrediction(**prediction)
        features = build_edge_features(
            envelope=envelope, regime=regime, lane_hint=lane, telemetry=telemetry
        )
        key = feature_key(features)
        prev = dict(self._state.get("priors", {}).get(key) or self._repo.get_prior(key=key) or {})
        count = int(prev.get("count") or 0)
        alpha = 0.35 if count < 8 else 0.18
        projected = float(features.get("projected_realized_profit_usd") or 0.0)
        ratio = actual_realized_edge_usd / projected if abs(projected) > 1e-9 else 1.0
        nxt = {
            "key": key,
            "family": str(features.get("strategy_family") or ""),
            "route_family": str(features.get("route_family") or ""),
            "venue": str((features.get("venues") or [""])[0]),
            "lane": str(lane),
            "regime": str(regime),
            "count": count + 1,
            "success_ewma": _ewma(
                float(prev.get("success_ewma") or prediction.success_probability),
                1.0 if actual_success else 0.0,
                alpha,
            ),
            "competition_ewma": _ewma(
                float(prev.get("competition_ewma") or prediction.competition_probability),
                1.0 if actual_competed_out else 0.0,
                alpha,
            ),
            "quality_ewma": _ewma(
                float(prev.get("quality_ewma") or prediction.quality_adjustment_factor),
                _clip(ratio, 0.25, 1.5),
                alpha,
            ),
            "freshness_ewma": _ewma(
                float(prev.get("freshness_ewma") or prediction.freshness_decay_factor),
                0.0 if actual_stale else 1.0,
                alpha,
            ),
            "slippage_bias_ewma": _ewma(
                float(prev.get("slippage_bias_ewma") or prediction.expected_slippage_bias),
                float(actual_slippage_bias),
                alpha,
            ),
            "failure_risk_ewma": _ewma(
                float(prev.get("failure_risk_ewma") or prediction.failure_mode_risk),
                0.0 if actual_success else 1.0,
                alpha,
            ),
            "updated_ts_ms": int(time.time() * 1000),
        }
        self._state.setdefault("priors", {})[key] = nxt
        q = dict(self._state.get("quarantine", {}).get(key) or {})
        recent_fails = int(q.get("recent_failures") or 0) + (0 if actual_success else 1)
        if actual_success:
            recent_fails = 0
        q["recent_failures"] = recent_fails
        if recent_fails >= int(self.policy.quarantine_failure_threshold):
            q["until_ts_ms"] = int(time.time() * 1000) + 30 * 60 * 1000
        self._state.setdefault("quarantine", {})[key] = q
        self._save()
        self._repo.upsert_prior(
            key=key,
            family=str(nxt["family"]),
            route_family=str(nxt["route_family"]),
            venue=str(nxt["venue"]),
            lane=str(nxt["lane"]),
            regime=str(nxt["regime"]),
            payload=nxt,
        )
        self._repo.insert_observation(
            family=str(nxt["family"]),
            route_family=str(nxt["route_family"]),
            venue=str(nxt["venue"]),
            lane=str(nxt["lane"]),
            regime=str(nxt["regime"]),
            feature_json=features,
            prediction_json=prediction.to_dict(),
            outcome_json={
                "success": actual_success,
                "actual_realized_edge_usd": actual_realized_edge_usd,
                "actual_competed_out": actual_competed_out,
                "actual_stale": actual_stale,
                "actual_slippage_bias": actual_slippage_bias,
            },
            ts_ms=int(time.time() * 1000),
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "items": self._repo.list_priors(limit=300)
            or list((self._state.get("priors") or {}).values()),
            "quarantine": dict(self._state.get("quarantine") or {}),
            "explorationBudget": self.exploration_budget(),
        }
