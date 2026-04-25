from __future__ import annotations

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
class OnlineStats:
    """Deterministic online stats (Welford).

    Stores:
      - n observations
      - wins count
      - mean reward
      - variance (via m2)
    """

    n: int = 0
    wins: int = 0
    mean: float = 0.0
    m2: float = 0.0
    last_ts: int = 0

    def update(self, *, reward: float, ok: bool) -> None:
        r = float(reward)
        self.n += 1
        if bool(ok):
            self.wins += 1
        # Welford update (deterministic)
        delta = r - self.mean
        self.mean += delta / float(self.n)
        delta2 = r - self.mean
        self.m2 += delta * delta2
        self.last_ts = int(time.time())

    @property
    def win_rate(self) -> float:
        return float(self.wins) / float(self.n) if self.n > 0 else 0.0

    @property
    def variance(self) -> float:
        return float(self.m2) / float(self.n - 1) if self.n > 1 else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "n": int(self.n),
            "wins": int(self.wins),
            "mean": float(self.mean),
            "variance": float(self.variance),
            "win_rate": float(self.win_rate),
            "last_ts": int(self.last_ts),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OnlineStats":
        return cls(
            n=int(d.get("n") or 0),
            wins=int(d.get("wins") or 0),
            mean=float(d.get("mean") or 0.0),
            m2=float(d.get("m2") or 0.0),
            last_ts=int(d.get("last_ts") or 0),
        )


class RegimeStrategyMemory:
    """Local deterministic memory of strategy outcomes per regime.

    - Purely advisory: influences scoring only (priority matrix).
    - Deterministic updates: no randomness.
    - State is part of the input state (persisted JSON), so repeated runs
      with identical history produce identical outputs.
    """

    def __init__(
        self,
        *,
        path: str,
        min_samples_for_boost: int = 8,
        max_weight_boost: float = 1.15,
        max_weight_penalty: float = 0.85,
        enabled: bool = True,
    ):
        self.path = str(path)
        self.enabled = bool(enabled)
        self.min_samples_for_boost = int(max(1, min_samples_for_boost))
        self.max_weight_boost = float(max_weight_boost)
        self.max_weight_penalty = float(max_weight_penalty)
        self._mem: Dict[str, Dict[str, OnlineStats]] = {}
        self._dirty = False
        self._load_status = _status(True, "strategy_memory_idle", path=self.path)
        self._save_status = _status(True, "strategy_memory_idle", path=self.path)
        self._load()

    def _load(self) -> None:
        if not self.enabled:
            self._load_status = _status(True, "strategy_memory_disabled", path=self.path)
            return
        if not os.path.exists(self.path):
            self._load_status = _status(True, "strategy_memory_missing", path=self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            out: Dict[str, Dict[str, OnlineStats]] = {}
            for regime, per in (raw or {}).items():
                if not isinstance(per, dict):
                    continue
                out[regime] = {}
                for st, sd in per.items():
                    if isinstance(sd, dict):
                        osd = OnlineStats(
                            n=int(sd.get("n") or 0),
                            wins=int(sd.get("wins") or 0),
                            mean=float(sd.get("mean") or 0.0),
                            m2=float(sd.get("m2") or 0.0),
                            last_ts=int(sd.get("last_ts") or 0),
                        )
                        out[regime][st] = osd
            self._mem = out
            self._load_status = _status(True, "strategy_memory_loaded", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._mem = {}
            self._load_status = _status(
                False,
                "strategy_memory_invalid_json",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mem = {}
            self._load_status = _status(
                False,
                "strategy_memory_read_failed",
                path=self.path,
                detail=str(exc),
            )

    def _save(self) -> None:
        if not (self.enabled and self._dirty):
            if not self.enabled:
                self._save_status = _status(True, "strategy_memory_disabled", path=self.path)
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            raw: Dict[str, Any] = {}
            for regime, per in self._mem.items():
                raw[regime] = {}
                for st, stats in per.items():
                    d = stats.as_dict()
                    d["m2"] = float(stats.m2)
                    raw[regime][st] = d
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
            self._dirty = False
            self._save_status = _status(True, "strategy_memory_saved", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "strategy_memory_serialize_failed",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "strategy_memory_save_failed",
                path=self.path,
                detail=str(exc),
            )

    def update(self, *, regime: str, strategy_type: str, reward: float, ok: bool) -> None:
        if not self.enabled:
            return
        r = str(regime or "unknown")
        s = str(strategy_type or "unknown")
        if r not in self._mem:
            self._mem[r] = {}
        if s not in self._mem[r]:
            self._mem[r][s] = OnlineStats()
        self._mem[r][s].update(reward=float(reward), ok=bool(ok))
        self._dirty = True
        self._save()

    def boost_map(self, *, regime: str) -> Dict[str, float]:
        """Return multiplicative boosts for each strategy in a regime.

        Values are clipped to [max_weight_penalty, max_weight_boost].
        """
        if not self.enabled:
            return {}
        r = str(regime or "unknown")
        per = self._mem.get(r) or {}
        means = [float(st.mean) for st in per.values() if int(st.n) >= self.min_samples_for_boost]
        base = float(sum(means) / len(means)) if means else 0.0
        out: Dict[str, float] = {}
        for stype, stats in per.items():
            if int(stats.n) < self.min_samples_for_boost:
                continue
            adv = float(stats.mean - base)
            wr = float(stats.win_rate)
            mult = 1.0
            mult += _clip(adv * 0.80, -0.10, 0.10)
            mult += _clip((wr - 0.5) * 0.25, -0.10, 0.10)
            out[str(stype)] = float(_clip(mult, float(self.max_weight_penalty), float(self.max_weight_boost)))
        return out

    def summary(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "regimes": 0}
        regimes = len(self._mem)
        top = []
        for r, per in self._mem.items():
            n = sum(int(s.n) for s in per.values())
            top.append((n, r))
        top.sort(reverse=True)
        return {
            "enabled": True,
            "regimes": int(regimes),
            "top_regimes": [r for _, r in top[:5]],
        }

    def state(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "load": dict(self._load_status),
            "save": dict(self._save_status),
            "degraded": bool(
                not self._load_status.get("ok", True)
                or not self._save_status.get("ok", True)
            ),
        }
