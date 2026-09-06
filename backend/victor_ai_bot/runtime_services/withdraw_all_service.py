from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, List

from ..deploy_mode import is_public_mode
from ..executor_owner import validate_executor_owner_proof
from ..gas import suggest_gas
from ..jsonsafe import to_json_safe
from ..offramp_tx_status import aggregate_submission_proof_reason, submitted_tx_status_payload
from ..pathing import canonical_data_dir
from ..rpc import JsonRpcClient
from ..tx_confirmation import SubmittedTxStatus, assess_submitted_tx
from .withdraw_control_contract import build_withdraw_control_view

_TX_STATUS_RANK = {
    "": 0,
    "receipt_unavailable": 1,
    "sent": 2,
    "pending": 3,
    "mined_reverted": 4,
    "mined_success": 4,
}
_REFRESHABLE_TX_STATUSES = {"pending", "sent", "receipt_unavailable"}
from ..treasury.ledger import LedgerLine
from ..withdraw_builder import build_withdraw_calldata

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


def _invalid_request_payload(
    reason_code: str,
    *,
    field: str | None = None,
    value: Any = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "status": "invalid",
        "reason_code": str(reason_code),
        "reason": str(reason_code),
        "error": str(reason_code),
    }
    detail_payload: Dict[str, Any] = {}
    if field is not None:
        detail_payload["field"] = str(field)
    if value is not None:
        detail_payload["value"] = value
    if details:
        detail_payload.update(dict(details))
    if detail_payload:
        payload["details"] = detail_payload
    return payload


def _coerce_canonical_bool(value: Any) -> tuple[bool, bool]:
    if isinstance(value, bool):
        return True, value
    if isinstance(value, int) and value in {0, 1}:
        return True, bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS:
            return True, True
        if normalized in _FALSE_STRINGS:
            return True, False
    return False, False


def _unexpected_request_fields(
    payload: Dict[str, Any], *, allowed_fields: set[str] | frozenset[str]
) -> list[str]:
    allowed = {str(field) for field in allowed_fields}
    return sorted(str(field) for field in payload.keys() if str(field) not in allowed)


_BALANCE_OF_SELECTOR = "70a08231"
_PREVIEW_TTL_MS = 5 * 60 * 1000
_STATE_REFRESH_TTL_MS = 10 * 1000
_REFRESH_FAILURE_DECAY_INTERVAL_MS = 60 * 1000


class WithdrawAllPersistenceError(RuntimeError):
    def __init__(self, reason_code: str = "state_save_failed"):
        super().__init__(str(reason_code))
        self.reason_code = str(reason_code)


def _tx_status_rank(value: str) -> int:
    return int(_TX_STATUS_RANK.get(str(value or ""), 0))


def _merge_tx_progress(
    existing_item: Dict[str, Any], refreshed: SubmittedTxStatus
) -> Dict[str, Any]:
    merged = dict(existing_item or {})
    current_status = str(merged.get("tx_status") or "")
    refreshed_status = str(refreshed.tx_status or "")
    if _tx_status_rank(refreshed_status) < _tx_status_rank(current_status):
        return merged
    merged.update(submitted_tx_status_payload(refreshed))
    if refreshed.tx_hash:
        merged["tx_hash"] = str(refreshed.tx_hash)
    return merged


def _item_status_changed(previous: Dict[str, Any], current: Dict[str, Any]) -> bool:
    keys = ("tx_status", "tx_proof_reason", "receipt_status", "block_number", "receipt")
    return any(previous.get(key) != current.get(key) for key in keys)


