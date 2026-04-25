from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..runtime_services.summary_read_contract import build_summary_read_contract

from ._route_helpers import (
    auto_trade_route_projection,
    degraded_payload,
    safe_json_route_call,
)


def _camel_recovery_event(item):
    data = dict(item) if isinstance(item, dict) else {}
    history_status = str(data.get("history_status") or "steady")
    stage = str(data.get("stage") or "")
    if history_status == "recovered" and (not stage or stage == "ok"):
        stage = str(data.get("history_stage") or stage or "ok")
    if not stage:
        stage = "ok"
    reason_codes = [str(x) for x in list(data.get("reason_codes") or []) if str(x)]
    reason_code = str(data.get("reason_code") or "")
    if history_status == "recovered" and (not reason_code or reason_code == "ok"):
        history_reason_codes = [
            str(x) for x in list(data.get("history_reason_codes") or []) if str(x)
        ]
        reason_code = str(
            data.get("history_reason_code")
            or (history_reason_codes[0] if history_reason_codes else "")
            or (reason_codes[0] if reason_codes else "")
            or reason_code
            or "ok"
        )
        if history_reason_codes:
            reason_codes = history_reason_codes
    if not reason_code:
        reason_code = "ok"
    return {
        "tsMs": int(data.get("ts_ms") or 0),
        "eventType": str(data.get("event_type") or ""),
        "stage": stage,
        "reasonCode": reason_code,
        "reasonCodes": reason_codes,
        "component": str(data.get("blocker_component") or data.get("history_component") or ""),
        "suggestedNextAction": str(
            data.get("next_action")
            or data.get("component_reliability_next_action")
            or data.get("reliability_next_action")
            or ""
        ),
        "historyStatus": history_status,
        "degraded": bool(data.get("degraded", history_status in {"blocked", "degraded"})),
        "degradedSinceTsMs": int(data.get("degraded_since_ts_ms") or 0),
        "recoveredAtTsMs": int(data.get("recovered_at_ts_ms") or 0),
        "lastHealthyTsMs": int(data.get("last_healthy_ts_ms") or 0),
        "updatedTsMs": int(data.get("updated_ts_ms") or 0),
        "degradedCount": int(data.get("degraded_count") or 0),
        "historyComponent": str(
            data.get("history_component") or data.get("blocker_component") or ""
        ),
        "historyStage": str(data.get("history_stage") or data.get("stage") or "ok"),
        "reliabilityClass": str(data.get("reliability_class") or "stable"),
        "reliabilityReasonCode": str(data.get("reliability_reason_code") or "ok"),
        "reliabilityReasonCodes": [
            str(x) for x in list(data.get("reliability_reason_codes") or []) if str(x)
        ],
        "reliabilityNextAction": str(data.get("reliability_next_action") or ""),
        "componentReliabilityClass": str(
            data.get("component_reliability_class") or data.get("reliability_class") or "stable"
        ),
        "componentReliabilityReasonCode": str(
            data.get("component_reliability_reason_code")
            or data.get("reliability_reason_code")
            or "ok"
        ),
        "componentReliabilityReasonCodes": [
            str(x)
            for x in list(
                data.get("component_reliability_reason_codes")
                or data.get("reliability_reason_codes")
                or []
            )
            if str(x)
        ],
        "componentReliabilityNextAction": str(
            data.get("component_reliability_next_action")
            or data.get("reliability_next_action")
            or ""
        ),
        "componentRecoveredFragile": bool(
            data.get(
                "component_recovered_fragile",
                str(data.get("history_status") or "") == "recovered"
                and str(
                    data.get("component_reliability_class") or data.get("reliability_class") or ""
                )
                == "fragile",
            )
        ),
        "familyHardeningReasonCodes": [
            str(x) for x in list(data.get("family_hardening_reason_codes") or []) if str(x)
        ],
        "receiptOutcomeTruthReasonCodes": [
            str(x) for x in list(data.get("receipt_outcome_truth_reason_codes") or []) if str(x)
        ],
    }


