from __future__ import annotations

"""Deterministic calibration loop logging for BehaveAgent.

This module tracks how well regime-confidence predictions align with realized
outcomes over time and persists the stats to disk.

Design goals:
- Deterministic for the same sequence of observations.
- Small JSON footprint.
- Best-effort, never crashes runtime.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict

_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _status(ok: bool, reason_code: str, *, path: str, detail: str = "") -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "reasonCode": str(reason_code),
        "path": str(path),
        "detail": str(detail or ""),
    }


@dataclass
class CalibrationStats:
    n: int = 0
    wins: int = 0

    mean_conf: float = 0.0
    m2_conf: float = 0.0

    mean_reward: float = 0.0
    m2_reward: float = 0.0

    last_ts: int = 0

    def update(self, *, confidence: float, reward: float, ok: bool) -> None:
        c = float(_clip(float(confidence), 0.0, 1.0))
        r = float(reward)
        self.n += 1
        if bool(ok):
            self.wins += 1

        dc = c - self.mean_conf
        self.mean_conf += dc / float(self.n)
        dc2 = c - self.mean_conf
        self.m2_conf += dc * dc2

        dr = r - self.mean_reward
        self.mean_reward += dr / float(self.n)
        dr2 = r - self.mean_reward
        self.m2_reward += dr * dr2

        self.last_ts = int(time.time())

    @property
    def win_rate(self) -> float:
        return float(self.wins) / float(self.n) if self.n > 0 else 0.0

    @property
    def conf_variance(self) -> float:
        return float(self.m2_conf) / float(self.n - 1) if self.n > 1 else 0.0

    @property
    def reward_variance(self) -> float:
        return float(self.m2_reward) / float(self.n - 1) if self.n > 1 else 0.0

    @property
    def calibration_error(self) -> float:
        return float(abs(self.win_rate - self.mean_conf))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "n": int(self.n),
            "wins": int(self.wins),
            "win_rate": float(self.win_rate),
            "mean_conf": float(self.mean_conf),
            "conf_variance": float(self.conf_variance),
            "mean_reward": float(self.mean_reward),
            "reward_variance": float(self.reward_variance),
            "calibration_error": float(self.calibration_error),
            "last_ts": int(self.last_ts),
            "m2_conf": float(self.m2_conf),
            "m2_reward": float(self.m2_reward),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibrationStats":
        return cls(
            n=int(d.get("n") or 0),
            wins=int(d.get("wins") or 0),
            mean_conf=float(d.get("mean_conf") or 0.0),
            m2_conf=float(d.get("m2_conf") or 0.0),
            mean_reward=float(d.get("mean_reward") or 0.0),
            m2_reward=float(d.get("m2_reward") or 0.0),
            last_ts=int(d.get("last_ts") or 0),
        )


class CalibrationTracker:
    def __init__(self, *, path: str, enabled: bool = True):
        self.path = str(path)
        self.enabled = bool(enabled)
        self._mem: Dict[str, CalibrationStats] = {}
        self._dirty = False
        self._load_status = _status(True, "calibration_idle", path=self.path)
        self._save_status = _status(True, "calibration_idle", path=self.path)
        self._log_status = _status(True, "calibration_idle", path=self.path)
        self._load()

    def _load(self) -> None:
        if not self.enabled:
            self._load_status = _status(True, "calibration_disabled", path=self.path)
            return
        if not os.path.exists(self.path):
            self._load_status = _status(True, "calibration_missing", path=self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            regimes = raw.get("regimes") if isinstance(raw, dict) else raw
            if not isinstance(regimes, dict):
                self._load_status = _status(True, "calibration_empty", path=self.path)
                return
            out: Dict[str, CalibrationStats] = {}
            for k, v in regimes.items():
                if isinstance(v, dict):
                    out[str(k)] = CalibrationStats.from_dict(v)
            self._mem = out
            self._load_status = _status(True, "calibration_loaded", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._mem = {}
            self._load_status = _status(
                False,
                "calibration_invalid_json",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mem = {}
            self._load_status = _status(
                False,
                "calibration_read_failed",
                path=self.path,
                detail=str(exc),
            )

    def _save(self) -> None:
        if not (self.enabled and self._dirty):
            if not self.enabled:
                self._save_status = _status(True, "calibration_disabled", path=self.path)
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {"regimes": {k: st.as_dict() for k, st in self._mem.items()}}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
            self._dirty = False
            self._save_status = _status(True, "calibration_saved", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "calibration_serialize_failed",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "calibration_save_failed",
                path=self.path,
                detail=str(exc),
            )

    def observe(self, *, regime: str, confidence: float, reward: float, ok: bool, strategy_type: str = "") -> None:
        if not self.enabled:
            return
        r = str(regime or "unknown")
        if r not in self._mem:
            self._mem[r] = CalibrationStats()
        self._mem[r].update(confidence=float(confidence), reward=float(reward), ok=bool(ok))
        self._dirty = True
        self._save()
        log_path = os.path.join(os.path.dirname(self.path), "calibration_log.jsonl")
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            row = {
                "ts": int(time.time()),
                "regime_label": r,
                "confidence": float(_clip(float(confidence), 0.0, 1.0)),
                "reward": float(reward),
                "ok": bool(ok),
                "strategy_type": str(strategy_type or ""),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
            self._log_status = _status(True, "calibration_log_appended", path=log_path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._log_status = _status(
                False,
                "calibration_log_serialize_failed",
                path=log_path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._log_status = _status(
                False,
                "calibration_log_append_failed",
                path=log_path,
                detail=str(exc),
            )

    def summary(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        top = sorted(((st.n, r) for r, st in self._mem.items()), reverse=True)
        top_reg = [r for _, r in top[:5]]
        tot = sum(int(st.n) for st in self._mem.values()) or 0
        werr = 0.0
        for st in self._mem.values():
            if tot > 0:
                werr += float(st.calibration_error) * (float(st.n) / float(tot))
        return {
            "enabled": True,
            "regimes": int(len(self._mem)),
            "total_samples": int(tot),
            "weighted_calibration_error": float(werr),
            "top_regimes": top_reg,
        }

    def state(self) -> Dict[str, Any]:
        log_path = os.path.join(os.path.dirname(self.path), "calibration_log.jsonl")
        return {
            "path": self.path,
            "logPath": log_path,
            "load": dict(self._load_status),
            "save": dict(self._save_status),
            "log": dict(self._log_status),
            "degraded": bool(
                not self._load_status.get("ok", True)
                or not self._save_status.get("ok", True)
                or not self._log_status.get("ok", True)
            ),
        }
