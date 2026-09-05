from __future__ import annotations

from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def decision_hook(runtime: Any, opp: Any, decision: Any | None, *, current_block: int) -> None:
    """Native decision-boundary hook; identity is established independently of OMAR."""
    try:
        chain = getattr(getattr(runtime, "cfg", None), "chain", None)
        ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(getattr(chain, "name", "chain")) or "chain",
            current_block=int(current_block),
        )
    except _SAFE:
        return


def execution_hook(
    runtime: Any,
    opp: Any,
    decision: Any | None,
    result: Any,
    *,
    bn: int,
    latency_ms: int,
    mode: str,
) -> None:
    """Native execution-boundary hook; copies canonical identity onto the execution result."""
    try:
        decision_hook(runtime, opp, decision, current_block=int(bn))
        lineage = lineage_from_opportunity(opp)
        plan = _dict(getattr(result, "plan", None))
        plan["canonical_lineage"] = dict(lineage)
        plan["canonical_decision_id"] = lineage["decision_id"]
        plan["correlation_id"] = lineage["correlation_id"]
        plan["latency_ms"] = int(latency_ms)
        plan["execution_mode"] = str(mode or "auto")
        try:
            result.plan = plan
        except _SAFE:
            pass
    except _SAFE:
        return


def settlement_hook(runtime: Any, opp: Any, outcome: Mapping[str, Any] | None) -> None:
    """Native settlement-boundary hook; feed only a canonical settled outcome to OMAR."""
    try:
        row = _dict(outcome)
        if _text(row.get("status")).lower() != "settled":
            return
        lineage = lineage_from_opportunity(opp)
        decision_id = lineage["decision_id"]
        correlation_id = lineage["correlation_id"]
        if not decision_id or not correlation_id:
            return
        if _text(row.get("decision_id")) not in {"", decision_id}:
            return
        if _text(row.get("correlation_id")) not in {"", correlation_id}:
            return
        omar = getattr(runtime, "_omar", None)
        if omar is None or not bool(getattr(omar, "enabled", False)):
            return
        omar.observe_outcome(
            decision_id=decision_id,
            ok=bool(row.get("ok", True)),
            realized_net_usd=float(
                row.get("realized_net_usd", row.get("realizedNetUsd", 0.0)) or 0.0
            ),
            expected_net_usd=float(
                row.get("expected_net_usd", row.get("expectedNetUsd", 0.0)) or 0.0
            ),
            amount_in_wei=int(row.get("amount_in_wei", row.get("amountInWei", 0)) or 0),
            gas_cost_usd=float(row.get("gas_cost_usd", row.get("gasCostUsd", 0.0)) or 0.0),
            slippage_bps=float(row.get("slippage_bps", row.get("slippageBps", 0.0)) or 0.0),
            latency_ms=int(row.get("latency_ms", row.get("latencyMs", 0)) or 0),
            route_id=_text(row.get("route_id") or getattr(opp, "route_id", "")),
            tx_hash=_text(row.get("tx_hash") or row.get("txHash")),
            outcome_truth_verified=bool(
                row.get("truth_verified", row.get("outcome_truth_verified", True))
            ),
            metadata={
                "canonical_lineage": {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                },
                "source": "canonical_outcome_ledger",
                "settlement": dict(row),
            },
        )
    except _SAFE:
        return
