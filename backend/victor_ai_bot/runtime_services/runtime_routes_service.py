from __future__ import annotations

from typing import Any, Dict, Tuple

from ..deploy_mode import deployment_mode, is_public_mode, public_broadcast_override_enabled
from ..jsonsafe import json_safe
from ..api_routes._route_helpers import (
    coerce_canonical_bool,
    coerce_non_negative_int,
    coerce_non_negative_int_string,
    invalid_request_payload,
    unexpected_request_fields,
)


class RuntimeRoutesService:
    _ALLOWED_SETTINGS_FIELDS = {
        "auto_trading",
        "gas_mode",
        "send_mode",
        "auto_reinvest_enabled",
        "reinvest_rate",
        "brain_mode",
        "base_borrow_amount",
        "dry_run",
    }
    _VALID_GAS_MODES = {"standard", "fast", "instant"}
    _VALID_SEND_MODES = {"public", "private", "protected_rpc"}
    _VALID_BRAIN_MODES = {"off", "shadow", "suggest", "auto"}

    def deploy_info(self) -> Dict[str, Any]:
        return json_safe(
            {
                "ok": True,
                "mode": deployment_mode(),
                "public_mode": bool(is_public_mode()),
                "public_allow_broadcast": bool(public_broadcast_override_enabled()),
                "brand": {"name": "x∆v", "slogan": "Sovereign Capital"},
            }
        )

    def _normalize_mode(
        self, payload: Dict[str, Any], field: str, valid_values: set[str], reason_code: str
    ) -> Tuple[bool, Any]:
        if field not in payload:
            return True, None
        value = str(payload.get(field) or "").strip().lower()
        if value not in valid_values:
            return False, invalid_request_payload(
                reason_code, field=field, value=payload.get(field)
            )
        return True, value

    def validate_settings_patch(self, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        extras = unexpected_request_fields(payload, allowed_fields=self._ALLOWED_SETTINGS_FIELDS)
        if extras:
            return False, invalid_request_payload(
                "unknown_request_fields",
                details={"fields": extras},
            )

        patch: Dict[str, Any] = {}

        for field in ("auto_trading", "auto_reinvest_enabled", "dry_run"):
            if field in payload:
                ok, coerced = coerce_canonical_bool(payload.get(field))
                if not ok:
                    return False, invalid_request_payload(
                        "invalid_boolean_value",
                        field=field,
                        value=payload.get(field),
                    )
                patch[field] = coerced

        if "reinvest_rate" in payload:
            ok, coerced = coerce_non_negative_int(payload.get("reinvest_rate"))
            if not ok:
                return False, invalid_request_payload(
                    "invalid_integer_value",
                    field="reinvest_rate",
                    value=payload.get("reinvest_rate"),
                )
            patch["reinvest_rate"] = coerced

        if "base_borrow_amount" in payload:
            ok, coerced = coerce_non_negative_int_string(payload.get("base_borrow_amount"))
            if not ok:
                return False, invalid_request_payload(
                    "invalid_integer_value",
                    field="base_borrow_amount",
                    value=payload.get("base_borrow_amount"),
                )
            patch["base_borrow_amount"] = coerced

        for field, valid, reason_code in (
            ("gas_mode", self._VALID_GAS_MODES, "invalid_gas_mode"),
            ("send_mode", self._VALID_SEND_MODES, "invalid_send_mode"),
            ("brain_mode", self._VALID_BRAIN_MODES, "invalid_brain_mode"),
        ):
            ok, normalized = self._normalize_mode(payload, field, valid, reason_code)
            if not ok:
                return False, normalized
            if normalized is not None:
                patch[field] = normalized

        if not patch:
            return False, invalid_request_payload("empty_settings_patch")

        return True, patch
