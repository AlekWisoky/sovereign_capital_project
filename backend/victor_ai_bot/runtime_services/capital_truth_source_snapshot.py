from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class CapitalTruthSourceSnapshotBundle:
    sources: Dict[str, Dict[str, Any]]
    family_targets: Dict[str, float]
    family_allocations_wei: Dict[str, int]
    receipt_last_ts_ms: int
    receipt_outcome_ts_ms: int
    ledger_event_ts_ms: int
    receipt_event_ts_ms: int
    bankroll_history_payload: Dict[str, Any]
    treasury_history_payload: Dict[str, Any]
    internal_prime_history_payload: Dict[str, Any]
    bankroll_event_payload: Dict[str, Any]
    bankroll_event_state: Dict[str, Any]
    treasury_event_payload: Dict[str, Any]
    treasury_event_capital_engine: Dict[str, Any]
    ledger_event_payload: Dict[str, Any]
    receipt_event_payload: Dict[str, Any]
    prime_event_payload: Dict[str, Any]
    lineage_anchor_commit_id: str


def normalize_ts_ms(value: Any) -> int:
    try:
        raw = int(value or 0)
    except (TypeError, ValueError):
        return 0
    if raw <= 0:
        return 0
    if raw < 1_000_000_000_000:
        raw *= 1000
    return int(raw)


def max_ts_ms(values: Any) -> int:
    best = 0
    for value in values:
        normalized = normalize_ts_ms(value)
        if normalized > best:
            best = normalized
    return int(best)


def freshness_class(*, age_ms: int | None, available: bool, material: bool) -> str:
    if not material:
        return "idle"
    if not available:
        return "unavailable"
    if age_ms is None:
        return "unknown"
    if age_ms <= 15 * 60 * 1000:
        return "current"
    if age_ms <= 6 * 60 * 60 * 1000:
        return "recent"
    if age_ms <= 24 * 60 * 60 * 1000:
        return "aging"
    return "stale"


def build_source_snapshot(
    *,
    name: str,
    now_ms: int,
    ts_ms: int,
    material: bool,
    available: bool,
    details: Dict[str, Any] | None = None,
    append_reason: Any,
) -> Dict[str, Any]:
    normalized_ts_ms = normalize_ts_ms(ts_ms)
    age_ms = max(0, int(now_ms) - normalized_ts_ms) if normalized_ts_ms > 0 else None
    freshness = freshness_class(
        age_ms=age_ms,
        available=bool(available),
        material=bool(material),
    )
    reason_codes: list[str] = []
    if material and not available:
        append_reason(reason_codes, f"{name}_unavailable")
    if material and freshness in {"unknown", "stale", "unavailable"}:
        append_reason(reason_codes, f"{name}_freshness_{freshness}")
    return {
        "name": str(name),
        "material": bool(material),
        "available": bool(available),
        "ts_ms": int(normalized_ts_ms or 0),
        "age_ms": int(age_ms or 0) if age_ms is not None else None,
        "freshness_class": freshness,
        "reason_codes": reason_codes,
        "details": dict(details or {}),
    }


