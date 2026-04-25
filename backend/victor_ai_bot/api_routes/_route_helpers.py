from __future__ import annotations

import math
from typing import Any, Callable, Mapping

_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}

from ..jsonsafe import to_json_safe as json_safe
from ..runtime_services.state_service import (
    auto_trade_gate_info_from_recovery,
    auto_trade_recovery_info,
    current_auto_trade_recovery_info,
)
from ..runtime_services.auxiliary_state_service import AuxiliaryStateService
from ..runtime_services.summary_read_contract import build_summary_read_contract
from ..runtime_services.capital_truth_read_context import build_capital_truth_read_context

_ROUTE_FAILURE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    LookupError,
    TypeError,
    ValueError,
    RuntimeError,
    OSError,
)

_AUDIT_APPEND_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    RuntimeError,
)


def safe_json_route_call(
    action: Callable[[], Any],
    *,
    fallback: Mapping[str, Any] | None = None,
    on_error: Callable[[Exception], Mapping[str, Any]] | None = None,
):
    try:
        return json_safe(action())
    except _ROUTE_FAILURE_EXCEPTIONS as exc:
        payload = on_error(exc) if on_error is not None else (fallback or {"ok": False})
        return json_safe(dict(payload))


def append_optional_audit(audit: Any, event: str, payload: Mapping[str, Any], **meta: Any) -> bool:
    if audit is None or not hasattr(audit, "append"):
        return False
    try:
        audit.append(event, dict(payload), **meta)
        return True
    except _AUDIT_APPEND_EXCEPTIONS:
        return False


def degraded_payload(
    reason_code: str,
    *,
    extra: Mapping[str, Any] | None = None,
    include_error: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "status": "degraded",
        "reason_code": str(reason_code),
        "reason": str(reason_code),
    }
    if include_error:
        payload["error"] = str(reason_code)
    if extra:
        payload.update(dict(extra))
    return payload


def invalid_request_payload(
    reason_code: str,
    *,
    field: str | None = None,
    value: Any = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "status": "invalid",
        "reason_code": str(reason_code),
        "reason": str(reason_code),
        "error": str(reason_code),
    }
    detail_payload: dict[str, Any] = {}
    if field is not None:
        detail_payload["field"] = str(field)
    if value is not None:
        detail_payload["value"] = value
    if details:
        detail_payload.update(dict(details))
    if detail_payload:
        payload["details"] = detail_payload
    return payload


def coerce_canonical_bool(value: Any) -> tuple[bool, bool]:
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


def coerce_non_negative_int(value: Any) -> tuple[bool, int]:
    if isinstance(value, bool):
        return False, 0
    if isinstance(value, int):
        return (value >= 0), value
    if isinstance(value, float):
        if value.is_integer() and value >= 0:
            return True, int(value)
        return False, 0
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return False, 0
        try:
            parsed = int(normalized, 10)
        except ValueError:
            return False, 0
        return (parsed >= 0), parsed
    return False, 0


def coerce_non_negative_int_string(value: Any) -> tuple[bool, str]:
    ok, parsed = coerce_non_negative_int(value)
    if not ok:
        return False, "0"
    return True, str(parsed)


def coerce_positive_int(value: Any) -> tuple[bool, int]:
    ok, parsed = coerce_non_negative_int(value)
    if not ok or parsed <= 0:
        return False, 0
    return True, parsed


def coerce_non_empty_string(value: Any) -> tuple[bool, str]:
    if value is None:
        return False, ""
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return True, normalized
        return False, ""
    normalized = str(value).strip()
    if normalized:
        return True, normalized
    return False, ""


def coerce_finite_float(value: Any) -> tuple[bool, float]:
    if isinstance(value, bool):
        return False, 0.0
    if isinstance(value, (int, float)):
        parsed = float(value)
        if math.isfinite(parsed):
            return True, parsed
        return False, 0.0
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return False, 0.0
        try:
            parsed = float(normalized)
        except ValueError:
            return False, 0.0
        if math.isfinite(parsed):
            return True, parsed
        return False, 0.0
    return False, 0.0


def coerce_non_negative_float(value: Any) -> tuple[bool, float]:
    if isinstance(value, bool):
        return False, 0.0
    if isinstance(value, (int, float)):
        parsed = float(value)
        if math.isfinite(parsed) and parsed >= 0.0:
            return True, parsed
        return False, 0.0
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return False, 0.0
        try:
            parsed = float(normalized)
        except ValueError:
            return False, 0.0
        if math.isfinite(parsed) and parsed >= 0.0:
            return True, parsed
        return False, 0.0
    return False, 0.0


def unexpected_request_fields(
    payload: Mapping[str, Any], *, allowed_fields: set[str] | frozenset[str]
) -> list[str]:
    allowed = {str(field) for field in allowed_fields}
    return sorted(str(field) for field in payload.keys() if str(field) not in allowed)


def auto_trade_route_projection(
    runtime: Any | None = None,
    *,
    include_recent_events: bool = False,
) -> dict[str, Any]:
    recovery = (
        dict(current_auto_trade_recovery_info(runtime))
        if runtime is not None
        else dict(auto_trade_recovery_info(None))
    )
    if include_recent_events and "recent_events" not in recovery:
        recovery["recent_events"] = []
    projection = {
        "auto_trade_recovery": recovery,
        "auto_trade_gate": auto_trade_gate_info_from_recovery(recovery),
    }
    if runtime is not None:
        try:
            projection["capitalTruthHealth"] = build_capital_truth_read_context(runtime).capital_truth_health
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            projection["capitalTruthHealth"] = {}
    return projection


def attach_summary_contract(
    payload: Mapping[str, Any] | None = None,
    *,
    family: str,
    read_model: str,
    runtime: Any | None = None,
    source_contracts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(payload or {})
    capital_contract: Mapping[str, Any] | None = None
    capital_policy: Mapping[str, Any] | None = None
    if runtime is not None:
        try:
            context = build_capital_truth_read_context(runtime, auxiliary_state=AuxiliaryStateService())
            capital_contract = dict(context.capital_contract or {})
            capital_policy = dict(context.capital_policy or {})
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            capital_contract = None
            capital_policy = None
    out["summaryContract"] = build_summary_read_contract(
        family=str(family or "summary"),
        payload=out,
        capital_contract=capital_contract,
        capital_policy=capital_policy,
        source_contracts=source_contracts,
        phase=str(f"{family}_summary"),
        read_model=str(read_model or f"{family}_summary_projection_v1"),
    )
    return out


def with_auto_trade_route_projection(
    payload: Mapping[str, Any] | None = None,
    *,
    runtime: Any | None = None,
    include_recent_events: bool = False,
) -> dict[str, Any]:
    out = dict(payload or {})
    out.update(
        auto_trade_route_projection(
            runtime,
            include_recent_events=include_recent_events,
        )
    )
    return out
