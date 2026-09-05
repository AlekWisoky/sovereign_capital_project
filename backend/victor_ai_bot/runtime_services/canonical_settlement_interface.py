from __future__ import annotations

from typing import Any, Mapping

from ..capital_demand import capital_demand_from_mapping


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
    chain = _chain_name(runtime)
    try:
        if callable(getattr(repo, "all_transactions", None)):
            rows = repo.all_transactions(chain=chain)
        elif callable(getattr(repo, "transactions_tail", None)):
            rows = repo.transactions_tail(chain=chain, limit=5000)
        else:
            return []
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return []
    return [dict(row) for row in list(rows or []) if isinstance(row, Mapping)]


def _matches(
    row: Mapping[str, Any],
    *,
    tx_hash: str,
    decision_id: str,
    correlation_id: str,
    opportunity_id: str,
    execution_id: str,
) -> bool:
    if _text(row.get("tx_type")) != _SETTLEMENT_TX_TYPE:
        return False

    metadata = _dict(row.get("metadata"))
    candidates = {
        _text(row.get("receipt_id")),
        _text(metadata.get("tx_hash")),
        _text(metadata.get("txHash")),
        _text(metadata.get("receipt_id")),
        _text(metadata.get("receiptId")),
    }
    candidates.discard("")

    lineage = _dict(metadata.get("canonical_lineage"))
    execution_lineage = _dict(metadata.get("execution_lineage"))
    decision_candidates = {
        _text(metadata.get("canonical_decision_id")),
        _text(metadata.get("decision_id")),
        _text(lineage.get("decision_id")),
        _text(execution_lineage.get("decision_id")),
    }
    correlation_candidates = {
        _text(metadata.get("correlation_id")),
        _text(lineage.get("correlation_id")),
        _text(execution_lineage.get("correlation_id")),
    }
    execution_candidates = {
        _text(metadata.get("execution_id")),
        _text(execution_lineage.get("execution_id")),
    }
    opportunity_candidates = {
        _text(metadata.get("opportunity_id")),
        _text(metadata.get("opportunityId")),
    }

    # When an execution ID is supplied, it is an exact lineage constraint.
    # A matching transaction hash must never override a mismatched execution
    # attempt; this prevents a retry/replacement from learning the wrong fill.
    if execution_id and execution_id not in execution_candidates:
        return False
    if tx_hash and tx_hash in candidates:
        return True
    return bool(
        (decision_id and decision_id in decision_candidates)
        or (correlation_id and correlation_id in correlation_candidates)
        or (opportunity_id and opportunity_id in opportunity_candidates)
    )


