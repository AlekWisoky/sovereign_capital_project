from __future__ import annotations

from typing import Any, Dict, List

from ..fund_os.family_identity import family_identity, family_matches


DEFAULT_FAMILY = "flashloan_atomic"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _unique_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        sval = str(value or "").strip()
        if sval and sval not in out:
            out.append(sval)
    return out


def family_identity_payload(value: Any) -> Dict[str, Any]:
    return family_identity(str(value or DEFAULT_FAMILY) or DEFAULT_FAMILY)


def build_receipt_summary_projection(receipt_summary: Dict[str, Any]) -> Dict[str, Any]:
    receipt = _safe_dict(receipt_summary)
    state_contract = _safe_dict(receipt.get("stateContract"))
    last_identity = _safe_dict(receipt.get("lastFamilyIdentity"))
    if not last_identity:
        last_identity = family_identity_payload(
            receipt.get("lastRuntimeFamily")
            or receipt.get("lastFamily")
            or receipt.get("lastRouteFamily")
            or DEFAULT_FAMILY
        )
    return {
        "ok": bool(receipt.get("ok", True)),
        "stateContract": state_contract,
        "lastTxHash": str(receipt.get("lastTxHash") or ""),
        "lastRouteFamily": str(receipt.get("lastRouteFamily") or ""),
        "lastFamily": str(receipt.get("lastFamily") or last_identity.get("launchFamily") or ""),
        "lastRuntimeFamily": str(
            receipt.get("lastRuntimeFamily") or last_identity.get("runtimeFamily") or ""
        ),
        "lastCapitalFamily": str(
            receipt.get("lastCapitalFamily") or last_identity.get("capitalFamily") or ""
        ),
        "lastDisplayFamily": str(
            receipt.get("lastDisplayFamily") or last_identity.get("displayName") or ""
        ),
        "lastFamilyAliases": list(
            receipt.get("lastFamilyAliases") or last_identity.get("aliases") or []
        ),
        "lastFamilyIdentity": last_identity,
        "lastProvider": str(receipt.get("lastProvider") or ""),
        "lastFlashloanFeeWei": _safe_int(receipt.get("lastFlashloanFeeWei")),
        "lastBorrowCostUsd": _safe_float(receipt.get("lastBorrowCostUsd")),
        "lastBorrowing": _safe_dict(receipt.get("lastBorrowing")),
        "lastLoanSettlement": _safe_dict(receipt.get("lastLoanSettlement")),
        "lastTerminalProfitabilityAuthority": _safe_dict(
            receipt.get("lastTerminalProfitabilityAuthority")
        ),
        "lastCapitalAdmission": _safe_dict(receipt.get("lastCapitalAdmission")),
        "lastLearningSync": _safe_dict(receipt.get("lastLearningSync")),
        "lastMemorySync": _safe_dict(receipt.get("lastMemorySync")),
        "lastClosedLoop": _safe_dict(receipt.get("lastClosedLoop")),
    }


def _route_family_matches(family: str, route_family: Any) -> bool:
    route_text = str(route_family or "")
    if not route_text:
        return False
    prefix = route_text.split("|", 1)[0]
    return family_matches(family=family, candidate=prefix)


def _lifecycle_matches_receipt(family: str, receipt: Dict[str, Any]) -> bool:
    return bool(
        family_matches(family=family, candidate=str(receipt.get("lastRuntimeFamily") or ""))
        or family_matches(family=family, candidate=str(receipt.get("lastFamily") or ""))
        or _route_family_matches(family, receipt.get("lastRouteFamily"))
    )


def _lifecycle_matches_live_item(family: str, item: Dict[str, Any]) -> bool:
    return bool(
        family_matches(family=family, candidate=str(item.get("runtimeFamily") or ""))
        or family_matches(family=family, candidate=str(item.get("family") or ""))
        or _route_family_matches(family, item.get("routeFamily"))
    )