def _camel_recovery(recovery):
    data = dict(recovery) if isinstance(recovery, dict) else {}
    history_status = str(data.get("history_status") or "steady")
    project_history = bool(
        history_status == "recovered"
        and (
            bool(data.get("component_recovered_fragile", False))
            or str(data.get("component_reliability_class") or data.get("reliability_class") or "")
            == "fragile"
        )
    )
    stage = str(data.get("stage") or "")
    if project_history and (not stage or stage == "ok"):
        stage = str(data.get("history_stage") or stage or "ok")
    if not stage:
        stage = "ok"
    reason_codes = [str(x) for x in list(data.get("reason_codes") or []) if str(x)]
    reason_code = str(data.get("reason_code") or "")
    if project_history and (not reason_code or reason_code == "ok"):
        history_reason_codes = [
            str(x) for x in list(data.get("history_reason_codes") or []) if str(x)
        ]
        reason_code = str(
            data.get("history_reason_code")
            or (history_reason_codes[0] if history_reason_codes else "")
            or (reason_codes[0] if reason_codes else "")
            or reason_code
            or "ok"
        )
        if history_reason_codes:
            reason_codes = history_reason_codes
    if not reason_code:
        reason_code = "ok"
    return {
        "blocked": bool(data.get("blocked", False)),
        "ready": bool(data.get("ready", True)),
        "stage": stage,
        "status": str(data.get("status") or "ready"),
        "reasonCode": reason_code,
        "reasonCodes": reason_codes,
        "suggestedNextAction": str(
            data.get("next_action")
            or data.get("component_reliability_next_action")
            or data.get("reliability_next_action")
            or ""
        ),
        "component": str(data.get("component") or data.get("history_component") or ""),
        "historyStatus": history_status,
        "degradedSinceTsMs": int(data.get("degraded_since_ts_ms") or 0),
        "recoveredAtTsMs": int(data.get("recovered_at_ts_ms") or 0),
        "degradedDurationMs": int(data.get("degraded_duration_ms") or 0),
        "degradedCount": int(data.get("degraded_count") or 0),
        "lastHealthyTsMs": int(data.get("last_healthy_ts_ms") or 0),
        "recoveredRecently": bool(data.get("recovered_recently", False)),
        "degradationSeverityClass": str(data.get("degradation_severity_class") or "stable"),
        "historyComponent": str(data.get("history_component") or ""),
        "historyStage": str(data.get("history_stage") or "ok"),
        "reliabilityClass": str(data.get("reliability_class") or "stable"),
        "reliabilityReasonCode": str(data.get("reliability_reason_code") or "ok"),
        "reliabilityReasonCodes": [
            str(x) for x in list(data.get("reliability_reason_codes") or []) if str(x)
        ],
        "reliabilityNextAction": str(data.get("reliability_next_action") or ""),
        "componentReliabilityClass": str(
            data.get("component_reliability_class") or data.get("reliability_class") or "stable"
        ),
        "componentReliabilityReasonCode": str(
            data.get("component_reliability_reason_code")
            or data.get("reliability_reason_code")
            or "ok"
        ),
        "componentReliabilityReasonCodes": [
            str(x)
            for x in list(
                data.get("component_reliability_reason_codes")
                or data.get("reliability_reason_codes")
                or []
            )
            if str(x)
        ],
        "componentReliabilityNextAction": str(
            data.get("component_reliability_next_action")
            or data.get("reliability_next_action")
            or ""
        ),
        "componentRecoveredFragile": bool(
            data.get(
                "component_recovered_fragile",
                str(data.get("history_status") or "") == "recovered"
                and str(
                    data.get("component_reliability_class") or data.get("reliability_class") or ""
                )
                == "fragile",
            )
        ),
        "familyHardeningReasonCodes": [
            str(x) for x in list(data.get("family_hardening_reason_codes") or []) if str(x)
        ],
        "receiptOutcomeTruthReasonCodes": [
            str(x) for x in list(data.get("receipt_outcome_truth_reason_codes") or []) if str(x)
        ],
    }


def _camel_auto_trade_gate(gate):
    data = dict(gate) if isinstance(gate, dict) else {}
    return {
        "allowed": bool(data.get("allowed", True)),
        "stage": str(data.get("stage") or "ok"),
        "reasonCode": str(data.get("reason_code") or "ok"),
        "reasonCodes": [str(x) for x in list(data.get("reason_codes") or []) if str(x)],
        "suggestedNextAction": str(data.get("next_action") or ""),
    }


router = APIRouter(tags=["telemetry"])


def _attach_summary_contract(payload, *, family: str, phase: str, read_model: str):
    body = dict(payload) if isinstance(payload, dict) else {}
    body["summaryContract"] = build_summary_read_contract(
        family=family,
        payload=body,
        phase=phase,
        read_model=read_model,
    )
    return body


def _telemetry_summary_failed_payload():
    projection = auto_trade_route_projection(include_recent_events=True)
    recovery = projection["auto_trade_recovery"]
    auto_trade_gate = projection["auto_trade_gate"]
    payload = degraded_payload(
        "telemetry_summary_failed",
        extra={"realization": {"families": []}, "agents": {"agents": []}},
    )
    payload["auto_trade_recovery"] = recovery
    payload["auto_trade_recovery_view"] = _camel_recovery(recovery)
    payload["auto_trade_gate"] = auto_trade_gate
    payload["auto_trade_gate_view"] = _camel_auto_trade_gate(auto_trade_gate)
    return _attach_summary_contract(
        payload,
        family="telemetry",
        phase="telemetry_summary",
        read_model="telemetry_summary_projection_v1",
    )