def _first_reverted_item(items: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for item in items:
        if str(item.get("tx_status") or "") == "mined_reverted":
            return dict(item)
    return None


def _submitted_result_status(items: List[Dict[str, Any]]) -> tuple[str, str, Dict[str, Any]]:
    reverted_item = _first_reverted_item(items)
    if reverted_item is not None:
        return (
            "execute_failed",
            "receipt_reverted",
            {
                "ok": False,
                "status": "execute_failed",
                "reason_code": "receipt_reverted",
                "failed_item": reverted_item,
            },
        )
    if items and all(str(item.get("tx_status") or "") == "mined_success" for item in items):
        return (
            "completed",
            "ok",
            {
                "ok": True,
                "status": "completed",
            },
        )
    submission_state = _submission_state(items)
    payload: Dict[str, Any] = {
        "ok": True,
        "status": "submitted",
        "submission_state": submission_state,
    }
    submission_proof_reason = aggregate_submission_proof_reason(items)
    if submission_proof_reason:
        payload["submission_proof_reason"] = submission_proof_reason
    return "submitted", "ok", payload


def _submission_state(items: List[Dict[str, Any]]) -> str:
    states = {
        str(item.get("tx_status") or "") for item in items if str(item.get("tx_status") or "")
    }
    if not states:
        return "sent"
    if len(states) == 1:
        return next(iter(states))
    return "mixed"


def _item_status_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        status = str(item.get("tx_status") or "")
        if not status:
            continue
        counts[status] = int(counts.get(status, 0)) + 1
    return counts


def _lifecycle_summary(
    result: Dict[str, Any], *, fallback_status: str = "", fallback_reason_code: str = ""
) -> Dict[str, Any]:
    payload = dict(result or {})
    items = [dict(item) for item in list(payload.get("items") or []) if isinstance(item, dict)]
    failed_item = (
        dict(payload.get("failed_item") or {})
        if isinstance(payload.get("failed_item"), dict)
        else {}
    )
    counts = _item_status_counts(items)
    failed_tx_hash = str(failed_item.get("tx_hash") or "")
    failed_item_already_counted = bool(
        failed_item
        and failed_tx_hash
        and any(str(item.get("tx_hash") or "") == failed_tx_hash for item in items)
    )
    failed_tx_status = str(failed_item.get("tx_status") or "")
    if failed_tx_status and not failed_item_already_counted:
        counts[failed_tx_status] = int(counts.get(failed_tx_status, 0)) + 1
    confirmed = int(counts.get("mined_success", 0))
    outstanding = (
        int(counts.get("pending", 0))
        + int(counts.get("sent", 0))
        + int(counts.get("receipt_unavailable", 0))
    )
    reverted = int(counts.get("mined_reverted", 0))
    summary_status = str(payload.get("status") or fallback_status or "")
    submission_state = str(payload.get("submission_state") or "")
    summary: Dict[str, Any] = {
        "status": summary_status,
        "reason_code": str(payload.get("reason_code") or fallback_reason_code or ""),
        "submission_state": submission_state,
        "item_count": len(items),
        "attempted_item_count": len(items)
        + (1 if failed_item and not failed_item_already_counted else 0),
        "confirmed_item_count": confirmed,
        "outstanding_item_count": outstanding,
        "reverted_item_count": reverted,
        "failed_item_count": 1 if failed_item else 0,
        "item_status_counts": counts,
    }
    if summary_status == "submitted" and not failed_item:
        submission_proof_reason = str(
            payload.get("submission_proof_reason") or ""
        ) or aggregate_submission_proof_reason(items)
        if submission_proof_reason:
            summary["submission_proof_reason"] = submission_proof_reason
    if failed_tx_hash:
        summary["failed_tx_hash"] = failed_tx_hash
    return summary


def _attach_lifecycle_summary(
    result: Dict[str, Any], *, fallback_status: str = "", fallback_reason_code: str = ""
) -> Dict[str, Any]:
    payload = dict(result or {})
    payload["lifecycle_summary"] = _lifecycle_summary(
        payload,
        fallback_status=fallback_status,
        fallback_reason_code=fallback_reason_code,
    )
    return payload


def _apply_refresh_metadata(
    state: Dict[str, Any],
    *,
    ts_ms: int,
    status: str,
    reason_code: str,
) -> Dict[str, Any]:
    state["last_result_refresh_ts_ms"] = int(ts_ms or 0)
    state["last_result_refresh_status"] = str(status or "idle")
    state["last_result_refresh_reason_code"] = str(reason_code or "")
    return state


def _refresh_metadata_changed(
    state: Dict[str, Any],
    *,
    ts_ms: int,
    status: str,
    reason_code: str,
) -> bool:
    return bool(
        int(state.get("last_result_refresh_ts_ms") or 0) != int(ts_ms or 0)
        or str(state.get("last_result_refresh_status") or "idle") != str(status or "idle")
        or str(state.get("last_result_refresh_reason_code") or "") != str(reason_code or "")
    )


def _apply_refresh_failure(
    state: Dict[str, Any], *, ts_ms: int, reason_code: str
) -> Dict[str, Any]:
    normalized_reason = _normalize_refresh_failure_reason(reason_code)
    previous_reason = _normalize_refresh_failure_reason(
        str(state.get("last_result_refresh_failure_reason_code") or "")
    )
    previous_count = int(state.get("last_result_refresh_failure_count") or 0)
    next_count = (
        previous_count + 1
        if normalized_reason and normalized_reason == previous_reason and previous_count > 0
        else (1 if normalized_reason else 0)
    )
    state["last_result_refresh_failure_ts_ms"] = int(ts_ms or 0)
    state["last_result_refresh_failure_reason_code"] = normalized_reason
    state["last_result_refresh_failure_count"] = int(next_count)
    return state


def _clear_refresh_failure(state: Dict[str, Any]) -> Dict[str, Any]:
    state["last_result_refresh_failure_ts_ms"] = 0
    state["last_result_refresh_failure_reason_code"] = ""
    state["last_result_refresh_failure_count"] = 0
    return state


def _decay_refresh_failure(state: Dict[str, Any], *, now_ms: int) -> tuple[Dict[str, Any], bool]:
    reason = _normalize_refresh_failure_reason(
        str(state.get("last_result_refresh_failure_reason_code") or "")
    )
    count = int(state.get("last_result_refresh_failure_count") or 0)
    ts_ms = int(state.get("last_result_refresh_failure_ts_ms") or 0)
    if not reason or count <= 0 or ts_ms <= 0:
        if count or reason or ts_ms:
            return _clear_refresh_failure(state), True
        return state, False
    elapsed_ms = max(0, int(now_ms or 0) - ts_ms)
    decay_steps = int(elapsed_ms // _REFRESH_FAILURE_DECAY_INTERVAL_MS)
    if decay_steps <= 0:
        return state, False
    applied_steps = min(count, decay_steps)
    remaining = count - applied_steps
    if remaining <= 0:
        return _clear_refresh_failure(state), True
    state["last_result_refresh_failure_count"] = int(remaining)
    state["last_result_refresh_failure_ts_ms"] = int(
        ts_ms + (applied_steps * _REFRESH_FAILURE_DECAY_INTERVAL_MS)
    )
    return state, True


def _clear_refresh_metadata(state: Dict[str, Any]) -> Dict[str, Any]:
    _clear_refresh_failure(state)
    return _apply_refresh_metadata(
        state,
        ts_ms=0,
        status="idle",
        reason_code="never_checked",
    )


def _set_idle_refresh_metadata(state: Dict[str, Any], *, reason_code: str) -> bool:
    changed = _refresh_metadata_changed(state, ts_ms=0, status="idle", reason_code=reason_code)
    failure_changed = bool(
        int(state.get("last_result_refresh_failure_count") or 0) > 0
        or int(state.get("last_result_refresh_failure_ts_ms") or 0) > 0
        or str(state.get("last_result_refresh_failure_reason_code") or "")
    )
    _clear_refresh_failure(state)
    _apply_refresh_metadata(state, ts_ms=0, status="idle", reason_code=reason_code)
    return bool(changed or failure_changed)


def _normalize_refresh_failure_reason(reason_code: str) -> str:
    normalized = str(reason_code or "").strip().lower()
    if not normalized:
        return ""
    if normalized in {"read_rpc_unavailable", "refresh_read_rpc_missing"}:
        return "refresh_read_rpc_missing"
    if normalized in {"receipt_lookup_degraded", "refresh_receipt_lookup_degraded"}:
        return "refresh_receipt_lookup_degraded"
    return normalized


def _refresh_failure_severity(*, count: int, reason_code: str) -> str:
    if count <= 0 or not _normalize_refresh_failure_reason(reason_code):
        return "none"
    if count >= 4:
        return "severe"
    if count >= 2:
        return "repeated"
    return "transient"


def _refresh_metadata_payload(
    state: Dict[str, Any],
    *,
    performed: bool,
    status: str,
    reason_code: str,
    now_ms: int,
) -> Dict[str, Any]:
    checked_ts_ms = int(state.get("last_result_refresh_ts_ms") or 0)
    last_result = dict(state.get("last_result") or {})
    lifecycle = _lifecycle_summary(
        last_result,
        fallback_status=str(state.get("last_status") or ""),
        fallback_reason_code=str(state.get("last_reason_code") or ""),
    )
    outstanding_item_count = int(lifecycle.get("outstanding_item_count") or 0)
    refreshable = bool(
        str(state.get("last_status") or "") == "submitted" and outstanding_item_count > 0
    )
    next_eligible_refresh_ts_ms = (
        int(checked_ts_ms + _STATE_REFRESH_TTL_MS) if refreshable and checked_ts_ms else 0
    )
    failure_ts_ms = int(state.get("last_result_refresh_failure_ts_ms") or 0)
    failure_reason_code = _normalize_refresh_failure_reason(
        str(state.get("last_result_refresh_failure_reason_code") or "")
    )
    failure_count = int(state.get("last_result_refresh_failure_count") or 0)
    failure_next_decay_ts_ms = (
        int(failure_ts_ms + _REFRESH_FAILURE_DECAY_INTERVAL_MS)
        if failure_count > 0 and failure_ts_ms > 0 and failure_reason_code
        else 0
    )
    failure_severity = _refresh_failure_severity(
        count=failure_count, reason_code=failure_reason_code
    )
    return {
        "performed": bool(performed),
        "status": str(status or "skipped"),
        "reason_code": str(reason_code or ""),
        "checked_ts_ms": checked_ts_ms,
        "next_eligible_refresh_ts_ms": next_eligible_refresh_ts_ms,
        "cooldown_ms": int(_STATE_REFRESH_TTL_MS if refreshable else 0),
        "refreshable": bool(refreshable),
        "outstanding_item_count": outstanding_item_count,
        "fresh": bool(refreshable and checked_ts_ms and now_ms < next_eligible_refresh_ts_ms),
        "failure_active": bool(failure_count > 0 and failure_reason_code),
        "failure_reason_code": failure_reason_code,
        "failure_count": failure_count,
        "failure_ts_ms": failure_ts_ms,
        "failure_severity": failure_severity,
        "failure_decay_interval_ms": int(_REFRESH_FAILURE_DECAY_INTERVAL_MS),
        "failure_next_decay_ts_ms": failure_next_decay_ts_ms,
    }


class WithdrawAllService:
    _CONFIG_ALLOWED_FIELDS = frozenset({"destination", "enabled", "activate_destination"})
    _EXECUTE_ALLOWED_FIELDS = frozenset({"preview_id", "confirm_text", "dry_run"})

    def __init__(self, *, data_dir: str, chain: str):
        root = canonical_data_dir(data_dir)
        self._path = os.path.join(root, "controls", f"withdraw_all_{chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
            "enabled": False,
            "approved_destination": "",
            "pending_destination": "",
            "last_preview_id": "",
            "last_preview_digest": "",
            "last_preview_ts_ms": 0,
            "last_status": "idle",
            "last_reason_code": "not_configured",
            "last_result": {},
            "last_executed_preview_id": "",
            "last_executed_result": {},
            "last_result_refresh_ts_ms": 0,
            "last_result_refresh_status": "idle",
            "last_result_refresh_reason_code": "never_checked",
            "last_result_refresh_failure_ts_ms": 0,
            "last_result_refresh_failure_reason_code": "",
            "last_result_refresh_failure_count": 0,
            "updated_ts_ms": 0,
        }

    @classmethod
    def _merge_state(cls, raw: Dict[str, Any] | None) -> Dict[str, Any]:
        state = cls._default_state()
        state.update(dict(raw or {}))
        return state

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._default_state()
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return self._merge_state(json.load(fh) or {})
        except (OSError, TypeError, ValueError):
            state = self._default_state()
            state["last_status"] = "degraded"
            state["last_reason_code"] = "state_load_failed"
            return state

    def _save(self, state: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._merge_state(state)
        payload["updated_ts_ms"] = int(time.time() * 1000)
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
        except (OSError, TypeError, ValueError) as exc:
            raise WithdrawAllPersistenceError("state_save_failed") from exc
        return payload

    def _save_failed_payload(
        self,
        *,
        state: Dict[str, Any] | None = None,
        reason_code: str = "state_save_failed",
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = self._merge_state(state)
        response: Dict[str, Any] = {
            "ok": False,
            "status": "degraded",
            "reason_code": str(reason_code),
            "reason": str(reason_code),
            "error": str(reason_code),
            "enabled": bool(payload.get("enabled", False)),
            "approved_destination": str(payload.get("approved_destination") or ""),
            "pending_destination": str(payload.get("pending_destination") or ""),
            "last_status": str(payload.get("last_status") or "idle"),
            "last_reason_code": str(payload.get("last_reason_code") or ""),
            "last_result": dict(payload.get("last_result") or {}),
            "last_preview_id": str(payload.get("last_preview_id") or ""),
            "last_preview_ts_ms": int(payload.get("last_preview_ts_ms") or 0),
        }
        if extra:
            response.update(dict(extra))
        return to_json_safe(response)

    @staticmethod
    def _allowlisted(cfg: Any, destination: str) -> bool:
        allow = [
            str(x).lower() for x in list(getattr(cfg.execution, "withdraw_allowlist", []) or [])
        ]
        return (
            bool(destination) and destination.lower() in set(allow) if allow else bool(destination)
        )

    @staticmethod
    def _is_address(value: str) -> bool:
        text = str(value or "").strip()
        if len(text) != 42 or not text.startswith("0x"):
            return False
        try:
            bytes.fromhex(text[2:])
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _is_tx_hash(value: str) -> bool:
        text = str(value or "").strip()
        if len(text) != 66 or not text.startswith("0x"):
            return False
        try:
            bytes.fromhex(text[2:])
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _clear_preview_state(state: Dict[str, Any]) -> None:
        state["last_preview_id"] = ""
        state["last_preview_digest"] = ""
        state["last_preview_ts_ms"] = 0
        state["last_executed_preview_id"] = ""
        state["last_executed_result"] = {}

    def _persist_execute_outcome(
        self,
        runtime: Any,
        *,
        state: Dict[str, Any],
        status: str,
        reason_code: str,
        result: Dict[str, Any],
        preview_id: str = "",
        event: str | None = None,
        persisted_state: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        state["last_status"] = str(status or "idle")
        state["last_reason_code"] = str(reason_code or "")
        state["last_result"] = dict(result or {})
        if preview_id:
            state["last_executed_preview_id"] = str(preview_id)
            state["last_executed_result"] = dict(result or {})
        try:
            saved = self._save(state)
        except WithdrawAllPersistenceError as exc:
            return self._save_failed_payload(
                state=persisted_state,
                reason_code=exc.reason_code,
                extra={
                    "attempted_status": str(status or "idle"),
                    "attempted_reason_code": str(reason_code or ""),
                    "attempted_preview_id": str(preview_id or ""),
                    "result_available": bool(result),
                    "result_persisted": False,
                },
            )
        if event:
            self._ledger_event(
                runtime,
                event=str(event),
                metadata={
                    "preview_id": str(preview_id or ""),
                    "reason_code": str(reason_code or ""),
                    "status": str(status or "idle"),
                },
            )
        return saved

    def _capital_truth(self, runtime: Any) -> Dict[str, Any]:
        return runtime.capital_truth_state() if hasattr(runtime, "capital_truth_state") else {}

    async def _refresh_submitted_result_progress(
        self, runtime: Any, state: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        if str(state.get("last_status") or "") != "submitted":
            cleared_state = dict(state)
            if _set_idle_refresh_metadata(cleared_state, reason_code="not_submitted"):
                try:
                    cleared_state = self._save(cleared_state)
                except WithdrawAllPersistenceError:
                    pass
            return cleared_state, _refresh_metadata_payload(
                cleared_state,
                performed=False,
                status="skipped",
                reason_code="not_submitted",
                now_ms=now_ms,
            )
        result = dict(state.get("last_result") or {})
        items = [dict(item) for item in list(result.get("items") or []) if isinstance(item, dict)]
        if not items:
            cleared_state = dict(state)
            if _set_idle_refresh_metadata(cleared_state, reason_code="no_items"):
                try:
                    cleared_state = self._save(cleared_state)
                except WithdrawAllPersistenceError:
                    pass
            return cleared_state, _refresh_metadata_payload(
                cleared_state,
                performed=False,
                status="skipped",
                reason_code="no_items",
                now_ms=now_ms,
            )
        if not any(
            self._is_tx_hash(str(item.get("tx_hash") or ""))
            and str(item.get("tx_status") or "") in _REFRESHABLE_TX_STATUSES
            for item in items
        ):
            cleared_state = dict(state)
            if _set_idle_refresh_metadata(cleared_state, reason_code="no_refreshable_transactions"):
                try:
                    cleared_state = self._save(cleared_state)
                except WithdrawAllPersistenceError:
                    pass
            return cleared_state, _refresh_metadata_payload(
                cleared_state,
                performed=False,
                status="skipped",
                reason_code="no_refreshable_transactions",
                now_ms=now_ms,
            )
        last_refresh_ts_ms = int(state.get("last_result_refresh_ts_ms") or 0)
        if last_refresh_ts_ms and now_ms - last_refresh_ts_ms < _STATE_REFRESH_TTL_MS:
            return state, _refresh_metadata_payload(
                state,
                performed=False,
                status="skipped",
                reason_code="refresh_cooldown_active",
                now_ms=now_ms,
            )
        rpc_read = (
            runtime.rpc_manager.best_read()
            if getattr(runtime, "rpc_manager", None) is not None
            else ""
        )
        if not rpc_read:
            degraded_state = dict(state)
            _apply_refresh_metadata(
                degraded_state,
                ts_ms=now_ms,
                status="skipped",
                reason_code="refresh_read_rpc_missing",
            )
            _apply_refresh_failure(
                degraded_state, ts_ms=now_ms, reason_code="refresh_read_rpc_missing"
            )
            try:
                degraded_state = self._save(degraded_state)
            except WithdrawAllPersistenceError:
                pass
            return degraded_state, _refresh_metadata_payload(
                degraded_state,
                performed=False,
                status="skipped",
                reason_code="refresh_read_rpc_missing",
                now_ms=now_ms,
            )
        cfg = getattr(runtime, "cfg", None)
        send_mode = str(getattr(getattr(cfg, "execution", None), "send_mode", "public") or "public")
        refreshed_items: List[Dict[str, Any]] = []
        changed = False
        refresh_degraded_reason = ""
        async with JsonRpcClient(
            str(rpc_read), timeout_s=10.0, max_concurrency=10, max_batch=20
        ) as rpc:
            for item in items:
                current_item = dict(item)
                tx_hash = str(current_item.get("tx_hash") or "")
                tx_status = str(current_item.get("tx_status") or "")
                next_item = dict(current_item)
                if self._is_tx_hash(tx_hash) and tx_status in _REFRESHABLE_TX_STATUSES:
                    refreshed = await assess_submitted_tx(rpc, tx_hash=tx_hash, send_mode=send_mode)
                    if (
                        str(getattr(refreshed, "proof_reason", "") or "")
                        == "receipt_lookup_degraded"
                    ):
                        refresh_degraded_reason = "refresh_receipt_lookup_degraded"
                        break
                    next_item = _merge_tx_progress(current_item, refreshed)
                refreshed_items.append(next_item)
                changed = changed or _item_status_changed(current_item, next_item)
        if refresh_degraded_reason:
            degraded_state = dict(state)
            _apply_refresh_metadata(
                degraded_state, ts_ms=now_ms, status="skipped", reason_code=refresh_degraded_reason
            )
            _apply_refresh_failure(
                degraded_state, ts_ms=now_ms, reason_code=refresh_degraded_reason
            )
            try:
                degraded_state = self._save(degraded_state)
            except WithdrawAllPersistenceError:
                pass
            return degraded_state, _refresh_metadata_payload(
                degraded_state,
                performed=False,
                status="skipped",
                reason_code=refresh_degraded_reason,
                now_ms=now_ms,
            )
        refreshed_state = dict(state)
        _clear_refresh_failure(refreshed_state)
        refresh_status = "refreshed_no_change"
        if changed:
            result["items"] = refreshed_items
            persisted_status, persisted_reason_code, status_payload = _submitted_result_status(
                refreshed_items
            )
            result.pop("failed_item", None)
            result.pop("submission_state", None)
            result.pop("reason_code", None)
            result.update(status_payload)
            result = _attach_lifecycle_summary(
                result, fallback_status=persisted_status, fallback_reason_code=persisted_reason_code
            )
            refreshed_state["last_status"] = persisted_status
            refreshed_state["last_reason_code"] = persisted_reason_code
            refreshed_state["last_result"] = result
            if str(refreshed_state.get("last_executed_preview_id") or ""):
                refreshed_state["last_executed_result"] = dict(result)
            refresh_status = "refreshed_updated"
        _apply_refresh_metadata(
            refreshed_state, ts_ms=now_ms, status="refreshed", reason_code=refresh_status
        )
        try:
            saved = self._save(refreshed_state)
        except WithdrawAllPersistenceError:
            saved = refreshed_state
        return saved, _refresh_metadata_payload(
            saved, performed=True, status="refreshed", reason_code=refresh_status, now_ms=now_ms
        )

    @staticmethod
    def _lifecycle_event_key(*, event: str, metadata: Dict[str, Any]) -> str:
        payload = dict(metadata or {})
        return "|".join(
            [
                str(event or "withdraw_all_event"),
                str(payload.get("preview_id") or ""),
                str(payload.get("status") or ""),
                str(payload.get("reason_code") or ""),
            ]
        )

    @staticmethod
    def _event_matches(row: Any, *, event: str, event_key: str) -> bool:
        if not isinstance(row, dict):
            return False
        if str(row.get("tx_type") or "") != str(event or ""):
            return False
        metadata = dict(row.get("metadata") or {})
        return str(metadata.get("event_key") or "") == str(event_key or "")

    def _existing_lifecycle_transaction(
        self, runtime: Any, *, event: str, event_key: str
    ) -> Dict[str, Any]:
        if not str(event_key or ""):
            return {}
        chain = str(
            getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or "default"
        )
        repo = getattr(runtime, "_ledger_repo", None)
        if repo is not None and hasattr(repo, "all_transactions"):
            try:
                for row in list(repo.all_transactions(chain=chain) or []):
                    if self._event_matches(row, event=str(event), event_key=str(event_key)):
                        return dict(row)
            except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
                pass
        ledger = getattr(runtime, "_ledger", None)
        if ledger is None or not hasattr(ledger, "transactions_all"):
            return {}
        try:
            for row in list(ledger.transactions_all() or []):
                if self._event_matches(row, event=str(event), event_key=str(event_key)):
                    return dict(row)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            return {}
        return {}

    def _lifecycle_event_exists(self, runtime: Any, *, event: str, event_key: str) -> bool:
        return bool(
            self._existing_lifecycle_transaction(
                runtime, event=str(event), event_key=str(event_key)
            )
        )

    def _ledger_event(self, runtime: Any, *, event: str, metadata: Dict[str, Any]) -> None:
        ledger = getattr(runtime, "_ledger", None)
        repo = getattr(runtime, "_ledger_repo", None)
        chain_cfg = getattr(getattr(runtime, "cfg", None), "chain", None)
        chain = str(getattr(chain_cfg, "name", "default") or "default")
        if ledger is None or not hasattr(ledger, "append_transaction"):
            return
        metadata_payload = dict(metadata or {})
        event_key = self._lifecycle_event_key(event=str(event), metadata=metadata_payload)
        metadata_payload["event_key"] = str(event_key)
        existing_tx = self._existing_lifecycle_transaction(
            runtime, event=str(event), event_key=str(event_key)
        )
        if existing_tx:
            if repo is not None and hasattr(repo, "append_transaction"):
                chain_payload = str(existing_tx.get("chain") or chain)
                repo_has_tx = False
                try:
                    for row in list(repo.all_transactions(chain=chain_payload) or []):
                        if self._event_matches(row, event=str(event), event_key=str(event_key)):
                            repo_has_tx = True
                            break
                except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
                    repo_has_tx = False
                if not repo_has_tx:
                    try:
                        repo.append_transaction(chain=chain_payload, payload=dict(existing_tx))
                    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
                        pass
            return
        try:
            tx = ledger.append_transaction(
                tx_type=str(event),
                chain=chain,
                lines=[
                    LedgerLine(
                        account="control:withdraw_all", asset="USD", amount=0.0, note=str(event)
                    ),
                    LedgerLine(account="equity:offset", asset="USD", amount=0.0, note=str(event)),
                ],
                metadata=metadata_payload,
            )
            if repo is not None and hasattr(repo, "append_transaction"):
                repo.append_transaction(chain=chain, payload=tx.to_dict())
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            return

    async def _token_balances(self, runtime: Any, tokens: List[str]) -> List[Dict[str, Any]]:
        cfg = getattr(runtime, "cfg", None)
        executor = str(getattr(getattr(cfg, "execution", None), "executor_address", "") or "")
        if not executor:
            return []
        read_url = (
            runtime.rpc_manager.best_read()
            if getattr(runtime, "rpc_manager", None) is not None
            else ""
        )
        if not read_url:
            return []
        rows: List[Dict[str, Any]] = []
        async with JsonRpcClient(
            str(read_url), timeout_s=10.0, max_concurrency=10, max_batch=20
        ) as rpc:
            for token in tokens:
                token_addr = str(token or "")
                if not self._is_address(token_addr):
                    continue
                data = (
                    "0x" + _BALANCE_OF_SELECTOR + executor.lower().replace("0x", "").rjust(64, "0")
                )
                try:
                    result = await rpc.eth_call(token_addr, data)
                    raw = result.result if getattr(result, "ok", False) else "0x0"
                    balance = int(str(raw or "0x0"), 16) if isinstance(raw, str) else 0
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    balance = 0
                rows.append({"token": token_addr, "balance": str(max(0, int(balance)))})
        return rows

    def _block_reason(self, runtime: Any, state: Dict[str, Any], truth: Dict[str, Any]) -> str:
        destination = str(state.get("approved_destination") or "")
        if not bool(state.get("enabled", False)):
            return "withdraw_all_disabled"
        if not self._is_address(destination):
            return "approved_destination_missing"
        if not self._allowlisted(getattr(runtime, "cfg", None), destination):
            return "destination_not_allowlisted"
        executor = str(
            getattr(
                getattr(getattr(runtime, "cfg", None), "execution", None), "executor_address", ""
            )
            or ""
        )
        if not executor:
            return "executor_not_configured"
        if not self._is_address(executor):
            return "invalid_executor_address"
        if str(truth.get("status") or "ok") != "ok":
            return "capital_truth_degraded"
        if not bool(((truth.get("withdrawal") or {}).get("available"))):
            return str(
                ((truth.get("withdrawal") or {}).get("reason_code")) or "no_withdrawable_balance"
            )
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is not None and bool(getattr(controls, "paused", False)):
            return "command_center_paused"
        return "ok"

    async def _plan(self, runtime: Any, state: Dict[str, Any]) -> Dict[str, Any]:
        truth = self._capital_truth(runtime)
        withdraw_control = build_withdraw_control_view(runtime, capital_truth=truth)
        reason = self._block_reason(runtime, state, truth)
        destination = str(state.get("approved_destination") or "")
        mode = str(
            getattr(
                getattr(getattr(runtime, "cfg", None), "execution", None), "withdraw_mode", "txdata"
            )
            or "txdata"
        )
        tokens = list(
            getattr(
                getattr(getattr(runtime, "cfg", None), "execution", None), "withdraw_tokens", []
            )
            or []
        )
        token_balances = await self._token_balances(runtime, tokens)
        active_items = [
            {
                "token": str(row.get("token") or ""),
                "amount": str(row.get("balance") or "0"),
                "to": destination,
                "mode": mode,
            }
            for row in token_balances
            if int(str(row.get("balance") or "0"), 10) > 0
        ]
        if reason == "ok" and not active_items:
            reason = "no_token_balances"
        return {
            "reason_code": reason,
            "capital_truth": truth,
            "capital_truth_health": dict(withdraw_control.get("capitalTruthHealth") or {}),
            "withdraw_control": withdraw_control,
            "withdrawable_balance_wei": str(
                ((truth.get("categories") or {}).get("withdrawable_balance_wei")) or "0"
            ),
            "approved_destination": destination,
            "token_balances": token_balances,
            "items": active_items,
            "mode": mode,
        }

    @staticmethod
    def _plan_digest(plan: Dict[str, Any]) -> str:
        canonical = {
            "reason_code": str(plan.get("reason_code") or ""),
            "approved_destination": str(plan.get("approved_destination") or ""),
            "withdrawable_balance_wei": str(plan.get("withdrawable_balance_wei") or "0"),
            "mode": str(plan.get("mode") or ""),
            "items": [
                {
                    "token": str(item.get("token") or ""),
                    "amount": str(item.get("amount") or "0"),
                    "to": str(item.get("to") or ""),
                    "mode": str(item.get("mode") or ""),
                }
                for item in list(plan.get("items") or [])
            ],
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _preview_expired(state: Dict[str, Any]) -> bool:
        ts_ms = int(state.get("last_preview_ts_ms") or 0)
        return not ts_ms or int(time.time() * 1000) - ts_ms > _PREVIEW_TTL_MS

    async def state(self, runtime: Any) -> Dict[str, Any]:
        state = self._load()
        now_ms = int(time.time() * 1000)
        state, decayed_failure = _decay_refresh_failure(dict(state), now_ms=now_ms)
        if decayed_failure:
            try:
                state = self._save(state)
            except WithdrawAllPersistenceError:
                pass
        state, refresh_metadata = await self._refresh_submitted_result_progress(runtime, state)
        plan = await self._plan(runtime, state)
        reason = str(plan.get("reason_code") or "ok")
        destination = str(state.get("approved_destination") or "")
        last_status = str(state.get("last_status") or "idle")
        last_reason_code = str(state.get("last_reason_code") or "")
        persistence_load_failed = (
            last_status == "degraded" and last_reason_code == "state_load_failed"
        )
        status = (
            "degraded"
            if persistence_load_failed
            else ("available" if reason == "ok" else "blocked")
        )
        reason_code = "state_load_failed" if persistence_load_failed else reason
        pending_destination = str(state.get("pending_destination") or "")
        approved_destination_valid = bool(destination and self._is_address(destination))
        pending_destination_valid = bool(
            pending_destination and self._is_address(pending_destination)
        )
        destination_status = (
            "approved"
            if approved_destination_valid
            else ("pending_activation" if pending_destination_valid else "missing")
        )
        destination_reason_code = (
            "ok"
            if approved_destination_valid
            else (
                "pending_destination_activation_required"
                if pending_destination_valid
                else "approved_destination_missing"
            )
        )
        action_available = bool(reason == "ok" and approved_destination_valid)
        return to_json_safe(
            {
                "ok": True,
                "canonical": True,
                "service": "withdraw_all_service",
                "enabled": bool(state.get("enabled", False)),
                "approved_destination": destination,
                "pending_destination": pending_destination,
                "destination_status": destination_status,
                "destination_reason_code": destination_reason_code,
                "destination_activation_required": bool(destination_status == "pending_activation"),
                "destination_ready": approved_destination_valid,
                "status": status,
                "reason_code": reason_code,
                "control_reason_code": reason,
                "action_available": action_available,
                "action_reason_code": reason if not action_available else "ok",
                "preview_required": True,
                "execute_confirmation_text": "WITHDRAW EVERYTHING",
                "capital_truth": plan.get("capital_truth") or {},
                "capitalTruthHealth": dict(plan.get("capital_truth_health") or {}),
                "withdrawControl": dict(plan.get("withdraw_control") or {}),
                "withdrawable_balance_wei": str(plan.get("withdrawable_balance_wei") or "0"),
                "last_status": last_status,
                "last_reason_code": last_reason_code,
                "last_result": dict(state.get("last_result") or {}),
                "last_result_summary": _lifecycle_summary(
                    dict(state.get("last_result") or {}),
                    fallback_status=last_status,
                    fallback_reason_code=last_reason_code,
                ),
                "last_result_refresh": refresh_metadata,
                "last_result_refresh_ts_ms": int(state.get("last_result_refresh_ts_ms") or 0),
                "last_result_refresh_status": str(
                    state.get("last_result_refresh_status") or "idle"
                ),
                "last_result_refresh_reason_code": str(
                    state.get("last_result_refresh_reason_code") or "never_checked"
                ),
                "last_result_refresh_failure": {
                    "active": bool(
                        int(state.get("last_result_refresh_failure_count") or 0) > 0
                        and _normalize_refresh_failure_reason(
                            str(state.get("last_result_refresh_failure_reason_code") or "")
                        )
                    ),
                    "count": int(state.get("last_result_refresh_failure_count") or 0),
                    "reason_code": _normalize_refresh_failure_reason(
                        str(state.get("last_result_refresh_failure_reason_code") or "")
                    ),
                    "ts_ms": int(state.get("last_result_refresh_failure_ts_ms") or 0),
                    "severity": _refresh_failure_severity(
                        count=int(state.get("last_result_refresh_failure_count") or 0),
                        reason_code=str(state.get("last_result_refresh_failure_reason_code") or ""),
                    ),
                    "decay_interval_ms": int(_REFRESH_FAILURE_DECAY_INTERVAL_MS),
                    "next_decay_ts_ms": (
                        int(
                            int(state.get("last_result_refresh_failure_ts_ms") or 0)
                            + _REFRESH_FAILURE_DECAY_INTERVAL_MS
                        )
                        if int(state.get("last_result_refresh_failure_count") or 0) > 0
                        and _normalize_refresh_failure_reason(
                            str(state.get("last_result_refresh_failure_reason_code") or "")
                        )
                        else 0
                    ),
                },
                "last_result_refresh_failure_ts_ms": int(
                    state.get("last_result_refresh_failure_ts_ms") or 0
                ),
                "last_result_refresh_failure_reason_code": _normalize_refresh_failure_reason(
                    str(state.get("last_result_refresh_failure_reason_code") or "")
                ),
                "last_result_refresh_failure_count": int(
                    state.get("last_result_refresh_failure_count") or 0
                ),
                "last_preview_id": str(state.get("last_preview_id") or ""),
                "last_preview_ts_ms": int(state.get("last_preview_ts_ms") or 0),
                "preview_expired": (
                    self._preview_expired(state) if state.get("last_preview_id") else False
                ),
                "items": list(plan.get("token_balances") or []),
                "token_balances": list(plan.get("token_balances") or []),
                "mode": str(
                    getattr(
                        getattr(getattr(runtime, "cfg", None), "execution", None),
                        "withdraw_mode",
                        "",
                    )
                    or ""
                ),
                "post_withdraw_posture": {
                    "target_deployable_capital_wei": "0",
                    "platform_posture": (
                        "observation_only_after_wipe"
                        if action_available or last_status in {"prepared", "submitted", "completed"}
                        else "unchanged"
                    ),
                    "preserves_audit_history": True,
                    "command_center_pause_expected": True,
                },
                "updated_ts_ms": now_ms,
            }
        )

    def configure(self, runtime: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(payload or {})
        unexpected = _unexpected_request_fields(payload, allowed_fields=self._CONFIG_ALLOWED_FIELDS)
        if unexpected:
            return _invalid_request_payload(
                "unknown_request_fields", details={"fields": unexpected}
            )

        state = self._load()
        persisted_state = dict(state)
        destination_present = "destination" in payload
        enabled_present = "enabled" in payload
        activate_present = "activate_destination" in payload

        if destination_present:
            destination = str(payload.get("destination") or "").strip()
            if not destination or not self._is_address(destination):
                return _invalid_request_payload(
                    "invalid_destination", field="destination", value=payload.get("destination")
                )
        else:
            destination = ""

        if activate_present:
            activate_ok, activate = _coerce_canonical_bool(payload.get("activate_destination"))
            if not activate_ok:
                return _invalid_request_payload(
                    "invalid_boolean_value",
                    field="activate_destination",
                    value=payload.get("activate_destination"),
                )
        else:
            activate = False

        if enabled_present:
            enabled_ok, enabled = _coerce_canonical_bool(payload.get("enabled"))
            if not enabled_ok:
                return _invalid_request_payload(
                    "invalid_boolean_value", field="enabled", value=payload.get("enabled")
                )
        else:
            enabled = bool(state.get("enabled", False))

        if activate and not destination_present:
            return _invalid_request_payload("missing_destination", field="destination")

        if (
            destination_present
            and activate
            and not self._allowlisted(getattr(runtime, "cfg", None), destination)
        ):
            return {
                "ok": False,
                "status": "blocked",
                "reason_code": "destination_not_allowlisted",
                "reason": "destination_not_allowlisted",
                "error": "destination_not_allowlisted",
            }

        config_changed = False
        if destination_present:
            if activate:
                if destination != str(state.get("approved_destination") or ""):
                    config_changed = True
                state["approved_destination"] = destination
                state["pending_destination"] = ""
            else:
                if destination != str(state.get("pending_destination") or ""):
                    config_changed = True
                state["pending_destination"] = destination

        if enabled_present:
            config_changed = config_changed or enabled != bool(state.get("enabled", False))
            state["enabled"] = enabled

        if not config_changed:
            return {"ok": True, **state}

        self._clear_preview_state(state)
        try:
            saved = self._save(state)
        except WithdrawAllPersistenceError as exc:
            return self._save_failed_payload(state=persisted_state, reason_code=exc.reason_code)
        self._ledger_event(
            runtime,
            event="withdraw_all_configured",
            metadata={
                "enabled": saved.get("enabled"),
                "approved_destination": saved.get("approved_destination"),
            },
        )
        return {"ok": True, **saved}

    async def preview(self, runtime: Any) -> Dict[str, Any]:
        state = self._load()
        persisted_state = dict(state)
        plan = await self._plan(runtime, state)
        preview_id = f"wipe_{uuid.uuid4().hex[:16]}"
        preview_digest = self._plan_digest(plan)
        state["last_preview_id"] = preview_id
        state["last_preview_digest"] = preview_digest
        state["last_preview_ts_ms"] = int(time.time() * 1000)
        state["last_executed_preview_id"] = ""
        state["last_executed_result"] = {}
        reason_code = str(plan.get("reason_code") or "ok")
        state["last_status"] = "preview_ready" if reason_code == "ok" else "preview_blocked"
        state["last_reason_code"] = reason_code
        try:
            saved = self._save(state)
        except WithdrawAllPersistenceError as exc:
            return self._save_failed_payload(
                state=persisted_state,
                reason_code=exc.reason_code,
                extra={
                    "preview_id": "",
                    "preview_ts_ms": 0,
                    "approved_destination": str(plan.get("approved_destination") or ""),
                    "withdrawable_balance_wei": str(plan.get("withdrawable_balance_wei") or "0"),
                    "items": list(plan.get("items") or []),
                },
            )
        self._ledger_event(
            runtime,
            event="withdraw_all_previewed",
            metadata={"preview_id": preview_id, "reason_code": saved.get("last_reason_code")},
        )
        withdraw_control = dict(plan.get("withdraw_control") or {})
        return to_json_safe(
            {
                "ok": reason_code == "ok",
                "preview_id": preview_id,
                "preview_ts_ms": int(saved.get("last_preview_ts_ms") or 0),
                "reason_code": reason_code,
                "capital_truth_reason_code": str(withdraw_control.get("reasonCode") or ""),
                "capital_truth_reason_codes": list(withdraw_control.get("reasonCodes") or []),
                "capitalTruthHealth": dict(plan.get("capital_truth_health") or {}),
                "withdrawControl": withdraw_control,
                "approved_destination": str(saved.get("approved_destination") or ""),
                "withdrawable_balance_wei": str(plan.get("withdrawable_balance_wei") or "0"),
                "items": list(plan.get("items") or []),
            }
        )

    async def execute(self, runtime: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_payload = dict(payload or {})
        unexpected = _unexpected_request_fields(
            raw_payload, allowed_fields=self._EXECUTE_ALLOWED_FIELDS
        )
        if unexpected:
            return _invalid_request_payload(
                "unknown_request_fields", details={"fields": unexpected}
            )

        if "dry_run" in raw_payload:
            dry_run_ok, dry_run = _coerce_canonical_bool(raw_payload.get("dry_run"))
            if not dry_run_ok:
                return _invalid_request_payload(
                    "invalid_boolean_value",
                    field="dry_run",
                    value=raw_payload.get("dry_run"),
                )
        else:
            dry_run = False

        state = self._load()
        persisted_state = dict(state)
        preview_id = str(raw_payload.get("preview_id") or "")
        confirm_text = str(raw_payload.get("confirm_text") or "")
        if not preview_id or preview_id != str(state.get("last_preview_id") or ""):
            result = {"ok": False, "reason_code": "preview_id_mismatch"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="preview_id_mismatch",
                result=result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {"ok": False, "reason_code": "preview_id_mismatch", **saved, "result": result}
        if confirm_text != "WITHDRAW EVERYTHING":
            result = {"ok": False, "reason_code": "confirmation_text_mismatch"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="confirmation_text_mismatch",
                result=result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "confirmation_text_mismatch",
                **saved,
                "result": result,
            }
        if self._preview_expired(state):
            result = {"ok": False, "reason_code": "preview_expired"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="preview_expired",
                result=result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {"ok": False, "reason_code": "preview_expired", **saved, "result": result}
        if (
            preview_id == str(state.get("last_executed_preview_id") or "")
            and isinstance(state.get("last_executed_result"), dict)
            and state.get("last_executed_result")
        ):
            replayed_result = dict(state.get("last_executed_result") or {})
            replay_ok = bool(replayed_result.get("ok", False))
            response = {"ok": replay_ok, **state, "result": replayed_result, "replayed": True}
            replay_reason = str(replayed_result.get("reason_code") or "")
            if replay_reason:
                response["reason_code"] = replay_reason
            return response

        plan = await self._plan(runtime, state)
        current_reason = str(plan.get("reason_code") or "ok")
        current_digest = self._plan_digest(plan)
        withdraw_control = dict(plan.get("withdraw_control") or {})
        capital_truth_health = dict(plan.get("capital_truth_health") or {})
        if current_digest != str(state.get("last_preview_digest") or ""):
            result = {
                "ok": False,
                "reason_code": "preview_stale",
                "current_reason_code": current_reason,
                "current_capital_truth_reason_code": str(withdraw_control.get("reasonCode") or ""),
                "current_capital_truth_reason_codes": list(
                    withdraw_control.get("reasonCodes") or []
                ),
                "capitalTruthHealth": capital_truth_health,
                "withdrawControl": withdraw_control,
            }
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="preview_stale",
                result=result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {"ok": False, "reason_code": "preview_stale", **saved, "result": result}
        if current_reason != "ok":
            result = {
                "ok": False,
                "reason_code": current_reason,
                "capital_truth_reason_code": str(withdraw_control.get("reasonCode") or ""),
                "capital_truth_reason_codes": list(withdraw_control.get("reasonCodes") or []),
                "capitalTruthHealth": capital_truth_health,
                "withdrawControl": withdraw_control,
            }
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code=current_reason,
                result=result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {"ok": False, "reason_code": current_reason, **saved, "result": result}

        items = list(plan.get("items") or [])
        mode = str(plan.get("mode") or "txdata")
        state["last_status"] = "prepared" if dry_run or mode != "backend" else "executing"
        state["last_reason_code"] = "ok"
        execute_result: Dict[str, Any] = {
            "ok": True,
            "status": state["last_status"],
            "preview_id": preview_id,
            "approved_destination": str(state.get("approved_destination") or ""),
            "mode": mode,
            "items": [],
        }
        if dry_run or mode != "backend":
            for item in items:
                execute_result["items"].append(
                    {
                        **dict(item),
                        "calldata": build_withdraw_calldata(
                            token=str(item.get("token") or ""),
                            to=str(state.get("approved_destination") or ""),
                            amount=int(str(item.get("amount") or "0"), 10),
                        ),
                    }
                )
            execute_result = _attach_lifecycle_summary(
                execute_result, fallback_status=state["last_status"], fallback_reason_code="ok"
            )
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status=state["last_status"],
                reason_code="ok",
                result=execute_result,
                preview_id=preview_id,
                event="withdraw_all_prepared",
                persisted_state=persisted_state,
            )
            return {"ok": True, **saved, "result": execute_result}

        if is_public_mode():
            execute_result = {
                "ok": False,
                "reason_code": "withdraw_execute_disabled_in_public_mode",
            }
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="withdraw_execute_disabled_in_public_mode",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "withdraw_execute_disabled_in_public_mode",
                **saved,
                "result": execute_result,
            }

        cfg = getattr(runtime, "cfg", None)
        key_env = str(
            getattr(getattr(cfg, "execution", None), "private_key_env", "VICTOR_PRIVATE_KEY")
            or "VICTOR_PRIVATE_KEY"
        )
        key_hex = os.environ.get(key_env, "").strip()
        if not key_hex:
            execute_result = {
                "ok": False,
                "reason_code": "missing_private_key_env",
                "private_key_env": key_env,
            }
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="missing_private_key_env",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "missing_private_key_env",
                **saved,
                "result": execute_result,
            }
        from eth_account import Account

        try:
            acct = Account.from_key(key_hex)
        except (TypeError, ValueError):
            execute_result = {
                "ok": False,
                "reason_code": "invalid_private_key_env",
                "private_key_env": key_env,
            }
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="invalid_private_key_env",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "invalid_private_key_env",
                **saved,
                "result": execute_result,
            }
        rpc_plan_read = (
            runtime.rpc_manager.best_read()
            if getattr(runtime, "rpc_manager", None) is not None
            else ""
        )
        rpc_plan_send = (
            runtime.rpc_manager.best_private() or runtime.rpc_manager.best_send()
            if getattr(runtime, "rpc_manager", None) is not None
            else ""
        )
        if not rpc_plan_read or not rpc_plan_send:
            execute_result = {"ok": False, "reason_code": "no_rpc_endpoints"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="no_rpc_endpoints",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "no_rpc_endpoints",
                **saved,
                "result": execute_result,
            }
        executor = str(getattr(getattr(cfg, "execution", None), "executor_address", "") or "")
        if not executor:
            execute_result = {"ok": False, "reason_code": "executor_not_configured"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="executor_not_configured",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "executor_not_configured",
                **saved,
                "result": execute_result,
            }
        if not self._is_address(executor):
            execute_result = {"ok": False, "reason_code": "invalid_executor_address"}
            saved = self._persist_execute_outcome(
                runtime,
                state=state,
                status="execute_blocked",
                reason_code="invalid_executor_address",
                result=execute_result,
                event="withdraw_all_execute_blocked",
                persisted_state=persisted_state,
            )
            return {
                "ok": False,
                "reason_code": "invalid_executor_address",
                **saved,
                "result": execute_result,
            }
        nonce_offset = 0
        async with (
            JsonRpcClient(
                str(rpc_plan_read), timeout_s=10.0, max_concurrency=10, max_batch=20
            ) as rpc_r,
            JsonRpcClient(
                str(rpc_plan_send), timeout_s=10.0, max_concurrency=5, max_batch=10
            ) as rpc_s,
        ):
            owner_reason, executor_owner = await validate_executor_owner_proof(
                rpc_r, executor_address=executor, signer_address=acct.address
            )
            if owner_reason is not None:
                failure = {
                    "ok": False,
                    "reason_code": owner_reason,
                    "private_key_env": key_env,
                    "signer_address": acct.address,
                    "executor_owner": executor_owner or "",
                }
                saved = self._persist_execute_outcome(
                    runtime,
                    state=state,
                    status="execute_blocked",
                    reason_code=owner_reason,
                    execute_result=failure,
                    event="withdraw_all_execute_blocked",
                    persisted_state=persisted_state,
                )
                return {"ok": False, "reason_code": owner_reason, **saved, "result": failure}

            max_fee, prio = await suggest_gas(
                rpc_r,
                mode=str(getattr(getattr(cfg, "execution", None), "gas_mode", "standard")),
                presets=getattr(getattr(cfg, "execution", None), "gas_presets", None),
            )
            base_nonce = await rpc_r.get_nonce(acct.address)
            for item in items:
                amount = int(str(item.get("amount") or "0"), 10)
                calldata = build_withdraw_calldata(
                    token=str(item.get("token") or ""),
                    to=str(state.get("approved_destination") or ""),
                    amount=amount,
                )
                gas_limit = int(
                    getattr(getattr(cfg, "execution", None), "gas_limit", 200_000) or 200_000
                )
                try:
                    est = await rpc_r.estimate_gas(
                        {"to": executor, "from": acct.address, "data": calldata, "value": hex(0)}
                    )
                    if est is not None:
                        gas_limit = max(gas_limit, int(est) + 20_000)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
                tx = {
                    "chainId": int(getattr(getattr(cfg, "chain", None), "chain_id", 0) or 0),
                    "to": executor,
                    "nonce": int(base_nonce) + nonce_offset,
                    "data": calldata,
                    "value": 0,
                    "gas": int(gas_limit),
                    "maxFeePerGas": int(max_fee),
                    "maxPriorityFeePerGas": int(prio),
                    "type": 2,
                }
                signed = Account.sign_transaction(tx, key_hex)
                raw_bytes = getattr(signed, "rawTransaction", None) or getattr(
                    signed, "raw_transaction", None
                )
                raw = raw_bytes.hex() if raw_bytes is not None else ""
                raw = raw if raw.startswith("0x") else ("0x" + raw)
                send_mode = str(
                    getattr(getattr(cfg, "execution", None), "send_mode", "public") or "public"
                )
                if send_mode == "private":
                    current_block = await rpc_r.block_number() or 0
                    sent = await rpc_s.send_private_tx(raw, max_block_number=current_block + 2)
                else:
                    sent = await rpc_s.send_raw_tx(raw)
                txh = getattr(sent, "result", None) if getattr(sent, "ok", False) else ""
                if isinstance(txh, dict):
                    txh = txh.get("txHash") or txh.get("hash") or txh.get("result")
                if not isinstance(txh, str) or not self._is_tx_hash(txh):
                    failure = {
                        "ok": False,
                        "reason_code": "send_failed",
                        "failed_item": dict(item),
                        "items": list(execute_result.get("items") or []),
                    }
                    failure = _attach_lifecycle_summary(
                        failure,
                        fallback_status="execute_failed",
                        fallback_reason_code="send_failed",
                    )
                    _clear_refresh_metadata(state)
                    saved = self._persist_execute_outcome(
                        runtime,
                        state=state,
                        status="execute_failed",
                        reason_code="send_failed",
                        execute_result=failure,
                        preview_id=preview_id,
                        event="withdraw_all_execute_failed",
                        persisted_state=persisted_state,
                    )
                    return {"ok": False, "reason_code": "send_failed", **saved, "result": failure}
                tx_result = await assess_submitted_tx(
                    rpc_r,
                    tx_hash=str(txh or ""),
                    send_mode=send_mode,
                )
                if tx_result.tx_status == "mined_reverted":
                    failure = {
                        "ok": False,
                        "reason_code": "receipt_reverted",
                        "failed_item": {
                            **dict(item),
                            "tx_hash": str(txh or ""),
                            **submitted_tx_status_payload(tx_result),
                        },
                        "items": list(execute_result.get("items") or []),
                    }
                    failure = _attach_lifecycle_summary(
                        failure,
                        fallback_status="execute_failed",
                        fallback_reason_code="receipt_reverted",
                    )
                    _clear_refresh_failure(state)
                    _apply_refresh_metadata(
                        state,
                        ts_ms=int(time.time() * 1000),
                        status="execution_assessed",
                        reason_code="ok",
                    )
                    saved = self._persist_execute_outcome(
                        runtime,
                        state=state,
                        status="execute_failed",
                        reason_code="receipt_reverted",
                        execute_result=failure,
                        preview_id=preview_id,
                        event="withdraw_all_execute_failed",
                        persisted_state=persisted_state,
                    )
                    return {
                        "ok": False,
                        "reason_code": "receipt_reverted",
                        **saved,
                        "result": failure,
                    }
                execute_result["items"].append(
                    {
                        **dict(item),
                        "tx_hash": str(txh or ""),
                        **submitted_tx_status_payload(tx_result),
                    }
                )
                nonce_offset += 1
        submission_state = _submission_state(list(execute_result.get("items") or []))
        if submission_state == "mined_success":
            execute_result["status"] = "completed"
            state["last_status"] = "completed"
            persist_status = "completed"
            persist_event = "withdraw_all_completed"
        else:
            execute_result["status"] = "submitted"
            execute_result["submission_state"] = submission_state
            submission_proof_reason = aggregate_submission_proof_reason(
                list(execute_result.get("items") or [])
            )
            if submission_proof_reason:
                execute_result["submission_proof_reason"] = submission_proof_reason
            state["last_status"] = "submitted"
            persist_status = "submitted"
            persist_event = "withdraw_all_submitted"
        execute_result = _attach_lifecycle_summary(
            execute_result, fallback_status=persist_status, fallback_reason_code="ok"
        )
        _clear_refresh_failure(state)
        _apply_refresh_metadata(
            state, ts_ms=int(time.time() * 1000), status="execution_assessed", reason_code="ok"
        )
        saved = self._persist_execute_outcome(
            runtime,
            state=state,
            status=persist_status,
            reason_code="ok",
            result=execute_result,
            preview_id=preview_id,
            event=persist_event,
            persisted_state=persisted_state,
        )
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is not None:
            try:
                controls.paused = True
                controls.allocations_frozen = True
                controls.evolution_enabled = False
            except (AttributeError, TypeError, ValueError):
                pass
        rollout = getattr(runtime, "_launch_rollout", None)
        if rollout is not None:
            for family in list(
                getattr(getattr(rollout, "profile", None), "rollout_order", []) or []
            ):
                if str(family) != "flash_arb":
                    try:
                        rollout.pause_family(str(family), actor="withdraw_all")
                    except (AttributeError, TypeError, ValueError):
                        continue
        return {"ok": True, **saved, "result": result}
