from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Header, Request

from ..fund_os.launch_modes import LaunchMode
from ..jsonsafe import to_json_safe as json_safe
from ..security.auth import require_capability
from ..security.permissions import Capability
from ..runtime_services.control_state import unavailable_state
from ..runtime_services.family_hardening_service import family_hardening_unavailable_summary
from ..runtime_services.auxiliary_state_service import AuxiliaryStateService
from ..runtime_services.capital_truth_read_context import build_capital_truth_read_context
from ._route_helpers import (
    attach_summary_contract,
    coerce_non_empty_string,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
)

router = APIRouter(tags=["launch"])


_LAUNCH_ROUTE_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


_ALLOWED_LAUNCH_MODES = frozenset(mode.value for mode in LaunchMode)


def _reject_unknown_fields(
    payload: Dict[str, Any], *, allowed_fields: frozenset[str]
) -> Dict[str, Any] | None:
    unknown_fields = unexpected_request_fields(payload, allowed_fields=allowed_fields)
    if not unknown_fields:
        return None
    return invalid_request_payload(
        "unknown_request_fields",
        details={"fields": unknown_fields, "allowed_fields": sorted(allowed_fields)},
    )


def _coerce_payload_string(
    payload: Dict[str, Any],
    *,
    field: str,
    required: bool,
) -> tuple[bool, Dict[str, Any] | None, str]:
    if field not in payload:
        if required:
            return False, invalid_request_payload(f"missing_{field}", field=field), ""
        return True, None, ""
    ok, value = coerce_non_empty_string(payload.get(field))
    if ok:
        return True, None, value
    return (
        False,
        invalid_request_payload("invalid_string_value", field=field, value=payload.get(field)),
        "",
    )


def _validated_launch_family(
    body: Dict[str, Any], *, allow_missing: bool
) -> tuple[bool, Dict[str, Any] | None, str]:
    rejected = _reject_unknown_fields(body, allowed_fields=frozenset({"family"}))
    if rejected is not None:
        return False, rejected, ""
    return _coerce_payload_string(body, field="family", required=not allow_missing)


def _family_hardening_unavailable_payload(family: str | None = None) -> Dict[str, Any]:
    return family_hardening_unavailable_summary(family)


def _launch_family_hardening_payload(rt: Any, family: str | None = None) -> Dict[str, Any]:
    if not hasattr(rt, "family_hardening_state"):
        return _family_hardening_unavailable_payload(family)
    try:
        payload = rt.family_hardening_state()
    except _LAUNCH_ROUTE_FAILURES:
        return _family_hardening_unavailable_payload(family)
    if not isinstance(payload, ABCMapping):
        return _family_hardening_unavailable_payload(family)
    payload_dict = dict(payload)
    if family:
        items = [
            item for item in list(payload_dict.get("items") or []) if isinstance(item, ABCMapping)
        ]
        for item in items:
            if str(item.get("family") or "") == str(family):
                return dict(item)
        return _family_hardening_unavailable_payload(family)
    return payload_dict


def _launch_service_unavailable(rt, family: str | None = None):
    payload = unavailable_state("launch_service_unavailable")
    if family:
        payload["hardening"] = _launch_family_hardening_payload(rt, family)
    else:
        payload["familyHardening"] = _launch_family_hardening_payload(rt)
    return json_safe(with_auto_trade_route_projection(payload, runtime=rt))


def _launch_state_failed_payload(rt) -> Dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "launch_state_failed",
            extra={"familyHardening": _launch_family_hardening_payload(rt)},
        ),
        runtime=rt,
    )


def _launch_family_detail_failed_payload(rt, family: str) -> Dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "launch_family_detail_failed",
            extra={"hardening": _launch_family_hardening_payload(rt, family)},
        ),
        runtime=rt,
    )


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def require_admin_write(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_WRITE, request=request, x_admin_key=x_admin_key)


@router.get("/api/launch/state")
def launch_state(rt=Depends(get_runtime)):
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return attach_summary_contract(
            _launch_service_unavailable(rt),
            family="launch",
            read_model="launch_summary_projection_v1",
            runtime=rt,
        )
    return safe_json_route_call(
        lambda: attach_summary_contract(
            with_auto_trade_route_projection(
                {
                    **dict(svc.summary(rt) or {}),
                    **build_capital_truth_read_context(
                        rt,
                        auxiliary_state=AuxiliaryStateService(),
                    ).capital_surface,
                },
                runtime=rt,
            ),
            family="launch",
            read_model="launch_summary_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            _launch_state_failed_payload(rt),
            family="launch",
            read_model="launch_summary_projection_v1",
            runtime=rt,
        ),
    )


@router.post("/api/launch/mode", dependencies=[Depends(require_admin_write)])
def set_launch_mode(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"mode"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, mode = _coerce_payload_string(payload, field="mode", required=True)
    if not ok:
        return json_safe(rejected)
    if mode not in _ALLOWED_LAUNCH_MODES:
        return json_safe(
            invalid_request_payload(
                "invalid_launch_mode",
                field="mode",
                value=mode,
                details={"allowed_modes": sorted(_ALLOWED_LAUNCH_MODES)},
            )
        )
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return _launch_service_unavailable(rt)
    return json_safe(svc.set_mode(rt, mode))


@router.post("/api/launch/enable-next", dependencies=[Depends(require_admin_write)])
def enable_next(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    ok, rejected, family = _validated_launch_family(payload, allow_missing=True)
    if not ok:
        return json_safe(rejected)
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return _launch_service_unavailable(rt)
    return json_safe(svc.enable_next(rt, family))


@router.post("/api/launch/pause-family", dependencies=[Depends(require_admin_write)])
def pause_family(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    ok, rejected, family = _validated_launch_family(payload, allow_missing=False)
    if not ok:
        return json_safe(rejected)
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return _launch_service_unavailable(rt, family)
    return json_safe(svc.pause_family(rt, family))


@router.post("/api/launch/revert-family", dependencies=[Depends(require_admin_write)])
def revert_family(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    ok, rejected, family = _validated_launch_family(payload, allow_missing=False)
    if not ok:
        return json_safe(rejected)
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return _launch_service_unavailable(rt, family)
    return json_safe(svc.revert_family(rt, family))


@router.post("/api/launch/quarantine-family", dependencies=[Depends(require_admin_write)])
def quarantine_family(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"family", "reason_code"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, family = _coerce_payload_string(payload, field="family", required=True)
    if not ok:
        return json_safe(rejected)
    ok, rejected, reason_code = _coerce_payload_string(payload, field="reason_code", required=False)
    if not ok:
        return json_safe(rejected)
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return _launch_service_unavailable(rt, family)
    return json_safe(
        svc.quarantine_family(
            rt,
            family,
            reason_code=reason_code or "operator_quarantine",
        )
    )


@router.get("/api/launch/family/{family}")
def family_detail(family: str, rt=Depends(get_runtime)):
    svc = getattr(rt, "_launch_service", None)
    if svc is None:
        return attach_summary_contract(
            _launch_service_unavailable(rt, family),
            family="launch_family",
            read_model="launch_family_projection_v1",
            runtime=rt,
        )
    return safe_json_route_call(
        lambda: attach_summary_contract(
            with_auto_trade_route_projection(svc.family_detail(rt, family), runtime=rt),
            family="launch_family",
            read_model="launch_family_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            _launch_family_detail_failed_payload(rt, family),
            family="launch_family",
            read_model="launch_family_projection_v1",
            runtime=rt,
        ),
    )
