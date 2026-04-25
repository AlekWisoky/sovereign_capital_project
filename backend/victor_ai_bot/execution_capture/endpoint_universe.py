from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping


_SAFE_PREFERENCE_SNAPSHOT_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_MANAGER_SNAPSHOT_EXCEPTIONS = (AttributeError, TypeError, ValueError)


@dataclass(frozen=True)
class EndpointCandidate:
    url: str
    lane: str
    endpoint_type: str
    privacy_class: str
    operator_preferred: bool
    allowed: bool
    source: str
    score_hint: float
    latency_ms: float


class EndpointUniverse:
    def __init__(
        self, *, cfg: Any, rpc_manager: Any | None = None, rpc_preferences: Any | None = None
    ):
        self.cfg = cfg
        self.rpc_manager = rpc_manager
        self.rpc_preferences = rpc_preferences

    def _preferred_snapshot(self) -> Dict[str, List[str]]:
        try:
            snap = self.rpc_preferences.snapshot() if self.rpc_preferences is not None else {}
        except _SAFE_PREFERENCE_SNAPSHOT_EXCEPTIONS:
            snap = {}
        if not isinstance(snap, Mapping):
            snap = {}
        return {
            "read": [str(x) for x in list(snap.get("read") or []) if str(x)],
            "send": [str(x) for x in list(snap.get("send") or []) if str(x)],
            "private": [str(x) for x in list(snap.get("private") or []) if str(x)],
        }

    def _preferred(self, lane: str) -> List[str]:
        snap = self._preferred_snapshot()
        lane = str(lane or "").upper()
        if lane == "PRIVATE":
            return list(snap["private"]) + list(snap["send"])
        if lane == "PROTECTED":
            return list(snap["private"]) + list(snap["send"])
        if lane == "READ":
            return list(snap["read"])
        return list(snap["send"]) + list(snap["read"])

    def _configured(self, lane: str) -> List[str]:
        chain = getattr(self.cfg, "chain", None)
        lane = str(lane or "").upper()
        if lane == "PRIVATE":
            return list(getattr(chain, "rpc_private", []) or []) or list(
                getattr(chain, "rpc_send", []) or []
            )
        if lane == "PROTECTED":
            return list(getattr(chain, "rpc_private", []) or []) + list(
                getattr(chain, "rpc_send", []) or []
            )
        if lane == "READ":
            return list(getattr(chain, "rpc_read", []) or [])
        return list(getattr(chain, "rpc_send", []) or []) or list(
            getattr(chain, "rpc_read", []) or []
        )

    def _manager_rows(self, lane: str) -> Dict[str, Dict[str, Any]]:
        if self.rpc_manager is None:
            return {}
        try:
            snap = self.rpc_manager.snapshot() or {}
        except _SAFE_MANAGER_SNAPSHOT_EXCEPTIONS:
            return {}
        if not isinstance(snap, Mapping):
            return {}
        lane = str(lane or "").upper()
        bucket_names = ["send"]
        if lane == "READ":
            bucket_names = ["read"]
        elif lane in {"PRIVATE", "PROTECTED"}:
            bucket_names = ["private", "send"]
        rows = {}
        for bucket in bucket_names:
            for row in list(snap.get(bucket) or []):
                if isinstance(row, dict) and row.get("url"):
                    item = dict(row)
                    item["_bucket"] = bucket
                    rows[str(row["url"])] = item
        return rows

    def candidates(self, *, lane: str) -> Dict[str, Any]:
        lane = str(lane or "PUBLIC").upper()
        preferred = self._preferred(lane)
        configured = self._configured(lane)
        manager = self._manager_rows(lane)
        configured_private = set(getattr(self.cfg.chain, "rpc_private", []) or [])
        preferred_private = set(self._preferred_snapshot().get("private") or [])
        merged: List[EndpointCandidate] = []
        seen = set()
        order = preferred + configured + list(manager.keys())
        for url in order:
            key = str(url or "")
            if not key or key in seen:
                continue
            seen.add(key)
            row = dict(manager.get(key) or {})
            ok = bool(row.get("ok", True))
            is_relay = bool(
                key in configured_private
                or key in preferred_private
                or row.get("privacy") == "private"
                or row.get("relay")
                or row.get("_bucket") == "private"
            )
            endpoint_type = "relay" if is_relay else "rpc"
            privacy = "private" if is_relay else ("protected" if lane == "PROTECTED" else "public")
            score_hint = float(
                row.get("quality")
                or row.get("score")
                or (0.9 if key in preferred else 0.7 if key in configured else 0.55)
            )
            latency_ms = float(row.get("latency_ms_ema") or row.get("latency_ms") or 0.0)
            merged.append(
                EndpointCandidate(
                    url=key,
                    lane=lane,
                    endpoint_type=endpoint_type,
                    privacy_class=privacy,
                    operator_preferred=key in preferred,
                    allowed=ok or key in preferred,
                    source=(
                        "rpc_manager"
                        if key in manager
                        else ("preferences" if key in preferred else "config")
                    ),
                    score_hint=score_hint,
                    latency_ms=latency_ms,
                )
            )
        relays = [c.__dict__ for c in merged if c.allowed and c.endpoint_type == "relay"][:8]
        endpoints = [c.__dict__ for c in merged if c.allowed and c.endpoint_type == "rpc"][:8]
        if lane == "PRIVATE" and not relays:
            relays = [c.__dict__ for c in merged if c.allowed][:8]
        return {
            "lane": lane,
            "chain": str(getattr(getattr(self.cfg, "chain", None), "name", "") or ""),
            "candidates": endpoints,
            "relays": relays,
            "preferred": preferred,
            "configured": configured,
            "reason": (
                "operator_preferences"
                if preferred
                else ("manager_health" if manager else "config_default")
            ),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "read": self.candidates(lane="READ"),
            "public": self.candidates(lane="PUBLIC"),
            "protected": self.candidates(lane="PROTECTED"),
            "private": self.candidates(lane="PRIVATE"),
        }