def _build_execution_lifecycle(
    *,
    family_value: Any,
    live_items: List[Dict[str, Any]],
    receipt: Dict[str, Any],
    auto_trade_gate: Dict[str, Any],
    execution_gate: Dict[str, Any],
    v1_focus: Dict[str, Any],
) -> Dict[str, Any]:
    family_info = family_identity_payload(family_value)
    family_launch = str(family_info.get("launchFamily") or "")
    family_items = [
        item for item in live_items if _lifecycle_matches_live_item(family_launch, item)
    ]
    latest = _safe_dict(family_items[-1]) if family_items else {}
    receipt_matches = _lifecycle_matches_receipt(family_launch, receipt)
    effective_receipt = receipt if receipt_matches else {}
    learning_sync = _safe_dict(effective_receipt.get("lastLearningSync"))
    memory_sync = _safe_dict(effective_receipt.get("lastMemorySync"))
    closed_loop = _safe_dict(effective_receipt.get("lastClosedLoop"))
    v1_runtime_family = str(v1_focus.get("runtimeFamily") or DEFAULT_FAMILY)
    focus_aligned = bool(
        family_matches(family=family_launch, candidate=v1_runtime_family)
        or family_matches(
            family=str(latest.get("runtimeFamily") or ""), candidate=v1_runtime_family
        )
    )
    can_trade_now = bool(auto_trade_gate.get("allowed", True)) and not bool(
        execution_gate.get("blocked", False)
    )
    family_trade_eligible = can_trade_now and (focus_aligned or bool(family_items))
    closed_loop_completed = bool(closed_loop.get("completed", False))
    reason_codes = _unique_strings(
        [
            *[str(x) for x in list(closed_loop.get("reasonCodes") or []) if str(x)],
            *[str(x) for x in list(auto_trade_gate.get("reasonCodes") or []) if str(x)],
            *[str(x) for x in list(execution_gate.get("reason_codes") or []) if str(x)],
        ]
    )
    terminal_profitability = _safe_dict(
        effective_receipt.get("lastTerminalProfitabilityAuthority")
    ) or _safe_dict(latest.get("terminalProfitabilityAuthority"))
    capital_admission = _safe_dict(effective_receipt.get("lastCapitalAdmission")) or _safe_dict(
        latest.get("capitalAdmission")
    )
    borrowing = _safe_dict(effective_receipt.get("lastBorrowing")) or _safe_dict(
        latest.get("flashloan")
    )
    loan_settlement = _safe_dict(effective_receipt.get("lastLoanSettlement"))
    provider = str(
        effective_receipt.get("lastProvider")
        or _safe_dict(latest.get("flashloan")).get("selectedProvider")
        or ""
    )
    tx_hash = str(effective_receipt.get("lastTxHash") or latest.get("txHash") or "")
    route_family = str(effective_receipt.get("lastRouteFamily") or latest.get("routeFamily") or "")
    phase = str(
        _safe_dict(effective_receipt.get("stateContract")).get("phase")
        or ("execution_pending" if family_items else "idle")
    )
    return {
        "focusFamily": str(v1_focus.get("launchFamily") or ""),
        "focusRuntimeFamily": v1_runtime_family,
        "focusCapitalFamily": str(v1_focus.get("capitalFamily") or ""),
        "focusDisplayFamily": str(v1_focus.get("displayName") or ""),
        "focusAliases": list(v1_focus.get("aliases") or []),
        "configured": bool(v1_focus.get("isCore", False)),
        "family": family_launch,
        "requestedFamily": str(family_info.get("requestedFamily") or family_launch),
        "runtimeFamily": str(family_info.get("runtimeFamily") or family_launch),
        "capitalFamily": str(family_info.get("capitalFamily") or family_launch),
        "displayFamily": str(family_info.get("displayName") or family_launch),
        "familyAliases": list(family_info.get("aliases") or []),
        "familyIdentity": family_info,
        "routeFamily": route_family,
        "txHash": tx_hash,
        "provider": provider,
        "flashloanFeeWei": _safe_int(
            effective_receipt.get("lastFlashloanFeeWei") or borrowing.get("flashloanFeeWei")
        ),
        "borrowCostUsd": _safe_float(
            effective_receipt.get("lastBorrowCostUsd") or borrowing.get("borrowCostUsd")
        ),
        "borrowing": borrowing,
        "loanSettlement": loan_settlement,
        "terminalProfitabilityAuthority": terminal_profitability,
        "capitalAdmission": capital_admission,
        "pendingCount": len(family_items),
        "pendingActive": bool(family_items),
        "pendingLane": str(latest.get("lane") or ""),
        "autoTradingReady": family_trade_eligible,
        "executionBlocked": bool(execution_gate.get("blocked", False)),
        "autoTradeStage": str(auto_trade_gate.get("stage") or "ok"),
        "v1FocusAligned": focus_aligned,
        "focusAligned": focus_aligned,
        "learningSync": learning_sync,
        "memorySync": memory_sync,
        "closedLoop": closed_loop,
        "settlementRecorded": bool(closed_loop.get("settlementAccounting", False)),
        "closedLoopCompleted": closed_loop_completed,
        "endToEndConfirmed": bool(closed_loop_completed),
        "reasonCodes": reason_codes,
        "nextAction": str(
            closed_loop.get("nextAction") or auto_trade_gate.get("suggestedNextAction") or ""
        ),
        "receiptSummaryState": _safe_dict(effective_receipt.get("stateContract")),
        "phase": phase,
    }


