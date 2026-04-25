from __future__ import annotations

import json
from typing import Any, Dict

from ..db import PersistenceDB


class CapitalRecoveryRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    @staticmethod
    def _int_like(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def load(self, component: str) -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM capital_recovery_state WHERE chain=? AND component=?",
                (self.chain, str(component)),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def observe(
        self,
        *,
        component: str,
        degraded: bool,
        ts_ms: int,
        reason_code: str = "",
    ) -> Dict[str, Any]:
        component_name = str(component)
        now_ms = self._int_like(ts_ms)
        current = self.load(component_name)
        was_degraded = bool(current.get("is_degraded", False))
        degraded_since_ts_ms = self._int_like(current.get("degraded_since_ts_ms"))
        last_recovered_ts_ms = self._int_like(current.get("last_recovered_ts_ms"))
        degraded_count = self._int_like(current.get("degraded_count"))
        last_healthy_ts_ms = self._int_like(current.get("last_healthy_ts_ms"))
        if degraded:
            if not was_degraded or degraded_since_ts_ms <= 0:
                degraded_since_ts_ms = now_ms
                degraded_count = max(0, degraded_count) + 1
        else:
            if was_degraded:
                last_recovered_ts_ms = now_ms
            degraded_since_ts_ms = 0
            if now_ms > 0:
                last_healthy_ts_ms = now_ms
        payload = {
            "component": component_name,
            "is_degraded": bool(degraded),
            "degraded_since_ts_ms": int(degraded_since_ts_ms or 0),
            "last_recovered_ts_ms": int(last_recovered_ts_ms or 0),
            "degraded_count": int(degraded_count or 0),
            "last_healthy_ts_ms": int(last_healthy_ts_ms or 0),
            "updated_ts_ms": int(now_ms or 0),
            "last_reason_code": str(reason_code or ("degraded" if degraded else "ok")),
        }
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO capital_recovery_state(
                    chain, component, is_degraded, degraded_since_ts_ms, last_recovered_ts_ms,
                    updated_ts_ms, last_reason_code, payload_json
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    self.chain,
                    component_name,
                    1 if degraded else 0,
                    int(payload["degraded_since_ts_ms"]),
                    int(payload["last_recovered_ts_ms"]),
                    int(payload["updated_ts_ms"]),
                    str(payload["last_reason_code"]),
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return payload
