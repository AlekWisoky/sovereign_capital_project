from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from victor_ai_bot.determinism import stable_hash_int

_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError)
_SAFE_RUNTIME_EXCEPTIONS = (TypeError, ValueError, KeyError, AttributeError)


def _status(ok: bool, reason_code: str, *, path: str, detail: str = "") -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "reasonCode": str(reason_code),
        "path": str(path),
        "detail": str(detail or ""),
    }


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    da = 0.0
    db = 0.0
    dp = 0.0
    for x, y in zip(a, b):
        dx = float(x)
        dy = float(y)
        dp += dx * dy
        da += dx * dx
        db += dy * dy
    if da <= 1e-12 or db <= 1e-12:
        return 0.0
    return float(dp / math.sqrt(da * db))


def _round_vec(vec: List[float], ndigits: int = 3) -> List[float]:
    return [float(round(float(x), int(ndigits))) for x in (vec or [])]


@dataclass(frozen=True)
class RegimePrototype:
    label: str
    vec: List[float]
    description: str


class RegimeLibrary:
    """Deterministic regime library.

    We keep a small set of hand-designed prototypes. This is stable,
    interpretable, and works offline.
    """

    def __init__(self):
        self.prototypes: List[RegimePrototype] = [
            RegimePrototype("calm", [0.2, 0.2, 0.2, 0.2], "Low volatility, low MEV, normal basefee"),
            RegimePrototype("high_vol", [0.9, 0.4, 0.6, 0.3], "High volatility / unstable spreads"),
            RegimePrototype("mev_stress", [0.5, 0.9, 0.8, 0.5], "High mempool competition / MEV risk"),
            RegimePrototype("gas_spike", [0.4, 0.4, 0.9, 0.9], "High basefee or gas spikes"),
            RegimePrototype("risk_off", [0.8, 0.6, 0.7, 0.7], "Risk-off environment"),
        ]

    def classify(self, *, vec: List[float]) -> Tuple[str, float, Dict[str, Any]]:
        best = ("unknown", 0.0, "")
        for p in self.prototypes:
            sim = _cosine(vec, p.vec)
            if sim > float(best[1]):
                best = (p.label, sim, p.description)
        return str(best[0]), float(_clip(best[1], 0.0, 1.0)), {"description": str(best[2])}


