from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (json.JSONDecodeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _status(ok: bool, code: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": bool(ok), "code": str(code)}
    payload.update(extra)
    return payload


def _coerce_float(value: Any, default: float = 0.0) -> Tuple[float, bool]:
    try:
        return float(value if value is not None else default), True
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default), False


@dataclass
class OnlineLinearCalibrator:
    """Very small online calibrator to support ML/RL adaptation.

    This is intentionally simple and safe:
      - Only updates when enabled via env `VICTOR_AGENT_LEARN=1`.
      - Bounded learning rate and weights.
      - Stores per-agent weights to JSON under data_dir/aqe/agents/.
    """

    name: str
    data_dir: str
    lr: float = 0.02
    max_w: float = 3.0
    enabled: bool = False

    w: Dict[str, float] = field(default_factory=dict)
    last_save_ts: float = 0.0
    _runtime: Dict[str, Dict[str, Any]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled or os.environ.get("VICTOR_AGENT_LEARN", "0") == "1")
        self._path = os.path.join(self.data_dir, "aqe", "agents", f"{self._safe(self.name)}.json")
        self._runtime = {
            "load": _status(True, "calibration_load_idle"),
            "save": _status(True, "calibration_save_idle"),
            "apply": _status(True, "calibration_apply_idle"),
            "update": _status(True, "calibration_update_idle"),
        }
        self._load()

    def _safe(self, s: str) -> str:
        return "".join([c.lower() if c.isalnum() else "_" for c in (s or "agent")])[:80]

    def _mark(self, bucket: str, ok: bool, code: str, **extra: Any) -> None:
        self._runtime[str(bucket)] = _status(ok, code, **extra)

    def state(self) -> Dict[str, Any]:
        payload = {k: dict(v) for k, v in self._runtime.items()}
        failures = [payload[k] for k in ("load", "save", "apply", "update") if not bool(payload[k].get("ok", False))]
        if failures:
            payload["ok"] = False
            payload["code"] = str(failures[0].get("code", "calibration_degraded"))
        else:
            payload["ok"] = True
            payload["code"] = str(payload.get("apply", {}).get("code", "calibration_ok"))
        payload["degraded"] = not bool(payload["ok"])
        return payload

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self.w = {}
            self._mark("load", True, "calibration_load_absent", count=0)
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.loads(fh.read() or "{}")
        except _SAFE_IO_EXCEPTIONS:
            self.w = {}
            self._mark("load", False, "calibration_load_failed")
            return
        except _SAFE_JSON_EXCEPTIONS:
            self.w = {}
            self._mark("load", False, "calibration_load_failed")
            return

        weights = raw.get("w") or {}
        if not isinstance(weights, dict):
            self.w = {}
            self._mark("load", False, "calibration_load_invalid")
            return

        invalid = []
        loaded: Dict[str, float] = {}
        for k, v in weights.items():
            fv, ok = _coerce_float(v, 0.0)
            key = str(k)
            if ok:
                loaded[key] = float(_clip(fv, -self.max_w, self.max_w))
            else:
                invalid.append(key)
        self.w = loaded
        self._mark(
            "load",
            not bool(invalid),
            "calibration_load_ok" if not invalid else "calibration_load_partial",
            invalid=invalid,
            count=len(self.w),
        )

    def _save(self) -> None:
        directory = os.path.dirname(self._path)
        tmp_path = f"{self._path}.tmp"
        try:
            os.makedirs(directory, exist_ok=True)
            raw = {"ts": int(time.time()), "w": dict(self.w)}
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(raw, indent=2, sort_keys=True))
            os.replace(tmp_path, self._path)
            self.last_save_ts = time.time()
            self._mark("save", True, "calibration_save_ok", count=len(self.w))
        except _SAFE_IO_EXCEPTIONS:
            self._mark("save", False, "calibration_save_failed")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except _SAFE_IO_EXCEPTIONS:
                pass
        except _SAFE_JSON_EXCEPTIONS:
            self._mark("save", False, "calibration_save_failed")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except _SAFE_IO_EXCEPTIONS:
                pass

    def apply(self, features: Mapping[str, Any] | Dict[str, Any] | None) -> float:
        """Return linear score adjustment based on learned weights."""
        score = 0.0
        invalid = []
        for key, value in dict(features or {}).items():
            feature_value, feature_ok = _coerce_float(value, 0.0)
            weight_value, weight_ok = _coerce_float(self.w.get(str(key), 0.0), 0.0)
            if not feature_ok or not weight_ok:
                invalid.append(str(key))
                continue
            score += float(weight_value) * float(feature_value)
        self._mark(
            "apply",
            not bool(invalid),
            "calibration_apply_ok" if not invalid else "calibration_apply_partial",
            invalid=invalid,
        )
        return float(score)

    def update(self, *, reward: float, features: Mapping[str, Any] | Dict[str, Any] | None) -> None:
        if not self.enabled:
            self._mark("update", True, "calibration_update_disabled")
            return
        reward_value, _ = _coerce_float(reward, 0.0)
        r = float(_clip(reward_value, -1.0, 1.0))
        invalid = []
        for key, value in dict(features or {}).items():
            feature_value, feature_ok = _coerce_float(value, 0.0)
            prev_value, _ = _coerce_float(self.w.get(str(key), 0.0), 0.0)
            if not feature_ok:
                invalid.append(str(key))
                continue
            g = r * float(feature_value)
            self.w[str(key)] = float(_clip(float(prev_value) + self.lr * g, -self.max_w, self.max_w))
        self._mark(
            "update",
            not bool(invalid),
            "calibration_update_ok" if not invalid else "calibration_update_partial",
            invalid=invalid,
            count=len(self.w),
        )
        if (time.time() - float(self.last_save_ts)) > 10.0:
            self._save()
