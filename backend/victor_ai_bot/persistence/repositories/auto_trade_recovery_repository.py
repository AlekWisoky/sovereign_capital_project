from __future__ import annotations

import json
from typing import Any, Dict, List

from ..db import PersistenceDB


class AutoTradeRecoveryRepository:
    def __init__(self, db: PersistenceDB, *, chain: str):
        self.db = db
        self.chain = str(chain)

    @staticmethod
    def _int_like(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _string_list(values: Any) -> List[str]:
        return [str(x) for x in list(values or []) if str(x)]

    @staticmethod
    def _pick_string(*values: Any, default: str = "") -> str:
        for value in values:
            s = str(value or "").strip()
            if s:
                return s
        return str(default)

    def _pick_strings(self, *values: Any) -> List[str]:
        for value in values:
            items = self._string_list(value)
            if items:
                return items
        return []

    @classmethod
    def _pick_int(cls, *values: Any, default: int = 0) -> int:
        for value in values:
            iv = cls._int_like(value)
            if iv > 0:
                return iv
        return int(default)

    def load(self, component: str = "auto_trade_admission") -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM auto_trade_recovery_state WHERE chain=? AND component=?",
                (self.chain, str(component)),
            ).fetchone()
        if row is None:
            return {}
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def recent_events(
        self, component: str = "auto_trade_admission", *, limit: int = 10
    ) -> List[Dict[str, Any]]:
        event_limit = max(1, min(100, self._int_like(limit) or 10))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT ts_ms, event_type, stage, reason_code, blocker_component, next_action, payload_json
                FROM auto_trade_recovery_events
                WHERE chain=? AND component=?
                ORDER BY ts_ms DESC, id DESC
                LIMIT ?
                """,
                (self.chain, str(component), event_limit),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            payload = dict(payload) if isinstance(payload, dict) else {}
            event_type = str(row["event_type"] or "")
            history_status = (
                "recovered"
                if event_type == "recovered"
                else (
                    "blocked"
                    if event_type in {"blocked", "blocked_update"}
                    else str(payload.get("history_status") or "steady")
                )
            )
            if event_type == "recovered":
                event_blocker_component = str(
                    row["blocker_component"] or payload.get("blocker_component") or ""
                )
                event_next_action = str(row["next_action"] or payload.get("next_action") or "")
            else:
                event_blocker_component = str(
                    row["blocker_component"]
                    or payload.get("blocker_component")
                    or payload.get("history_component")
                    or ""
                )
                event_next_action = str(
                    row["next_action"]
                    or payload.get("next_action")
                    or payload.get("history_next_action")
                    or payload.get("component_reliability_next_action")
                    or payload.get("reliability_next_action")
                    or ""
                )
            event_stage = str(row["stage"] or payload.get("stage") or "")
            if not event_stage:
                event_stage = "ok"
            event_reason_code = str(row["reason_code"] or payload.get("reason_code") or "")
            event_reason_codes = self._string_list(payload.get("reason_codes") or [])
            if not event_reason_code:
                event_reason_code = "ok"
            if event_type == "recovered":
                event_degraded = False
            elif event_type in {"blocked", "blocked_update"}:
                event_degraded = True
            else:
                event_degraded = bool(payload.get("is_degraded", payload.get("degraded", False)))
            event_degraded_since_ts_ms = self._int_like(
                payload.get("history_degraded_since_ts_ms")
                if history_status == "recovered"
                else payload.get("degraded_since_ts_ms")
            )
            if history_status == "blocked" and event_degraded_since_ts_ms <= 0:
                event_degraded_since_ts_ms = self._int_like(row["ts_ms"])
            event_recovered_at_ts_ms = self._int_like(
                payload.get("history_recovered_at_ts_ms")
                if history_status == "recovered"
                else payload.get("last_recovered_ts_ms") or payload.get("recovered_at_ts_ms")
            )
            if history_status == "recovered" and event_recovered_at_ts_ms <= 0:
                event_recovered_at_ts_ms = self._pick_int(
                    payload.get("last_recovered_ts_ms"), row["ts_ms"]
                )
            event = {
                "ts_ms": self._int_like(row["ts_ms"]),
                "event_type": event_type,
                "stage": event_stage,
                "reason_code": event_reason_code,
                "reason_codes": event_reason_codes,
                "blocker_component": event_blocker_component,
                "next_action": event_next_action,
                "degraded": event_degraded,
                "history_status": history_status,
                "degraded_count": self._int_like(payload.get("degraded_count")),
                "degraded_since_ts_ms": event_degraded_since_ts_ms,
                "recovered_at_ts_ms": event_recovered_at_ts_ms,
                "last_healthy_ts_ms": self._int_like(payload.get("last_healthy_ts_ms")),
                "updated_ts_ms": self._int_like(payload.get("updated_ts_ms")),
                "history_component": str(
                    payload.get("history_component") or payload.get("blocker_component") or ""
                ),
                "history_stage": str(payload.get("history_stage") or payload.get("stage") or "ok"),
                "history_reason_code": str(payload.get("history_reason_code") or ""),
                "history_reason_codes": self._string_list(
                    payload.get("history_reason_codes") or []
                ),
                "history_next_action": str(payload.get("history_next_action") or ""),
                "reliability_class": str(payload.get("reliability_class") or "stable"),
                "reliability_reason_code": str(payload.get("reliability_reason_code") or "ok"),
                "reliability_reason_codes": self._string_list(
                    payload.get("reliability_reason_codes") or []
                ),
                "reliability_next_action": str(
                    payload.get("reliability_next_action") or payload.get("next_action") or ""
                ),
                "component_reliability_class": str(
                    payload.get("component_reliability_class")
                    or payload.get("reliability_class")
                    or "stable"
                ),
                "component_reliability_reason_code": str(
                    payload.get("component_reliability_reason_code")
                    or payload.get("reliability_reason_code")
                    or "ok"
                ),
                "component_reliability_reason_codes": self._string_list(
                    payload.get("component_reliability_reason_codes")
                    or payload.get("reliability_reason_codes")
                    or []
                ),
                "component_reliability_next_action": str(
                    payload.get("component_reliability_next_action")
                    or payload.get("reliability_next_action")
                    or payload.get("next_action")
                    or ""
                ),
                "component_recovered_fragile": bool(
                    payload.get(
                        "component_recovered_fragile",
                        str(payload.get("history_status") or "") == "recovered"
                        and str(
                            payload.get("component_reliability_class")
                            or payload.get("reliability_class")
                            or ""
                        )
                        == "fragile",
                    )
                ),
                "family_hardening_reason_codes": self._string_list(
                    payload.get("family_hardening_reason_codes") or []
                ),
                "receipt_outcome_truth_reason_codes": self._string_list(
                    payload.get("receipt_outcome_truth_reason_codes") or []
                ),
            }
            if (
                event["history_status"] == "recovered"
                and event["history_component"]
                and event["component_reliability_class"] == "fragile"
            ):
                event["component_recovered_fragile"] = True
            out.append(event)
        return out

    def _append_event(
        self,
        *,
        component: str,
        ts_ms: int,
        event_type: str,
        stage: str,
        reason_code: str,
        blocker_component: str,
        next_action: str,
        payload: Dict[str, Any],
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO auto_trade_recovery_events(
                    chain, component, ts_ms, event_type, stage, reason_code,
                    blocker_component, next_action, payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    self.chain,
                    str(component),
                    int(ts_ms or 0),
                    str(event_type or "state_changed"),
                    str(stage or "ok"),
                    str(reason_code or "ok"),
                    str(blocker_component or ""),
                    str(next_action or ""),
                    json.dumps(payload, sort_keys=True),
                ),
            )

    def observe(
        self,
        *,
        component: str = "auto_trade_admission",
        degraded: bool,
        ts_ms: int,
        reason_code: str = "",
        stage: str = "",
        blocker_component: str = "",
        next_action: str = "",
        reason_codes: list[str] | None = None,
        payload_extras: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        component_name = str(component or "auto_trade_admission")
        now_ms = self._int_like(ts_ms)
        current = self.load(component_name)
        was_degraded = bool(current.get("is_degraded", False))
        degraded_since_ts_ms = self._int_like(current.get("degraded_since_ts_ms"))
        last_recovered_ts_ms = self._int_like(current.get("last_recovered_ts_ms"))
        degraded_count = self._int_like(current.get("degraded_count"))
        last_healthy_ts_ms = self._int_like(current.get("last_healthy_ts_ms"))
        if degraded:
            normalized_reason_codes = self._string_list(
                reason_codes or current.get("last_reason_codes") or []
            )
            normalized_reason_code = str(
                reason_code or current.get("last_reason_code") or "degraded"
            )
            normalized_stage = str(stage or current.get("last_stage") or "ok")
            normalized_component = str(
                blocker_component or current.get("last_blocker_component") or ""
            )
            normalized_next_action = str(next_action or current.get("last_next_action") or "")
        else:
            normalized_reason_codes = []
            normalized_reason_code = "ok"
            normalized_stage = "ok"
            normalized_component = ""
            normalized_next_action = ""
        if normalized_reason_code != "ok" and normalized_reason_code not in normalized_reason_codes:
            normalized_reason_codes = [normalized_reason_code, *normalized_reason_codes]
        elif normalized_reason_code == "ok" and not degraded and reason_codes is None:
            normalized_reason_codes = []
        extra_payload = dict(payload_extras or {}) if isinstance(payload_extras, dict) else {}
        history_component_values = (
            (
                current.get("history_component"),
                extra_payload.get("history_component"),
                normalized_component,
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("history_component"),
                current.get("history_component"),
                normalized_component,
            )
        )
        effective_history_component = self._pick_string(*history_component_values)
        history_stage_values = (
            (
                current.get("history_stage"),
                extra_payload.get("history_stage"),
                normalized_stage,
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("history_stage"),
                current.get("history_stage"),
                normalized_stage,
            )
        )
        effective_history_stage = self._pick_string(*history_stage_values, default="ok")
        history_reason_code_values = (
            (
                current.get("last_reason_code"),
                extra_payload.get("history_reason_code"),
                normalized_reason_code,
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("history_reason_code"),
                current.get("last_reason_code"),
                normalized_reason_code,
            )
        )
        effective_history_reason_code = self._pick_string(
            *history_reason_code_values,
            default=("degraded" if degraded else "ok"),
        )
        history_reason_codes_values = (
            (
                current.get("last_reason_codes"),
                extra_payload.get("history_reason_codes"),
                normalized_reason_codes,
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("history_reason_codes"),
                current.get("last_reason_codes"),
                normalized_reason_codes,
            )
        )
        effective_history_reason_codes = self._pick_strings(*history_reason_codes_values)
        history_next_action_values = (
            (
                current.get("last_next_action"),
                extra_payload.get("history_next_action"),
                normalized_next_action,
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("history_next_action"),
                current.get("last_next_action"),
                normalized_next_action,
            )
        )
        effective_history_next_action = self._pick_string(*history_next_action_values)
        if not degraded and was_degraded:
            effective_history_degraded_since_ts_ms = self._pick_int(
                current.get("degraded_since_ts_ms"),
                extra_payload.get("history_degraded_since_ts_ms"),
                current.get("history_degraded_since_ts_ms"),
            )
            effective_history_recovered_at_ts_ms = self._pick_int(
                last_recovered_ts_ms,
                extra_payload.get("history_recovered_at_ts_ms"),
                current.get("history_recovered_at_ts_ms"),
                now_ms,
            )
        elif degraded:
            effective_history_degraded_since_ts_ms = self._pick_int(
                extra_payload.get("history_degraded_since_ts_ms"),
                current.get("history_degraded_since_ts_ms"),
                degraded_since_ts_ms,
            )
            effective_history_recovered_at_ts_ms = 0
        else:
            effective_history_degraded_since_ts_ms = self._pick_int(
                extra_payload.get("history_degraded_since_ts_ms"),
                current.get("history_degraded_since_ts_ms"),
            )
            effective_history_recovered_at_ts_ms = self._pick_int(
                extra_payload.get("history_recovered_at_ts_ms"),
                current.get("history_recovered_at_ts_ms"),
                last_recovered_ts_ms,
            )
        effective_reliability_class = self._pick_string(
            extra_payload.get("reliability_class"),
            current.get("reliability_class"),
            "stable",
            default="stable",
        )
        effective_reliability_reason_code = self._pick_string(
            extra_payload.get("reliability_reason_code"),
            current.get("reliability_reason_code"),
            "ok",
            default="ok",
        )
        effective_reliability_reason_codes = self._pick_strings(
            extra_payload.get("reliability_reason_codes"), current.get("reliability_reason_codes")
        )
        effective_reliability_next_action = self._pick_string(
            extra_payload.get("reliability_next_action"),
            current.get("reliability_next_action"),
            normalized_next_action,
        )
        effective_component_reliability_class = self._pick_string(
            extra_payload.get("component_reliability_class"),
            current.get("component_reliability_class"),
            effective_reliability_class,
            default=effective_reliability_class,
        )
        effective_component_reliability_reason_code = self._pick_string(
            extra_payload.get("component_reliability_reason_code"),
            current.get("component_reliability_reason_code"),
            effective_reliability_reason_code,
            default=effective_reliability_reason_code,
        )
        effective_component_reliability_reason_codes = self._pick_strings(
            extra_payload.get("component_reliability_reason_codes"),
            current.get("component_reliability_reason_codes"),
            effective_reliability_reason_codes,
        )
        effective_component_reliability_next_action = self._pick_string(
            extra_payload.get("component_reliability_next_action"),
            current.get("component_reliability_next_action"),
            effective_reliability_next_action,
        )
        family_hardening_reason_code_values = (
            (
                current.get("family_hardening_reason_codes"),
                extra_payload.get("family_hardening_reason_codes"),
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("family_hardening_reason_codes"),
                current.get("family_hardening_reason_codes"),
            )
        )
        effective_family_hardening_reason_codes = self._pick_strings(
            *family_hardening_reason_code_values
        )
        receipt_outcome_truth_reason_code_values = (
            (
                current.get("receipt_outcome_truth_reason_codes"),
                extra_payload.get("receipt_outcome_truth_reason_codes"),
            )
            if (not degraded and was_degraded)
            else (
                extra_payload.get("receipt_outcome_truth_reason_codes"),
                current.get("receipt_outcome_truth_reason_codes"),
            )
        )
        effective_receipt_outcome_truth_reason_codes = self._pick_strings(
            *receipt_outcome_truth_reason_code_values
        )
        effective_component_recovered_fragile = bool(
            extra_payload.get(
                "component_recovered_fragile",
                current.get("component_recovered_fragile", False),
            )
        )
        if degraded:
            effective_component_recovered_fragile = False
        elif effective_history_component and effective_component_reliability_class == "fragile":
            effective_component_recovered_fragile = True
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
        canonical_history_status = (
            "blocked"
            if degraded
            else ("recovered" if int(last_recovered_ts_ms or 0) > 0 else "steady")
        )
        payload = {
            "component": component_name,
            "is_degraded": bool(degraded),
            "degraded_since_ts_ms": int(degraded_since_ts_ms or 0),
            "last_recovered_ts_ms": int(last_recovered_ts_ms or 0),
            "degraded_count": int(degraded_count or 0),
            "last_healthy_ts_ms": int(last_healthy_ts_ms or 0),
            "updated_ts_ms": int(now_ms or 0),
            "history_status": canonical_history_status,
            "last_reason_code": normalized_reason_code,
            "last_stage": normalized_stage,
            "last_blocker_component": normalized_component,
            "last_next_action": normalized_next_action,
            "last_reason_codes": normalized_reason_codes,
            "history_component": effective_history_component,
            "history_stage": effective_history_stage,
            "history_reason_code": effective_history_reason_code,
            "history_reason_codes": effective_history_reason_codes,
            "history_next_action": effective_history_next_action,
            "history_degraded_since_ts_ms": effective_history_degraded_since_ts_ms,
            "history_recovered_at_ts_ms": effective_history_recovered_at_ts_ms,
            "reliability_class": effective_reliability_class,
            "reliability_reason_code": effective_reliability_reason_code,
            "reliability_reason_codes": effective_reliability_reason_codes,
            "reliability_next_action": effective_reliability_next_action,
            "component_reliability_class": effective_component_reliability_class,
            "component_reliability_reason_code": effective_component_reliability_reason_code,
            "component_reliability_reason_codes": effective_component_reliability_reason_codes,
            "component_reliability_next_action": effective_component_reliability_next_action,
            "component_recovered_fragile": effective_component_recovered_fragile,
            "family_hardening_reason_codes": effective_family_hardening_reason_codes,
            "receipt_outcome_truth_reason_codes": effective_receipt_outcome_truth_reason_codes,
        }
        if extra_payload:
            payload.update(extra_payload)
        payload["component"] = component_name
        payload["is_degraded"] = bool(degraded)
        payload["degraded_since_ts_ms"] = int(degraded_since_ts_ms or 0)
        payload["last_recovered_ts_ms"] = int(last_recovered_ts_ms or 0)
        payload["degraded_count"] = int(degraded_count or 0)
        payload["last_healthy_ts_ms"] = int(last_healthy_ts_ms or 0)
        payload["updated_ts_ms"] = int(now_ms or 0)
        payload["history_status"] = canonical_history_status
        payload["last_reason_code"] = normalized_reason_code
        payload["last_stage"] = normalized_stage
        payload["last_blocker_component"] = normalized_component
        payload["last_next_action"] = normalized_next_action
        payload["last_reason_codes"] = list(normalized_reason_codes)
        payload["history_component"] = effective_history_component
        payload["history_stage"] = effective_history_stage
        payload["history_reason_code"] = effective_history_reason_code
        payload["history_reason_codes"] = list(effective_history_reason_codes)
        payload["history_next_action"] = effective_history_next_action
        payload["history_degraded_since_ts_ms"] = int(effective_history_degraded_since_ts_ms or 0)
        payload["history_recovered_at_ts_ms"] = int(effective_history_recovered_at_ts_ms or 0)
        payload["reliability_class"] = effective_reliability_class
        payload["reliability_reason_code"] = effective_reliability_reason_code
        payload["reliability_reason_codes"] = list(effective_reliability_reason_codes)
        payload["reliability_next_action"] = effective_reliability_next_action
        payload["component_reliability_class"] = effective_component_reliability_class
        payload["component_reliability_reason_code"] = effective_component_reliability_reason_code
        payload["component_reliability_reason_codes"] = list(
            effective_component_reliability_reason_codes
        )
        payload["component_reliability_next_action"] = effective_component_reliability_next_action
        payload["family_hardening_reason_codes"] = list(effective_family_hardening_reason_codes)
        payload["receipt_outcome_truth_reason_codes"] = list(
            effective_receipt_outcome_truth_reason_codes
        )
        payload["component_recovered_fragile"] = effective_component_recovered_fragile
        material_context_changed = (
            normalized_reason_code != str(current.get("last_reason_code") or "")
            or normalized_stage != str(current.get("last_stage") or "")
            or normalized_component != str(current.get("last_blocker_component") or "")
            or normalized_next_action != str(current.get("last_next_action") or "")
            or normalized_reason_codes != self._string_list(current.get("last_reason_codes") or [])
        )
        event_type = ""
        if degraded and not was_degraded:
            event_type = "blocked"
        elif not degraded and was_degraded:
            event_type = "recovered"
        elif degraded and was_degraded and material_context_changed:
            event_type = "blocked_update"
        event_blocker_component = normalized_component
        event_next_action = normalized_next_action
        event_stage = normalized_stage
        event_reason_code = normalized_reason_code
        event_reason_codes = list(normalized_reason_codes)
        if event_type == "recovered":
            event_blocker_component = normalized_component
            event_next_action = normalized_next_action
            event_stage = normalized_stage
            event_reason_code = normalized_reason_code
            event_reason_codes = list(normalized_reason_codes)
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO auto_trade_recovery_state(
                    chain, component, is_degraded, degraded_since_ts_ms, last_recovered_ts_ms,
                    updated_ts_ms, last_reason_code, payload_json
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    self.chain,
                    component_name,
                    1 if degraded else 0,
                    self._int_like(payload.get("degraded_since_ts_ms")),
                    self._int_like(payload.get("last_recovered_ts_ms")),
                    self._int_like(payload.get("updated_ts_ms")),
                    str(payload["last_reason_code"]),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            if event_type:
                event_payload = {
                    "component": component_name,
                    "degraded": bool(event_type != "recovered"),
                    "history_status": ("blocked" if degraded else "recovered"),
                    "stage": event_stage,
                    "reason_code": event_reason_code,
                    "reason_codes": event_reason_codes,
                    "history_reason_code": effective_history_reason_code,
                    "history_reason_codes": effective_history_reason_codes,
                    "history_next_action": effective_history_next_action,
                    "history_degraded_since_ts_ms": int(
                        effective_history_degraded_since_ts_ms or 0
                    ),
                    "history_recovered_at_ts_ms": int(effective_history_recovered_at_ts_ms or 0),
                    "blocker_component": event_blocker_component,
                    "next_action": event_next_action,
                    "degraded_count": self._int_like(payload.get("degraded_count")),
                    "degraded_since_ts_ms": self._int_like(
                        effective_history_degraded_since_ts_ms
                        if event_type == "recovered"
                        else payload.get("degraded_since_ts_ms")
                    ),
                    "recovered_at_ts_ms": self._int_like(
                        effective_history_recovered_at_ts_ms
                        if event_type == "recovered"
                        else payload.get("last_recovered_ts_ms")
                    ),
                    "last_healthy_ts_ms": self._int_like(payload.get("last_healthy_ts_ms")),
                    "updated_ts_ms": self._int_like(payload.get("updated_ts_ms")),
                    "history_component": effective_history_component,
                    "history_stage": effective_history_stage,
                    "reliability_class": effective_reliability_class,
                    "reliability_reason_code": effective_reliability_reason_code,
                    "reliability_reason_codes": effective_reliability_reason_codes,
                    "reliability_next_action": effective_reliability_next_action,
                    "component_reliability_class": effective_component_reliability_class,
                    "component_reliability_reason_code": effective_component_reliability_reason_code,
                    "component_reliability_reason_codes": effective_component_reliability_reason_codes,
                    "component_reliability_next_action": effective_component_reliability_next_action,
                    "component_recovered_fragile": effective_component_recovered_fragile,
                    "family_hardening_reason_codes": effective_family_hardening_reason_codes,
                    "receipt_outcome_truth_reason_codes": effective_receipt_outcome_truth_reason_codes,
                }
                conn.execute(
                    """
                    INSERT INTO auto_trade_recovery_events(
                        chain, component, ts_ms, event_type, stage, reason_code,
                        blocker_component, next_action, payload_json
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.chain,
                        component_name,
                        int(now_ms or 0),
                        str(event_type),
                        event_stage,
                        event_reason_code,
                        event_blocker_component,
                        event_next_action,
                        json.dumps(event_payload, sort_keys=True),
                    ),
                )
        return payload
