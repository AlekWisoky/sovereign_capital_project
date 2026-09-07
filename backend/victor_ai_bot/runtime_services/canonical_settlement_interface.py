from __future__ import annotations

from typing import Any, Mapping

_SETTLEMENT_TX_TYPE = "receipt_settlement"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _chain_name(runtime: Any) -> str:
    return _text(getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", ""))


def _transactions(runtime: Any) -> list[dict[str, Any]]:
    repo = getattr(runtime, "_ledger_repo", None)
    if repo is None:
        return []
    try:
        if callable(getattr(repo, "all_transactions", None)):
            rows = repo.all_transactions(chain=_chain_name(runtime))
        elif callable(getattr(repo, "transactions_tail", None)):
            rows = repo.transactions_tail(chain=_chain_name(runtime), limit=5000)
        else:
            return []
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def _normalize(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _dict(row.get("metadata"))
    lineage = _dict(metadata.get("canonical_lineage"))

    def first(*keys: str, default: Any = None) -> Any:
        for key in keys:
            if metadata.get(key) not in (None, ""):
                return metadata[key]
        return default

    return {
        "status": "settled",
        "source": "phase2_canonical_outcome_ledger",
        "transaction_id": _text(row.get("transaction_id")),
        "tx_hash": _text(row.get("receipt_id") or metadata.get("tx_hash") or metadata.get("txHash")),
        "decision_id": _text(first("canonical_decision_id", "decision_id", default=lineage.get("decision_id"))),
        "correlation_id": _text(first("correlation_id", default=lineage.get("correlation_id"))),
        "execution_id": _text(first("execution_id", default=lineage.get("execution_id"))),
        "outcome_id": _text(first("outcome_id", default=lineage.get("outcome_id"))),
        "sizing_id": _text(first("sizing_id", default=lineage.get("sizing_id"))),
        "opportunity_id": _text(first("opportunity_id", "opportunityId")),
        "route_id": _text(first("route_id", "routeId")),
        "action": _text(first("action", "aqe_action", default=lineage.get("action"))),
        "strategy_family": _text(first("strategy_family", "strategyFamily", "family")),
        "ok": bool(first("ok", default=True)),
        "expected_net_usd": float(first("expected_net_usd", "expectedNetUsd", default=0.0) or 0.0),
        "realized_net_usd": float(first("realized_net_usd", "realizedNetUsd", default=0.0) or 0.0),
        "amount_in_wei": int(first("amount_in_wei", "amountInWei", default=0) or 0),
        "gas_cost_usd": float(first("gas_cost_usd", "gasCostUsd", default=0.0) or 0.0),
        "slippage_bps": float(first("slippage_bps", "slippageBps", default=0.0) or 0.0),
        "latency_ms": int(first("latency_ms", "latencyMs", default=0) or 0),
        "truth_verified": bool(first("truth_verified", "outcome_truth_verified", "verified", default=False)),
        "metadata": metadata,
        "ledger_transaction": dict(row),
    }


def canonical_settled_outcome(
    runtime: Any,
    *,
    tx_hash: str = "",
    decision_id: str = "",
    correlation_id: str = "",
    opportunity_id: str = "",
) -> dict[str, Any] | None:
    """Read one exact canonical settled outcome from the physical ledger."""
    rows = [row for row in _transactions(runtime) if _text(row.get("tx_type")) == _SETTLEMENT_TX_TYPE]
    matches = []
    for row in rows:
        normalized = _normalize(row)
        if tx_hash and normalized["tx_hash"] != _text(tx_hash):
            continue
        if decision_id and normalized["decision_id"] != _text(decision_id):
            continue
        if correlation_id and normalized["correlation_id"] != _text(correlation_id):
            continue
        if opportunity_id and normalized["opportunity_id"] != _text(opportunity_id):
            continue
        matches.append(normalized)
    if not matches:
        return None
    matches.sort(key=lambda item: int(item["ledger_transaction"].get("ts_ms") or 0), reverse=True)
    return matches[0]


__all__ = ["canonical_settled_outcome"]