class PersistentRegimeLibrary(RegimeLibrary):
    """RegimeLibrary with a deterministic, local, append-only memory of custom regimes.

    This allows BehaveAgent to:
      - create NEW_REGIME_PROFILE when similarity is low
      - cluster future observations into those custom regimes (via cosine similarity)
    """

    def __init__(self, *, path: str, max_prototypes: int = 200, enabled: bool = True):
        super().__init__()
        self.path = str(path)
        self.max_prototypes = int(max(0, max_prototypes))
        self.enabled = bool(enabled)
        self._custom: List[Dict[str, Any]] = []
        self._load_status = _status(True, "regime_memory_idle", path=self.path)
        self._save_status = _status(True, "regime_memory_idle", path=self.path)
        self._touch_status = _status(True, "regime_memory_idle", path=self.path)
        self._load()

    def _load(self) -> None:
        if not self.enabled:
            self._load_status = _status(True, "regime_memory_disabled", path=self.path)
            return
        if not os.path.exists(self.path):
            self._load_status = _status(True, "regime_memory_missing", path=self.path)
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            items = raw.get("prototypes") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                self._load_status = _status(True, "regime_memory_empty", path=self.path)
                return
            for it in items:
                if not isinstance(it, dict):
                    continue
                label = str(it.get("label") or "")
                vec = it.get("vec") or []
                if not label or not isinstance(vec, list):
                    continue
                desc = str(it.get("description") or "Auto-discovered regime")
                self.prototypes.append(RegimePrototype(label, [float(x) for x in vec], desc))
                self._custom.append(
                    {
                        "label": label,
                        "vec": [float(x) for x in vec],
                        "description": desc,
                        "created_ts": int(it.get("created_ts") or 0),
                        "n_seen": int(it.get("n_seen") or 0),
                        "last_seen_ts": int(it.get("last_seen_ts") or (it.get("created_ts") or 0)),
                    }
                )
            self._load_status = _status(True, "regime_memory_loaded", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._load_status = _status(
                False,
                "regime_memory_invalid_json",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._load_status = _status(
                False,
                "regime_memory_read_failed",
                path=self.path,
                detail=str(exc),
            )

    def _save(self) -> None:
        if not self.enabled:
            self._save_status = _status(True, "regime_memory_disabled", path=self.path)
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {"prototypes": list(self._custom)}
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
            self._save_status = _status(True, "regime_memory_saved", path=self.path)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "regime_memory_serialize_failed",
                path=self.path,
                detail=str(exc),
            )
        except _SAFE_IO_EXCEPTIONS as exc:
            self._save_status = _status(
                False,
                "regime_memory_save_failed",
                path=self.path,
                detail=str(exc),
            )

    def maybe_create_profile(self, *, vec: List[float], similarity: float, similarity_threshold: float) -> Tuple[str, float, Dict[str, Any]]:
        """Create or reuse a deterministic custom regime label when similarity is low."""
        if not self.enabled:
            return "unknown", float(similarity), {"description": ""}
        if float(similarity) >= float(similarity_threshold):
            return "unknown", float(similarity), {"description": ""}

        rv = _round_vec(vec, ndigits=3)
        key = json.dumps(rv, sort_keys=True, separators=(",", ":"))
        hid = stable_hash_int(f"custom_regime:{key}", modulo=10**12)
        label = f"custom_{hid:012x}"
        if any(str(p.label) == label for p in self.prototypes):
            for it in self._custom:
                if str(it.get("label")) == label:
                    it["n_seen"] = int(it.get("n_seen") or 0) + 1
                    it["last_seen_ts"] = int(time.time())
                    self._save()
                    break
            return label, float(similarity), {"description": "Auto-discovered regime", "auto": True}

        self.prototypes.append(RegimePrototype(label, list(rv), "Auto-discovered regime"))
        self._custom.append(
            {
                "label": label,
                "vec": list(rv),
                "description": "Auto-discovered regime",
                "created_ts": int(time.time()),
                "n_seen": 1,
                "last_seen_ts": int(time.time()),
            }
        )
        if self.max_prototypes > 0 and len(self._custom) > self.max_prototypes:
            self._custom = self._custom[-self.max_prototypes :]
            core = RegimeLibrary().prototypes
            self.prototypes = list(core) + [
                RegimePrototype(
                    str(it["label"]),
                    list(it["vec"]),
                    str(it.get("description") or "Auto-discovered regime"),
                )
                for it in self._custom
            ]
        self._save()
        return label, float(similarity), {"description": "Auto-discovered regime", "auto": True}

    def touch(self, *, label: str) -> None:
        """Update last_seen/n_seen for an existing custom regime (best-effort)."""
        if not self.enabled:
            self._touch_status = _status(True, "regime_memory_disabled", path=self.path)
            return
        lab = str(label or "")
        if not lab.startswith("custom_"):
            self._touch_status = _status(True, "regime_memory_touch_skipped", path=self.path)
            return
        try:
            changed = False
            for it in self._custom:
                if str(it.get("label")) == lab:
                    it["n_seen"] = int(it.get("n_seen") or 0) + 1
                    it["last_seen_ts"] = int(time.time())
                    changed = True
                    break
            if changed:
                self._save()
                self._touch_status = _status(True, "regime_memory_touched", path=self.path)
            else:
                self._touch_status = _status(True, "regime_memory_touch_missing", path=self.path)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._touch_status = _status(
                False,
                "regime_memory_touch_failed",
                path=self.path,
                detail=str(exc),
            )

    def state(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "load": dict(self._load_status),
            "save": dict(self._save_status),
            "touch": dict(self._touch_status),
            "customCount": int(len(self._custom)),
            "degraded": bool(
                not self._load_status.get("ok", True)
                or not self._save_status.get("ok", True)
                or not self._touch_status.get("ok", True)
            ),
        }


def build_regime_vector(
    *,
    basefee_gwei: float,
    mev_risk: float,
    pending_rate: float,
    volatility_proxy: float,
    liquidity_score: float | None = None,
    sentiment_score: float | None = None,
) -> List[float]:
    """Create a small normalized regime vector (MME_VECTOR).

    Design constraints:
      - cheap to compute
      - deterministic
      - fixed dimensionality so cosine similarity stays meaningful

    Vector order (4 dims):
      0: volatility proxy
      1: MEV / competition proxy
      2: gas/basefee proxy
      3: pending pressure proxy
    """

    g = _clip(float(basefee_gwei) / 100.0, 0.0, 1.0)
    m = _clip(float(mev_risk), 0.0, 1.0)
    p = _clip(float(pending_rate) / 5000.0, 0.0, 1.0)
    v = _clip(float(volatility_proxy), 0.0, 1.0)

    if liquidity_score is not None:
        l = _clip(float(liquidity_score), 0.0, 1.0)
        v = _clip(v * (1.0 + (1.0 - l) * 0.35), 0.0, 1.0)
        p = _clip(p * (1.0 + (1.0 - l) * 0.25), 0.0, 1.0)
    if sentiment_score is not None:
        s = _clip(float(sentiment_score), 0.0, 1.0)
        v = _clip(v * (1.0 + abs(s - 0.5) * 0.20), 0.0, 1.0)
        m = _clip(m * (1.0 + abs(s - 0.5) * 0.15), 0.0, 1.0)

    return [v, m, g, p]


def detect_regime(
    *,
    features: Dict[str, Any],
    library: RegimeLibrary,
    similarity_threshold: float = 0.72,
) -> Tuple[str, float, Dict[str, Any], List[float]]:
    """Detect a regime label + confidence from feature streams.

    This function is deterministic for the same inputs and same library state.
    """

    f = dict(features or {})
    vec = build_regime_vector(
        basefee_gwei=float(f.get("basefee_gwei", 0.0) or 0.0),
        mev_risk=float(f.get("mev_risk", 0.0) or 0.0),
        pending_rate=float(f.get("pending_rate", 0.0) or 0.0),
        volatility_proxy=float(f.get("volatility_proxy", 0.0) or 0.0),
        liquidity_score=(float(f.get("liquidity_score")) if f.get("liquidity_score") is not None else None),
        sentiment_score=(float(f.get("sentiment_score")) if f.get("sentiment_score") is not None else None),
    )
    label, sim, info = library.classify(vec=vec)
    sim_thr = float(similarity_threshold)
    if float(sim) < sim_thr:
        if isinstance(library, PersistentRegimeLibrary):
            cl, _, extra = library.maybe_create_profile(vec=vec, similarity=float(sim), similarity_threshold=sim_thr)
            if cl and cl != "unknown":
                label = cl
                try:
                    info = {**dict(info or {}), **dict(extra or {})}
                except _SAFE_RUNTIME_EXCEPTIONS:
                    info = dict(info or {})
        else:
            label = "unknown"
    return str(label), float(_clip(sim, 0.0, 1.0)), dict(info or {}), list(vec)