def capital_commit_id_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("capitalCommitId", "capital_commit_id"):
        value = payload.get(key)
        if value:
            return str(value)
    for nested_key in ("metadata", "payload", "state", "journal_tx", "state_snapshot"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            value = capital_commit_id_from_payload(nested)
            if value:
                return str(value)
    return ""


def state_field_mismatches(
    current: Dict[str, Any], recorded: Dict[str, Any], fields: list[str]
) -> list[str]:
    mismatches: list[str] = []
    for field in fields:
        if current.get(field) != recorded.get(field):
            mismatches.append(str(field))
    return mismatches


def bankroll_ts_ms(current_bankroll_state: Dict[str, Any]) -> int:
    return max_ts_ms(
        [
            current_bankroll_state.get("updated_ts_ms"),
            current_bankroll_state.get("profit_updated_ts_ms"),
            current_bankroll_state.get("sizing_updated_ts_ms"),
        ]
    )


def capital_engine_ts_ms(
    capital_state: Dict[str, Any],
    capital_engine: Dict[str, Any],
    efficiency: Dict[str, Any],
    reinvestment: Dict[str, Any] | None = None,
) -> int:
    return max_ts_ms(
        [
            capital_state.get("updated_ts_ms"),
            capital_state.get("updatedTsMs"),
            capital_state.get("ts_ms"),
            capital_state.get("ts"),
            capital_engine.get("updated_ts_ms"),
            capital_engine.get("updatedTsMs"),
            capital_engine.get("observed_ts_ms"),
            efficiency.get("updated_ts_ms"),
            efficiency.get("updatedTsMs"),
            (reinvestment or {}).get("updated_ts_ms"),
            (reinvestment or {}).get("updatedTsMs"),
        ]
    )


def internal_prime_ts_ms(internal_prime_state: Dict[str, Any]) -> int:
    values: list[Any] = [
        internal_prime_state.get("updated_ts_ms"),
        internal_prime_state.get("updatedTsMs"),
        internal_prime_state.get("stateUpdatedTsMs"),
    ]
    for loan in list(internal_prime_state.get("openLoans") or []) + list(
        internal_prime_state.get("disputedLoans") or []
    ):
        if not isinstance(loan, dict):
            continue
        values.extend(
            [
                loan.get("openedTsMs"),
                loan.get("settledTsMs"),
                loan.get("disputedTsMs"),
                loan.get("opened_ts_ms"),
                loan.get("settled_ts_ms"),
                loan.get("disputed_ts_ms"),
            ]
        )
    return max_ts_ms(values)


def build_capital_truth_source_snapshots(
    *,
    now_ms: int,
    ledger_ts_ms: int,
    realized_profit_wei: int,
    deployed_capital_wei: int,
    borrowed_usd: float,
    prime_open_loan_count: int,
    capital_state: Dict[str, Any],
    capital_engine: Dict[str, Any],
    efficiency: Dict[str, Any],
    reinvestment: Dict[str, Any],
    receipt_settlement: Dict[str, Any],
    receipt_outcome_truth: Dict[str, Any],
    internal_prime_state: Dict[str, Any],
    current_bankroll_state: Dict[str, Any],
    bankroll_history_event: Dict[str, Any],
    treasury_history_snapshot: Dict[str, Any],
    internal_prime_state_history_snapshot: Dict[str, Any],
    bankroll_history_enabled: bool,
    treasury_history_enabled: bool,
    internal_prime_history_enabled: bool,
    capital_event_enabled: bool,
    capital_event_bankroll: Dict[str, Any],
    capital_event_treasury: Dict[str, Any],
    capital_event_ledger: Dict[str, Any],
    capital_event_receipt: Dict[str, Any],
    capital_event_internal_prime: Dict[str, Any],
    append_reason: Any,
) -> CapitalTruthSourceSnapshotBundle:
    sources: Dict[str, Dict[str, Any]] = {}

    ledger_material = bool(
        ledger_ts_ms
        or realized_profit_wei > 0
        or deployed_capital_wei > 0
        or borrowed_usd > 0.0
        or prime_open_loan_count > 0
    )
    sources["ledger"] = build_source_snapshot(
        name="ledger",
        now_ms=now_ms,
        ts_ms=ledger_ts_ms,
        material=ledger_material,
        available=bool(ledger_ts_ms > 0),
        details={"last_ts_ms": int(ledger_ts_ms or 0)},
        append_reason=append_reason,
    )

    capital_engine_updated_ts_ms = capital_engine_ts_ms(
        capital_state,
        capital_engine,
        efficiency,
        reinvestment,
    )
    capital_engine_material = bool(capital_engine or efficiency)
    sources["capital_engine"] = build_source_snapshot(
        name="capital_engine",
        now_ms=now_ms,
        ts_ms=capital_engine_updated_ts_ms,
        material=capital_engine_material,
        available=bool(capital_engine_material),
        details={
            "family_target_count": int(len(dict(capital_engine.get("family_targets") or {}))),
            "family_allocation_count": int(
                len(dict(capital_engine.get("family_allocations_wei") or {}))
            ),
        },
        append_reason=append_reason,
    )

    family_targets = {
        str(k): float(v or 0.0) for k, v in dict(capital_engine.get("family_targets") or {}).items()
    }
    family_allocations_wei = {
        str(k): int(v or 0)
        for k, v in dict(capital_engine.get("family_allocations_wei") or {}).items()
    }
    family_material = bool(family_targets or family_allocations_wei)
    sources["family_allocations"] = build_source_snapshot(
        name="family_allocations",
        now_ms=now_ms,
        ts_ms=capital_engine_updated_ts_ms,
        material=family_material,
        available=bool(family_material),
        details={
            "family_target_count": int(len(family_targets)),
            "family_allocation_count": int(len(family_allocations_wei)),
        },
        append_reason=append_reason,
    )

    receipt_last_ts_ms = max_ts_ms(
        [
            receipt_settlement.get("last_observed_ts_ms"),
            dict(receipt_settlement.get("pnl_receipts") or {}).get("last_ts_ms"),
            dict(receipt_settlement.get("ledger_receipts") or {}).get("last_ts_ms"),
            dict(receipt_settlement.get("withdraw_history") or {}).get("last_ts_ms"),
        ]
    )
    receipt_material = bool(
        int(dict(receipt_settlement.get("pnl_receipts") or {}).get("successful_count") or 0)
        or int(dict(receipt_settlement.get("ledger_receipts") or {}).get("count") or 0)
        or int(dict(receipt_settlement.get("withdraw_history") or {}).get("count") or 0)
        or realized_profit_wei > 0
    )
    sources["receipt_settlement"] = build_source_snapshot(
        name="receipt_settlement",
        now_ms=now_ms,
        ts_ms=receipt_last_ts_ms,
        material=receipt_material,
        available=bool(receipt_last_ts_ms > 0) or not receipt_material,
        details={
            "pnl_receipt_count": int(
                dict(receipt_settlement.get("pnl_receipts") or {}).get("successful_count") or 0
            ),
            "ledger_receipt_count": int(
                dict(receipt_settlement.get("ledger_receipts") or {}).get("count") or 0
            ),
        },
        append_reason=append_reason,
    )

    receipt_outcome_updated_ts_ms = max_ts_ms(
        [
            receipt_outcome_truth.get("updated_ts_ms"),
            receipt_outcome_truth.get("last_healthy_ts_ms"),
            receipt_outcome_truth.get("last_recovered_ts_ms"),
        ]
    )
    receipt_outcome_material = bool(receipt_material or receipt_outcome_truth)
    sources["receipt_outcome_truth"] = build_source_snapshot(
        name="receipt_outcome_truth",
        now_ms=now_ms,
        ts_ms=receipt_outcome_updated_ts_ms,
        material=receipt_outcome_material,
        available=bool(receipt_outcome_truth),
        details={
            "is_degraded": bool(receipt_outcome_truth.get("is_degraded", False)),
        },
        append_reason=append_reason,
    )

    internal_prime_updated_ts_ms = internal_prime_ts_ms(internal_prime_state)
    internal_prime_material = bool(borrowed_usd > 0.0 or prime_open_loan_count > 0)
    internal_prime_runtime_commit_id = capital_commit_id_from_payload(
        dict(internal_prime_state or {})
    )
    sources["internal_prime"] = build_source_snapshot(
        name="internal_prime",
        now_ms=now_ms,
        ts_ms=internal_prime_updated_ts_ms,
        material=internal_prime_material,
        available=bool(internal_prime_state),
        details={
            "borrowed_usd": round(float(borrowed_usd), 8),
            "open_loan_count": int(prime_open_loan_count),
            "capital_commit_id": str(internal_prime_runtime_commit_id or ""),
        },
        append_reason=append_reason,
    )

    internal_prime_history_payload = dict(
        internal_prime_state_history_snapshot.get("payload") or {}
    )
    internal_prime_history_ts_ms = max_ts_ms(
        [
            internal_prime_state_history_snapshot.get("ts_ms"),
            internal_prime_history_payload.get("updatedTsMs"),
            internal_prime_history_payload.get("updated_ts_ms"),
        ]
    )
    internal_prime_history_commit_id = capital_commit_id_from_payload(
        internal_prime_history_payload
    )
    sources["internal_prime_state_history"] = build_source_snapshot(
        name="internal_prime_state_history",
        now_ms=now_ms,
        ts_ms=internal_prime_history_ts_ms,
        material=bool(internal_prime_material and internal_prime_history_enabled),
        available=bool(internal_prime_state_history_snapshot)
        or not bool(internal_prime_material and internal_prime_history_enabled),
        details={
            "state_type": str(internal_prime_state_history_snapshot.get("state_type") or ""),
            "capital_commit_id": str(internal_prime_history_commit_id or ""),
        },
        append_reason=append_reason,
    )

    bankroll_updated_ts_ms = bankroll_ts_ms(current_bankroll_state)
    bankroll_material = bool(realized_profit_wei > 0 or deployed_capital_wei > 0)
    sources["bankroll"] = build_source_snapshot(
        name="bankroll",
        now_ms=now_ms,
        ts_ms=bankroll_updated_ts_ms,
        material=bankroll_material,
        available=bool(current_bankroll_state),
        details={
            "realized_profit_wei": str(max(0, int(realized_profit_wei))),
            "native_ts_ms": int(bankroll_updated_ts_ms or 0),
        },
        append_reason=append_reason,
    )

    bankroll_history_payload = dict(bankroll_history_event.get("state") or {})
    bankroll_history_ts_ms = max_ts_ms(
        [
            bankroll_history_event.get("ts_ms"),
            bankroll_history_payload.get("updated_ts_ms"),
            bankroll_history_payload.get("profit_updated_ts_ms"),
            bankroll_history_payload.get("sizing_updated_ts_ms"),
        ]
    )
    sources["bankroll_history"] = build_source_snapshot(
        name="bankroll_history",
        now_ms=now_ms,
        ts_ms=bankroll_history_ts_ms,
        material=bool(bankroll_material and bankroll_history_enabled),
        available=bool(bankroll_history_event)
        or not bool(bankroll_material and bankroll_history_enabled),
        details={
            "event_type": str(bankroll_history_event.get("event_type") or ""),
            "realized_profit_wei": str(
                max(0, int(bankroll_history_payload.get("realized_profit_wei") or 0))
            ),
            "last_amount_in_wei": str(
                max(0, int(bankroll_history_payload.get("last_amount_in_wei") or 0))
            ),
            "capital_commit_id": str(capital_commit_id_from_payload(bankroll_history_event) or ""),
        },
        append_reason=append_reason,
    )

    treasury_history_payload = dict(treasury_history_snapshot.get("payload") or {})
    treasury_history_ts_ms = max_ts_ms(
        [treasury_history_snapshot.get("ts_ms"), treasury_history_payload.get("updated_ts_ms")]
    )
    sources["treasury_state_history"] = build_source_snapshot(
        name="treasury_state_history",
        now_ms=now_ms,
        ts_ms=treasury_history_ts_ms,
        material=bool(capital_engine_material and treasury_history_enabled),
        available=bool(treasury_history_snapshot)
        or not bool(capital_engine_material and treasury_history_enabled),
        details={
            "state_type": str(treasury_history_snapshot.get("state_type") or ""),
            "observed_ts_ms": int(treasury_history_payload.get("observed_ts_ms") or 0),
            "capital_commit_id": str(
                capital_commit_id_from_payload(treasury_history_payload) or ""
            ),
        },
        append_reason=append_reason,
    )

    bankroll_event_payload = dict(capital_event_bankroll.get("payload") or {})
    bankroll_event_state = dict(bankroll_event_payload.get("state") or {})
    bankroll_event_ts_ms = max_ts_ms(
        [
            capital_event_bankroll.get("ts_ms"),
            bankroll_event_state.get("updated_ts_ms"),
            bankroll_event_state.get("profit_updated_ts_ms"),
            bankroll_event_state.get("sizing_updated_ts_ms"),
        ]
    )
    sources["capital_event_bankroll"] = build_source_snapshot(
        name="capital_event_bankroll",
        now_ms=now_ms,
        ts_ms=bankroll_event_ts_ms,
        material=bool(bankroll_material and capital_event_enabled),
        available=bool(capital_event_bankroll)
        or not bool(bankroll_material and capital_event_enabled),
        details={
            "event_type": str(capital_event_bankroll.get("event_type") or ""),
            "source": str(capital_event_bankroll.get("source") or ""),
            "capital_commit_id": str(capital_commit_id_from_payload(bankroll_event_payload) or ""),
        },
        append_reason=append_reason,
    )

    treasury_event_payload = dict(capital_event_treasury.get("payload") or {})
    treasury_event_capital_engine = dict(treasury_event_payload.get("capital_engine") or {})
    treasury_event_ts_ms = max_ts_ms(
        [
            capital_event_treasury.get("ts_ms"),
            treasury_event_payload.get("updated_ts_ms"),
            treasury_event_capital_engine.get("updated_ts_ms"),
        ]
    )
    sources["capital_event_treasury"] = build_source_snapshot(
        name="capital_event_treasury",
        now_ms=now_ms,
        ts_ms=treasury_event_ts_ms,
        material=bool(capital_engine_material and capital_event_enabled),
        available=bool(capital_event_treasury)
        or not bool(capital_engine_material and capital_event_enabled),
        details={
            "event_type": str(capital_event_treasury.get("event_type") or ""),
            "source": str(capital_event_treasury.get("source") or ""),
            "capital_commit_id": str(capital_commit_id_from_payload(treasury_event_payload) or ""),
        },
        append_reason=append_reason,
    )

    ledger_event_payload = dict(capital_event_ledger.get("payload") or {})
    ledger_event_ts_ms = max_ts_ms([capital_event_ledger.get("ts_ms")])
    sources["capital_event_ledger"] = build_source_snapshot(
        name="capital_event_ledger",
        now_ms=now_ms,
        ts_ms=ledger_event_ts_ms,
        material=bool(ledger_material and capital_event_enabled),
        available=bool(capital_event_ledger) or not bool(ledger_material and capital_event_enabled),
        details={
            "event_type": str(capital_event_ledger.get("event_type") or ""),
            "transaction_id": str(capital_event_ledger.get("transaction_id") or ""),
            "receipt_id": str(capital_event_ledger.get("receipt_id") or ""),
            "tx_type": str(ledger_event_payload.get("tx_type") or ""),
        },
        append_reason=append_reason,
    )

    receipt_event_payload = dict(capital_event_receipt.get("payload") or {})
    receipt_event_ts_ms = max_ts_ms(
        [capital_event_receipt.get("ts_ms"), receipt_event_payload.get("ts_ms")]
    )
    sources["capital_event_receipt"] = build_source_snapshot(
        name="capital_event_receipt",
        now_ms=now_ms,
        ts_ms=receipt_event_ts_ms,
        material=bool(receipt_material and capital_event_enabled),
        available=bool(capital_event_receipt)
        or not bool(receipt_material and capital_event_enabled),
        details={
            "event_type": str(capital_event_receipt.get("event_type") or ""),
            "transaction_id": str(capital_event_receipt.get("transaction_id") or ""),
            "receipt_id": str(capital_event_receipt.get("receipt_id") or ""),
            "capital_commit_id": str(capital_commit_id_from_payload(receipt_event_payload) or ""),
        },
        append_reason=append_reason,
    )

    prime_event_payload = dict(capital_event_internal_prime.get("payload") or {})
    prime_event_ts_ms = max_ts_ms(
        [
            capital_event_internal_prime.get("ts_ms"),
            prime_event_payload.get("updatedTsMs"),
            prime_event_payload.get("updated_ts_ms"),
        ]
    )
    sources["capital_event_internal_prime"] = build_source_snapshot(
        name="capital_event_internal_prime",
        now_ms=now_ms,
        ts_ms=prime_event_ts_ms,
        material=bool(
            capital_event_enabled and (prime_open_loan_count > 0 or capital_event_internal_prime)
        ),
        available=bool(capital_event_internal_prime)
        or not bool(
            capital_event_enabled and (prime_open_loan_count > 0 or capital_event_internal_prime)
        ),
        details={
            "event_type": str(capital_event_internal_prime.get("event_type") or ""),
            "transaction_id": str(capital_event_internal_prime.get("transaction_id") or ""),
            "receipt_id": str(capital_event_internal_prime.get("receipt_id") or ""),
            "capital_commit_id": str(capital_commit_id_from_payload(prime_event_payload) or ""),
        },
        append_reason=append_reason,
    )

    lineage_anchor_commit_id = (
        capital_commit_id_from_payload(receipt_event_payload)
        or capital_commit_id_from_payload(ledger_event_payload)
        or capital_commit_id_from_payload(bankroll_event_payload)
        or capital_commit_id_from_payload(treasury_event_payload)
        or capital_commit_id_from_payload(prime_event_payload)
    )

    return CapitalTruthSourceSnapshotBundle(
        sources=sources,
        family_targets=family_targets,
        family_allocations_wei=family_allocations_wei,
        receipt_last_ts_ms=int(receipt_last_ts_ms or 0),
        receipt_outcome_ts_ms=int(receipt_outcome_updated_ts_ms or 0),
        ledger_event_ts_ms=int(ledger_event_ts_ms or 0),
        receipt_event_ts_ms=int(receipt_event_ts_ms or 0),
        bankroll_history_payload=bankroll_history_payload,
        treasury_history_payload=treasury_history_payload,
        internal_prime_history_payload=internal_prime_history_payload,
        bankroll_event_payload=bankroll_event_payload,
        bankroll_event_state=bankroll_event_state,
        treasury_event_payload=treasury_event_payload,
        treasury_event_capital_engine=treasury_event_capital_engine,
        ledger_event_payload=ledger_event_payload,
        receipt_event_payload=receipt_event_payload,
        prime_event_payload=prime_event_payload,
        lineage_anchor_commit_id=str(lineage_anchor_commit_id or ""),
    )
