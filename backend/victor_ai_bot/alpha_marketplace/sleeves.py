from __future__ import annotations

import math
from typing import Any, Dict, Iterable

from ..runtime_services.canonical_settlement_interface import canonical_settled_outcomes


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def project_strategy_sleeves(
    runtime: Any,
    *,
    strategy_ids: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Project marketplace sleeves from canonical settlement + existing Prime state.

    This is a read-only projection. It never reserves capital, mutates Prime/Treasury,
    promotes a strategy, or authorizes execution.
    """
    requested = {str(value).strip() for value in (strategy_ids or []) if str(value).strip()}
    outcomes = canonical_settled_outcomes(runtime)
    prime = dict(
        runtime.internal_prime_state()
        if hasattr(runtime, "internal_prime_state")
        else getattr(getattr(runtime, "_internal_prime", None), "snapshot", lambda: {})()
        or {}
    )
    prime_ready = bool(prime.get("stateReady", True))
    if not prime_ready:
        return {
            "ok": False,
            "reason_code": str(prime.get("stateReasonCode") or "internal_prime_state_unavailable"),
            "primeState": prime,
            "sleeves": {},
        }

    sleeves: Dict[str, Dict[str, Any]] = {}

    def sleeve(strategy_id: str) -> Dict[str, Any]:
        return sleeves.setdefault(
            strategy_id,
            {
                "strategyId": strategy_id,
                "capitalSleeveStatus": "unfunded",
                "primeCommittedUsd": 0.0,
                "settledCount": 0,
                "expectedNetUsd": 0.0,
                "realizedNetUsd": 0.0,
                "expectationErrorUsd": 0.0,
                "verifiedSettlementCount": 0,
                "decisionIds": [],
                "receiptIds": [],
            },
        )

    for outcome in outcomes:
        strategy_id = str(outcome.get("strategy_id") or "").strip()
        if not strategy_id or (requested and strategy_id not in requested):
            continue
        if not bool(outcome.get("truth_verified")) or not bool(outcome.get("settlement_verified")):
            continue
        realized = _finite_float(outcome.get("realized_net_usd"))
        if realized is None:
            continue
        item = sleeve(strategy_id)
        expected = _finite_float(outcome.get("expected_net_usd"))
        item["settledCount"] += 1
        item["verifiedSettlementCount"] += 1
        item["realizedNetUsd"] = round(float(item["realizedNetUsd"]) + realized, 8)
        if expected is not None:
            item["expectedNetUsd"] = round(float(item["expectedNetUsd"]) + expected, 8)
            item["expectationErrorUsd"] = round(
                float(item["expectationErrorUsd"]) + (realized - expected), 8
            )
        decision_id = str(outcome.get("decision_id") or "")
        receipt_id = str(outcome.get("receipt_id") or "")
        if decision_id and decision_id not in item["decisionIds"]:
            item["decisionIds"].append(decision_id)
        if receipt_id and receipt_id not in item["receiptIds"]:
            item["receiptIds"].append(receipt_id)

    for loan in list(prime.get("openLoans") or []) + list(prime.get("disputedLoans") or []):
        if not isinstance(loan, dict):
            continue
        strategy_id = str(loan.get("strategy_id") or loan.get("strategyId") or "").strip()
        if not strategy_id or (requested and strategy_id not in requested):
            continue
        item = sleeve(strategy_id)
        notional = _finite_float(loan.get("notional_usd"))
        if notional is not None and notional >= 0.0:
            item["primeCommittedUsd"] = round(float(item["primeCommittedUsd"]) + notional, 8)

    for item in sleeves.values():
        if float(item["primeCommittedUsd"]) > 0.0:
            item["capitalSleeveStatus"] = "funded"
        elif int(item["verifiedSettlementCount"]) > 0:
            item["capitalSleeveStatus"] = "settled_unfunded"

    return {
        "ok": True,
        "reason_code": "ok",
        "primeState": {
            "stateReady": prime_ready,
            "capacityUsd": prime.get("capacityUsd"),
            "borrowedUsd": prime.get("borrowedUsd"),
            "utilization": prime.get("utilization"),
        },
        "sleeves": sleeves,
    }


__all__ = ["project_strategy_sleeves"]