def build_execution_lifecycle_projections(
    *,
    live_execution: Dict[str, Any],
    receipt_summary: Dict[str, Any],
    auto_trade_gate: Dict[str, Any],
    execution_gate: Dict[str, Any],
    v1_focus: Dict[str, Any],
) -> List[Dict[str, Any]]:
    live = _safe_dict(live_execution)
    live_items = list(live.get("items") or []) if isinstance(live.get("items"), list) else []
    receipt = build_receipt_summary_projection(receipt_summary)
    family_values = _unique_strings(
        [
            str(v1_focus.get("runtimeFamily") or DEFAULT_FAMILY),
            str(receipt.get("lastRuntimeFamily") or ""),
            str(receipt.get("lastFamily") or ""),
            *[
                str(
                    _safe_dict(item).get("runtimeFamily")
                    or _safe_dict(item).get("family")
                    or _safe_dict(item).get("routeFamily")
                    or ""
                )
                for item in live_items
            ],
        ]
    )
    lifecycles = [
        _build_execution_lifecycle(
            family_value=family_value,
            live_items=live_items,
            receipt=receipt,
            auto_trade_gate=auto_trade_gate,
            execution_gate=execution_gate,
            v1_focus=v1_focus,
        )
        for family_value in family_values
    ]
    lifecycles.sort(
        key=lambda item: (
            0 if bool(item.get("v1FocusAligned")) else 1,
            0 if bool(item.get("pendingActive")) else 1,
            0 if bool(item.get("settlementRecorded")) else 1,
            str(item.get("family") or ""),
        )
    )
    return lifecycles


def select_focus_execution_lifecycle(
    lifecycles: List[Dict[str, Any]], v1_focus: Dict[str, Any]
) -> Dict[str, Any]:
    focus_family = str(v1_focus.get("launchFamily") or "")
    for item in lifecycles:
        if family_matches(family=str(item.get("family") or ""), candidate=focus_family):
            return dict(item)
    return _build_execution_lifecycle(
        family_value=v1_focus.get("runtimeFamily") or DEFAULT_FAMILY,
        live_items=[],
        receipt={},
        auto_trade_gate={
            "allowed": False,
            "stage": "unavailable",
            "reasonCodes": ["focus_lifecycle_unavailable"],
        },
        execution_gate={"blocked": True, "reason_codes": ["focus_lifecycle_unavailable"]},
        v1_focus=v1_focus,
    )
