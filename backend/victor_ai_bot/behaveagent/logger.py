from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

_SAFE_IO_EXCEPTIONS = (OSError,)
_SAFE_JSON_EXCEPTIONS = (TypeError, ValueError)


def _status(ok: bool, reason_code: str, *, path: str, detail: str = "") -> Dict[str, Any]:
    return {
        "ok": bool(ok),
        "reasonCode": str(reason_code),
        "path": str(path),
        "detail": str(detail or ""),
    }


@dataclass
class ReasoningRecord:
    intent_id: str
    regime_label: str
    decision_factors: Dict[str, Any]
    workflow_tier: str
    risk_assessment: Dict[str, Any]
    simulation_result: Dict[str, Any] | None
    governance_outcome: str  # approved|rejected|escalated
    reviewer: str
    timestamp: int


class ImmutableReasoningLogger:
    """Append-only JSONL logger.

    Must never throw; logging is best-effort.
    """

    def __init__(self, *, path: str, max_bytes: int = 25 * 1024 * 1024):
        self.path = str(path)
        self.max_bytes = int(max_bytes)
        self._tail: List[Dict[str, Any]] = []
        self._append_status = _status(True, "reasoning_idle", path=self.path)
        self._truncate_status = _status(True, "reasoning_idle", path=self.path)
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._append_status = _status(
                False,
                "reasoning_dir_unavailable",
                path=self.path,
                detail=str(exc),
            )
            self._truncate_status = _status(
                False,
                "reasoning_dir_unavailable",
                path=self.path,
                detail=str(exc),
            )

    def append(self, row: Dict[str, Any]) -> None:
        try:
            payload = dict(row)
            payload.setdefault("ts", int(time.time()))
            line = json.dumps(payload, ensure_ascii=False)
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._append_status = _status(
                False,
                "reasoning_serialize_failed",
                path=self.path,
                detail=str(exc),
            )
            return

        tmp = self.path + ".tmp"
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except _SAFE_IO_EXCEPTIONS as exc:
            self._append_status = _status(
                False,
                "reasoning_append_failed",
                path=self.path,
                detail=str(exc),
            )
            return

        self._append_status = _status(True, "reasoning_appended", path=self.path)
        self._tail.append(payload)
        if len(self._tail) > 200:
            self._tail = self._tail[-200:]

        try:
            if os.path.getsize(self.path) <= self.max_bytes:
                self._truncate_status = _status(True, "reasoning_truncate_not_needed", path=self.path)
                return
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-2000:]
            with open(tmp, "w", encoding="utf-8") as f2:
                f2.writelines(lines)
            os.replace(tmp, self.path)
            self._truncate_status = _status(True, "reasoning_truncated", path=self.path)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._truncate_status = _status(
                False,
                "reasoning_truncate_failed",
                path=self.path,
                detail=str(exc),
            )

    def tail(self, n: int = 50) -> List[Dict[str, Any]]:
        return list(self._tail[-max(1, int(n)) :])

    def state(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "append": dict(self._append_status),
            "truncate": dict(self._truncate_status),
            "degraded": bool(
                not self._append_status.get("ok", True)
                or not self._truncate_status.get("ok", True)
            ),
        }