def _telemetry_summary_payload(rt):
    payload = rt.telemetry_summary()
    if not isinstance(payload, dict):
        payload = {"realization": {"families": []}, "agents": {"agents": []}}
    else:
        payload = dict(payload)
    projection = auto_trade_route_projection(rt)
    recovery = projection["auto_trade_recovery"]
    auto_trade_gate = projection["auto_trade_gate"]
    payload["auto_trade_recovery"] = recovery
    payload["auto_trade_recovery_view"] = _camel_recovery(recovery)
    payload["auto_trade_gate"] = auto_trade_gate
    payload["auto_trade_gate_view"] = _camel_auto_trade_gate(auto_trade_gate)
    return _attach_summary_contract(
        payload,
        family="telemetry",
        phase="telemetry_summary",
        read_model="telemetry_summary_projection_v1",
    )


def _execution_calibration_failed_payload():
    projection = auto_trade_route_projection(include_recent_events=True)
    recovery = projection["auto_trade_recovery"]
    auto_trade_gate = projection["auto_trade_gate"]
    payload = degraded_payload("execution_calibration_failed", extra={"items": []})
    payload["auto_trade_recovery"] = recovery
    payload["auto_trade_recovery_view"] = _camel_recovery(recovery)
    payload["auto_trade_gate"] = auto_trade_gate
    payload["auto_trade_gate_view"] = _camel_auto_trade_gate(auto_trade_gate)
    return _attach_summary_contract(
        payload,
        family="execution_calibration",
        phase="execution_calibration_summary",
        read_model="execution_calibration_summary_projection_v1",
    )


def _execution_calibration_payload(rt):
    payload = rt.execution_calibration_state()
    if not isinstance(payload, dict):
        payload = {"items": []}
    else:
        payload = dict(payload)
    projection = auto_trade_route_projection(rt)
    recovery = projection["auto_trade_recovery"]
    auto_trade_gate = projection["auto_trade_gate"]
    payload["auto_trade_recovery"] = recovery
    payload["auto_trade_recovery_view"] = _camel_recovery(recovery)
    payload["auto_trade_gate"] = auto_trade_gate
    payload["auto_trade_gate_view"] = _camel_auto_trade_gate(auto_trade_gate)
    return _attach_summary_contract(
        payload,
        family="execution_calibration",
        phase="execution_calibration_summary",
        read_model="execution_calibration_summary_projection_v1",
    )


def _auto_trade_recovery_failed_payload():
    projection = auto_trade_route_projection(include_recent_events=True)
    recovery = projection["auto_trade_recovery"]
    auto_trade_gate = projection["auto_trade_gate"]
    return _attach_summary_contract(
        degraded_payload(
            "auto_trade_recovery_failed",
            extra={
                "component": "auto_trade_admission",
                "recovery": recovery,
                "recovery_view": _camel_recovery(recovery),
                "auto_trade_gate": auto_trade_gate,
                "auto_trade_gate_view": _camel_auto_trade_gate(auto_trade_gate),
                "events": [],
                "history": [],
                "history_items": [],
                "event_count": 0,
            },
        ),
        family="auto_trade_recovery",
        phase="auto_trade_recovery_summary",
        read_model="auto_trade_recovery_summary_projection_v1",
    )


def _auto_trade_recovery_payload(rt):
    projection = auto_trade_route_projection(rt, include_recent_events=True)
    recovery = dict(projection["auto_trade_recovery"])
    events = [
        dict(item)
        for item in list(recovery.pop("recent_events", []) or [])
        if isinstance(item, dict)
    ]
    history_items = [_camel_recovery_event(item) for item in events]
    auto_trade_gate = projection["auto_trade_gate"]
    return _attach_summary_contract(
        {
            "ok": True,
            "status": "ok",
            "component": "auto_trade_admission",
            "recovery": recovery,
            "recovery_view": _camel_recovery(recovery),
            "auto_trade_gate": auto_trade_gate,
            "auto_trade_gate_view": _camel_auto_trade_gate(auto_trade_gate),
            "events": events,
            "history": list(events),
            "history_items": history_items,
            "event_count": len(events),
        },
        family="auto_trade_recovery",
        phase="auto_trade_recovery_summary",
        read_model="auto_trade_recovery_summary_projection_v1",
    )


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/telemetry/summary")
def telemetry_summary(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _telemetry_summary_payload(rt),
        on_error=lambda exc: _telemetry_summary_failed_payload(),
    )


@router.get("/api/execution/calibration")
def execution_calibration(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _execution_calibration_payload(rt),
        on_error=lambda exc: _execution_calibration_failed_payload(),
    )


@router.get("/api/telemetry/auto-trade-recovery")
def auto_trade_recovery(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _auto_trade_recovery_payload(rt),
        on_error=lambda exc: _auto_trade_recovery_failed_payload(),
    )
