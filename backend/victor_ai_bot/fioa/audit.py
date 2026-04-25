from __future__ import annotations

import json
import os
import time
from typing import Any, BinaryIO, Dict, List, Tuple

_SAFE_IO_EXCEPTIONS: Tuple[type[BaseException], ...] = (OSError, ValueError)
_SAFE_JSON_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    TypeError,
    ValueError,
    UnicodeError,
    json.JSONDecodeError,
)


class AuditLogger:
    """Append-only JSONL audit log.

    This is intentionally simple and dependency-free. It is safe for multi-task
    usage within a single process (uses atomic append writes on POSIX).
    """

    def __init__(self, path: str, *, max_bytes: int = 25_000_000, enabled: bool = True):
        self.path = str(path)
        self.max_bytes = int(max_bytes)
        self.enabled = bool(enabled)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._append_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_write_ts": 0,
        }
        self._tail_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_read_ts": 0,
        }
        self._compact_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_compact_ts": 0,
        }

    def _mark_state(self, state: Dict[str, Any], *, ok: bool, code: str = "", error: str = "", ts_key: str = "") -> None:
        state["ok"] = bool(ok)
        state["last_error_code"] = str(code or "")
        state["last_error"] = str(error or "")
        if ts_key:
            state[ts_key] = int(time.time()) if ok else int(state.get(ts_key) or 0)

    def _mark_append_ok(self) -> None:
        self._mark_state(self._append_state, ok=True, ts_key="last_write_ts")

    def _mark_append_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._append_state, ok=False, code=code, error=str(exc))

    def _mark_tail_ok(self) -> None:
        self._mark_state(self._tail_state, ok=True, ts_key="last_read_ts")

    def _mark_tail_error(self, code: str, exc: BaseException | str) -> None:
        self._mark_state(self._tail_state, ok=False, code=code, error=str(exc))

    def _mark_compact_ok(self) -> None:
        self._mark_state(self._compact_state, ok=True, ts_key="last_compact_ts")

    def _mark_compact_error(self, code: str, exc: BaseException) -> None:
        self._mark_state(self._compact_state, ok=False, code=code, error=str(exc))

    def state(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "path": str(self.path),
            "append": dict(self._append_state),
            "tail": dict(self._tail_state),
            "compact": dict(self._compact_state),
            "degraded": not all(
                bool(bucket.get("ok", True))
                for bucket in (self._append_state, self._tail_state, self._compact_state)
            ),
        }

    def append(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        item: Dict[str, Any] = {
            "ts": int(time.time()),
            "event": str(event),
            **(fields or {}),
        }
        try:
            payload = json.dumps(item, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        except _SAFE_JSON_EXCEPTIONS as exc:
            self._mark_append_error("append_serialize_failed", exc)
            return
        try:
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            try:
                self._write_all(fd, payload)
            finally:
                os.close(fd)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_append_error("append_write_failed", exc)
            return
        self._mark_append_ok()
        self._maybe_compact()

    def tail(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        limit = max(1, min(5_000, int(limit)))
        try:
            with open(self.path, "rb") as f:
                out = self._tail_bytes(f, limit)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_tail_error("tail_open_failed", exc)
            return []
        return out

    def _write_all(self, fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        total = 0
        while total < len(payload):
            written = os.write(fd, view[total:])
            if written <= 0:
                raise OSError("audit_append_short_write")
            total += int(written)

    def _tail_bytes(self, f: BinaryIO, limit: int) -> List[Dict[str, Any]]:
        # Read chunks backwards until we have enough newlines.
        try:
            f.seek(0, os.SEEK_END)
            end = f.tell()
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_tail_error("tail_seek_failed", exc)
            return []

        chunk = 8192
        data = b""
        pos = end
        newlines = 0
        read_failed = False
        while pos > 0 and newlines <= limit:
            read_size = chunk if pos >= chunk else pos
            pos -= read_size
            try:
                f.seek(pos)
                data = f.read(read_size) + data
                newlines = data.count(b"\n")
            except _SAFE_IO_EXCEPTIONS as exc:
                self._mark_tail_error("tail_read_failed", exc)
                read_failed = True
                break
            if len(data) > 5_000_000:
                break

        lines = [ln for ln in data.splitlines() if ln.strip()]
        lines = lines[-limit:]
        out: List[Dict[str, Any]] = []
        parse_errors = 0
        for ln in lines:
            try:
                out.append(json.loads(ln.decode("utf-8")))
            except _SAFE_JSON_EXCEPTIONS:
                parse_errors += 1
                continue
        if parse_errors:
            self._mark_tail_error("tail_parse_partial", f"skipped={parse_errors}")
        elif not read_failed:
            self._mark_tail_ok()
        return out

    def _maybe_compact(self) -> None:
        """Hard-cap file size.

        When exceeding max_bytes, keep the newest ~70% of lines.
        """
        try:
            st = os.stat(self.path)
            if st.st_size <= self.max_bytes:
                return
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_compact_error("compact_stat_failed", exc)
            return

        try:
            with open(self.path, "rb") as f:
                # keep last ~70% of file
                keep = int(self.max_bytes * 0.70)
                f.seek(0, os.SEEK_END)
                end = f.tell()
                start = max(0, end - keep)
                f.seek(start)
                data = f.read()
                # align to next newline so we don't cut mid-line
                i = data.find(b"\n")
                if i >= 0:
                    data = data[i + 1 :]
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_compact_error("compact_read_failed", exc)
            return

        try:
            tmp = self.path + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, self.path)
        except _SAFE_IO_EXCEPTIONS as exc:
            self._mark_compact_error("compact_write_failed", exc)
            return
        self._mark_compact_ok()