def _normalize(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _dict(row.get("metadata"))
    profitability = _dict(
        metadata.get("terminalProfitability") or metadata.get("terminal_profitability")
    )
    chain = _dict(metadata.get("profitabilityChain") or metadata.get("profitability_chain"))
    capital_admission = _dict(metadata.get("capitalAdmission") or metadata.get("capital_admission"))
    capital_authority = _dict(metadata.get("capitalAuthority") or metadata.get("capital_authority"))
    internal_prime_authority = _dict(
        metadata.get("internalPrimeAuthority") or metadata.get("internal_prime_authority")
    )
    lineage = _dict(metadata.get("canonical_lineage"))
    execution_lineage = _dict(metadata.get("execution_lineage"))
    capital_demand = capital_demand_from_mapping(
        metadata.get("capitalDemand") or metadata.get("capital_demand") or metadata
    ).to_dict()

    def first(*keys: str, default: Any = None) -> Any:
        for source in (metadata, profitability, chain, row):
            for key in keys:
                value = source.get(key)
                if value is not None and value != "":
                    return value
        return default

    return {
        "status": "settled",
        "source": "phase2_canonical_outcome_ledger",
        "settlement_status": "settled",
        "transaction_id": _text(row.get("transaction_id")),
        "tx_hash": _text(
            row.get("receipt_id") or metadata.get("tx_hash") or metadata.get("txHash")
        ),
        "settled_at_ms": int(row.get("ts_ms") or 0),
        "decision_id": _text(
            first("canonical_decision_id", "decision_id", default=lineage.get("decision_id"))
        ),
        "correlation_id": _text(first("correlation_id", default=lineage.get("correlation_id"))),
        "execution_id": _text(first("execution_id", default=execution_lineage.get("execution_id"))),
        "opportunity_id": _text(first("opportunity_id", "opportunityId")),
        "route_id": _text(first("route_id", "routeId")),
        "strategy_family": _text(first("strategy_family", "strategyFamily", "family")),
        "ok": bool(first("ok", default=True)),
        "expected_net_usd": float(first("expected_net_usd", "expectedNetUsd", default=0.0) or 0.0),
        "realized_net_usd": float(first("realized_net_usd", "realizedNetUsd", default=0.0) or 0.0),
        "amount_in_wei": int(first("amount_in_wei", "amountInWei", default=0) or 0),
        "gas_cost_usd": float(first("gas_cost_usd", "gasCostUsd", default=0.0) or 0.0),
        "slippage_bps": float(first("slippage_bps", "slippageBps", default=0.0) or 0.0),
        "latency_ms": int(first("latency_ms", "latencyMs", default=0) or 0),
        "truth_verified": bool(
            first("truth_verified", "outcome_truth_verified", "verified", default=True)
        ),
        "outcome_truth_reason_code": _text(
            first("outcome_truth_reason_code", "truth_reason_code", default="ok")
        ),
        "terminal_profitability": profitability,
        "profitability_chain": chain,
        "capital_admission": capital_admission,
        "capital_demand": capital_demand,
        "capital_authority": capital_authority,
        "internal_prime_authority": internal_prime_authority,
        "canonical_lineage": {
            "decision_id": _text(
                lineage.get("decision_id") or execution_lineage.get("decision_id")
            ),
            "correlation_id": _text(
                lineage.get("correlation_id") or execution_lineage.get("correlation_id")
            ),
            "execution_id": _text(
                execution_lineage.get("execution_id") or metadata.get("execution_id")
            ),
        },
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
    execution_id: str = "",
) -> dict[str, Any] | None:
    """Return the exact settled outcome recorded by the Phase 2 ledger."""
    rows = _transactions(runtime)
    matches = [
        row
        for row in rows
        if _matches(
            row,
            tx_hash=_text(tx_hash),
            decision_id=_text(decision_id),
            correlation_id=_text(correlation_id),
            opportunity_id=_text(opportunity_id),
            execution_id=_text(execution_id),
        )
    ]
    if not matches:
        return None
    matches.sort(key=lambda row: int(row.get("ts_ms") or 0), reverse=True)
    return _normalize(matches[0])


def install_canonical_settlement_interface() -> None:
    """Install one stable runtime read surface without replacing the ledger."""
    from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    existing = getattr(RuntimeReceiptFacade, "canonical_settled_outcome", None)
    if existing is not None and getattr(existing, "_phase2_canonical_interface", False):
        return

    def runtime_canonical_settled_outcome(
        self: Any,
        *,
        tx_hash: str = "",
        decision_id: str = "",
        correlation_id: str = "",
        opportunity_id: str = "",
        execution_id: str = "",
    ) -> dict[str, Any] | None:
        return canonical_settled_outcome(
            self,
            tx_hash=tx_hash,
            decision_id=decision_id,
            correlation_id=correlation_id,
            opportunity_id=opportunity_id,
            execution_id=execution_id,
        )

    runtime_canonical_settled_outcome._phase2_canonical_interface = True
    RuntimeReceiptFacade.canonical_settled_outcome = runtime_canonical_settled_outcome


def install_canonical_settlement_bridge() -> None:
    """Make the Phase 4 lifecycle bridge consume the stable runtime surface."""
    from victor_ai_bot.omar import lifecycle_bridge

    def bridge_settled_outcome(runtime: Any, result: Any, opp: Any) -> dict[str, Any] | None:
        meta = _dict(getattr(opp, "meta", None))
        brain = _dict(meta.get("brain"))
        execution_lineage = _dict(meta.get("execution_lineage"))
        plan = _dict(getattr(result, "plan", None))
        return runtime.canonical_settled_outcome(
            tx_hash=_text(getattr(result, "tx_hash", "")),
            decision_id=_text(brain.get("canonical_decision_id") or brain.get("omar_decision_id")),
            correlation_id=_text(brain.get("correlation_id")),
            opportunity_id=_text(getattr(opp, "id", "")),
            execution_id=_text(
                plan.get("execution_id")
                or execution_lineage.get("execution_id")
                or brain.get("execution_id")
            ),
        )

    lifecycle_bridge._canonical_settled_outcome = bridge_settled_outcome
