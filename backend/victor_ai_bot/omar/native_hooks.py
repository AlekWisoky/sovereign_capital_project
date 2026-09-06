from __future__ import annotations

from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity
from ..sentry_config import set_sentry_trade_context

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def decision_hook(runtime: Any, opp: Any, decision: Any | None, *, current_block: int) -> None:
    """Native decision-boundary hook; identity is established independently of OMAR."""
    try:
        chain = getattr(getattr(runtime, "cfg", None), "chain", None)
        identity = ensure_decision_identity(
            opp,
            decision,
            chain_name=_text(getattr(chain, "name", "chain")) or "chain",
            current_block=int(current_block),
        )
        set_sentry_trade_context(
            decision_id=identity.decision_id,
            correlation_id=identity.correlation_id,
            opportunity_id=_text(getattr(opp, "id", "")),
            route_id=_text(getattr(opp, "route_id", "")),
            action=_text(getattr(decision, "action", "")),
            mode=_text(getattr(getattr(runtime, "cfg", None), "execution", None).brain_mode),
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
        plan["opportunity_id"] = lineage["opportunity_id"]
        plan["route_id"] = lineage["route_id"]
        plan["action"] = lineage["action"]
        plan["latency_ms"] = int(latency_ms)
        plan["execution_mode"] = str(mode or "auto")
        try:
            result.plan = plan
        except _SAFE:
            pass
        set_sentry_trade_context(
            decision_id=lineage["decision_id"],
            correlation_id=lineage["correlation_id"],
            execution_id=_text(plan.get("execution_id")),
            opportunity_id=lineage["opportunity_id"],
            route_id=lineage["route_id"],
            action=lineage["action"],
            mode=str(mode or "auto"),
        )
    except _SAFE:
        return


def settlement_hook(runtime: Any, opp: Any, outcome: Mapping[str, Any] | None) -> None:
    """Feed OMAR only an exact, verified canonical settled outcome."""
    try:
        row = _dict(outcome)
        if _text(row.get("status")).lower() != "settled":
            return
        if _text(row.get("source")) != "phase2_canonical_outcome_ledger":
            return
        if not bool(row.get("truth_verified", False)):
            return

        lineage = lineage_from_opportunity(opp)
        decision_id = lineage["decision_id"]
        correlation_id = lineage["correlation_id"]
        opportunity_id = lineage["opportunity_id"]
        route_id = lineage["route_id"]
        action = lineage["action"]
        if not all((decision_id, correlation_id, opportunity_id, route_id, action)):
            return

        if _text(row.get("decision_id")) != decision_id:
            return
        if _text(row.get("correlation_id")) != correlation_id:
            return
        if _text(row.get("opportunity_id")) != opportunity_id:
            return
        if _text(row.get("route_id")) != route_id:
            return
        if _text(row.get("action")) != action:
            return

        omar = getattr(runtime, "_omar", None)
        if omar is None or not bool(getattr(omar, "enabled", False)):
            return
        set_sentry_trade_context(
            decision_id=decision_id,
            correlation_id=correlation_id,
            outcome_id=_text(row.get("transaction_id")),
            opportunity_id=opportunity_id,
            route_id=route_id,
            action=action,
            mode="settled",
        )
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
            route_id=route_id,
            tx_hash=_text(row.get("tx_hash") or row.get("txHash")),
            outcome_truth_verified=True,
            metadata={
                "canonical_lineage": {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                    "opportunity_id": opportunity_id,
                    "route_id": route_id,
                    "action": action,
                },
                "source": "phase2_canonical_outcome_ledger",
                "settlement": dict(row),
            },
        )
    except _SAFE:
        return
