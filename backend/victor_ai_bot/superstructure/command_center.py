from __future__ import annotations

from ..pathing import canonical_data_dir

import json
import os
import time
from typing import Any, Dict

from ..caq_kds.bus import BUS

_SAFE_AUDIT_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_BUS_EXCEPTIONS = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


class CommandCenter:
    """Human command & control layer (Phase 17).

    Add-only, admin-gated via API.
    All actions are written to an append-only audit ledger.
    """

    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain or "global")
        root = canonical_data_dir(str(data_dir or "") or "backend/data")
        self._path = os.path.join(root, "superstructure", f"human_audit_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

        self._directive: Dict[str, Any] = {}
        self._directive_until: float = 0.0
        self._risk_multiplier: float = 1.0
        self._exploration_cap: float = 1.0
        self._approvals: Dict[str, float] = {}
        self._audit_status: Dict[str, Any] = {
            "ok": True,
            "path": self._path,
            "last_error_code": "",
            "last_error": "",
            "last_write_ts": 0.0,
        }
        self._bus_status: Dict[str, Any] = {
            "ok": True,
            "last_bucket": "",
            "last_error_code": "",
            "last_error": "",
            "last_publish_ts": 0.0,
        }

    def _mark_audit_ok(self) -> None:
        self._audit_status.update(
            {
                "ok": True,
                "last_error_code": "",
                "last_error": "",
                "last_write_ts": float(time.time()),
            }
        )

    def _mark_audit_error(self, code: str, exc: BaseException) -> None:
        self._audit_status.update(
            {
                "ok": False,
                "last_error_code": str(code or "audit_failed"),
                "last_error": str(exc),
            }
        )

    def _mark_bus_ok(self, bucket: str) -> None:
        self._bus_status.update(
            {
                "ok": True,
                "last_bucket": str(bucket or ""),
                "last_error_code": "",
                "last_error": "",
                "last_publish_ts": float(time.time()),
            }
        )

    def _mark_bus_error(self, bucket: str, code: str, exc: BaseException) -> None:
        self._bus_status.update(
            {
                "ok": False,
                "last_bucket": str(bucket or ""),
                "last_error_code": str(code or "bus_publish_failed"),
                "last_error": str(exc),
            }
        )

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        offset = 0
        total = len(payload)
        while offset < total:
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("command_center_short_write")
            offset += int(written)

    def _append_record(self, rec: Dict[str, Any]) -> None:
        payload = json.dumps(rec, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        fd = os.open(self._path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            self._write_all(fd, payload)
        finally:
            os.close(fd)

    def _publish(self, bucket: str, payload: Dict[str, Any]) -> None:
        BUS.update(str(bucket or "default"), dict(payload or {}))

    def _write(self, action: str, payload: Dict[str, Any]) -> None:
        rec = {
            "ts": float(time.time()),
            "chain": self.chain,
            "action": str(action),
            "payload": dict(payload or {}),
        }
        try:
            self._append_record(rec)
            self._mark_audit_ok()
        except _SAFE_AUDIT_EXCEPTIONS as exc:
            self._mark_audit_error("audit_append_failed", exc)
        try:
            self._publish("human", {"last_action": rec})
            self._mark_bus_ok("human")
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bus_error("human", "bus_publish_failed", exc)

    def set_directive(self, directive: Dict[str, Any], *, ttl_s: float = 6 * 3600.0) -> None:
        self._directive = dict(directive or {})
        ttl = float(max(0.0, float(ttl_s or 0.0)))
        self._directive_until = float(time.time() + ttl) if ttl > 0 else 0.0
        self._write("set_directive", {"directive": self._directive, "ttl_s": ttl})

    def directive(self) -> Dict[str, Any]:
        if self._directive_until and time.time() > self._directive_until:
            self._directive = {}
            self._directive_until = 0.0
        return dict(self._directive or {})

    def set_risk_multiplier(self, m: float) -> None:
        self._risk_multiplier = float(max(0.10, min(2.0, float(m))))
        self._write("set_risk_multiplier", {"risk_multiplier": self._risk_multiplier})

    def risk_multiplier(self) -> float:
        return float(self._risk_multiplier)

    def set_exploration_cap(self, cap: float) -> None:
        self._exploration_cap = float(max(0.0, min(1.0, float(cap))))
        self._write("set_exploration_cap", {"exploration_cap": self._exploration_cap})

    def exploration_cap(self) -> float:
        return float(self._exploration_cap)

    def approve(self, proposal_id: str, *, ttl_s: float = 600.0) -> None:
        pid = str(proposal_id or "")
        if not pid:
            return
        ttl = float(max(10.0, float(ttl_s or 0.0)))
        self._approvals[pid] = float(time.time() + ttl)
        self._write("approve", {"proposal_id": pid, "ttl_s": ttl})

    def is_approved(self, proposal_id: str) -> bool:
        pid = str(proposal_id or "")
        if not pid:
            return False
        until = float(self._approvals.get(pid, 0.0) or 0.0)
        if until <= 0.0:
            return False
        if time.time() > until:
            self._approvals.pop(pid, None)
            return False
        return True

    def state(self) -> Dict[str, Any]:
        audit = dict(self._audit_status)
        bus = dict(self._bus_status)
        return {
            "ok": True,
            "audit": audit,
            "bus": bus,
            "degraded": (not bool(audit.get("ok", True)) or not bool(bus.get("ok", True))),
        }

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        expired = [k for k, v in (self._approvals or {}).items() if float(v or 0.0) <= now]
        for k in expired:
            self._approvals.pop(k, None)
        snap = {
            "ok": True,
            "enabled": True,
            "chain": self.chain,
            "directive": self.directive(),
            "risk_multiplier": float(self._risk_multiplier),
            "exploration_cap": float(self._exploration_cap),
            "approvals": {k: float(v) for k, v in (self._approvals or {}).items()},
            "storage": self.state(),
        }
        try:
            self._publish("command", snap)
            self._mark_bus_ok("command")
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bus_error("command", "bus_publish_failed", exc)
            snap["storage"] = self.state()
        return snap
