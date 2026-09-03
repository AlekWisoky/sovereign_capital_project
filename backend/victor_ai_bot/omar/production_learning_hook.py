from __future__ import annotations

from typing import Any, Mapping

from ..identity import identity_from

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _operator_intent(value: Any) -> Any:
    try:
        from .operator_intent import OperatorIntentSnapshot

        return value if isinstance(value, OperatorIntentSnapshot) else None
    except _SAFE:
        return None


def _decision_state(opp: Any, decision: Any) -> dict[str, Any]:
    metadata = _mapping(getattr(decision, "metadata", None))
    brain = _mapping(_mapping(getattr(opp, "meta", None)).get("brain"))
    state = _mapping(metadata.get("learning_state"))
    if not state:
        state = _mapping(metadata.get("state"))
    if not state:
        state = _mapping(brain.get("learning_state"))
    if "rl_state" not in state:
        rl_state = _text(metadata.get("rl_state") or brain.get("rl_state"))
        if rl_state:
            state["rl_state"] = rl_state
    return state


def _pending_identity(pending: Mapping[str, Any]) -> Any:
    direct = identity_from(pending)
    if direct is not None and direct.decision_id and direct.correlation_id:
        return direct
    lineage = _mapping(pending.get("canonical_lineage"))
    brain = _mapping(pending.get("brain"))
    return identity_from(
        {
            "identity": {
                "decision_id": _text(
                    pending.get("canonical_decision_id")
                    or lineage.get("decision_id")
                    or brain.get("canonical_decision_id")
                ),
                "correlation_id": _text(
                    pending.get("correlation_id")
                    or lineage.get("correlation_id")
                    or brain.get("correlation_id")
                ),
                "execution_id": _text(pending.get("execution_id") or lineage.get("execution_id")),
                "settlement_id": _text(pending.get("settlement_id") or lineage.get("settlement_id")),
            }
        }
    )


def _install_decision_hook() -> None:
    from ..runtime_services.runtime_decision_facade import RuntimeDecisionFacade

    original = getattr(RuntimeDecisionFacade, "_apply_omar_to_candidate", None)
    if original is None or getattr(original, "_omar_real_learning_hook", False):
        return

    def wrapped(self: Any, opp: Any, decision: Any, current_block: int):
        chosen, selected = original(self, opp, decision, current_block=current_block)
        try:
            from .integration import active_omar_runtime

            omar = active_omar_runtime()
            if omar is not None and bool(getattr(omar.cfg, "enabled", False)):
                omar.bind_runtime(self)
                identity = identity_from(selected)
                if identity is not None and identity.decision_id and identity.correlation_id:
                    meta = _mapping(getattr(selected, "metadata", None))
                    intent = _operator_intent(
                        meta.get("operator_intent_snapshot") or meta.get("operator_intent")
                    )
                    omar.observe_decision(
                        decision_id=identity.decision_id,
                        correlation_id=identity.correlation_id,
                        action=_text(getattr(selected, "action", "trade")) or "trade",
                        opp_id=_text(getattr(opp, "id", "")),
                        route_id=_text(getattr(opp, "route_id", "")),
                        policy_version=_text(meta.get("policy_version")),
                        state=_decision_state(opp, selected),
                        operator_intent=intent,
                        metadata={
                            "source": "production_runtime_decision_boundary",
                            "current_block": int(current_block),
                        },
                    )
        except _SAFE:
            pass
        return chosen, selected

    wrapped._omar_real_learning_hook = True
    wrapped._omar_real_learning_original = original
    RuntimeDecisionFacade._apply_omar_to_candidate = wrapped


def _install_execution_hook() -> None:
    from ..runtime_services.execution_service import ExecutionService

    original = getattr(ExecutionService, "handle_post_execute_bookkeeping", None)
    if original is None or getattr(original, "_omar_real_learning_hook", False):
        return

    async def wrapped(
        self: Any,
        runtime: Any,
        opp: Any,
        result: Any,
        *,
        bn: int,
        latency_ms: int,
        mode: str,
    ) -> None:
        await original(
            self,
            runtime,
            opp,
            result,
            bn=bn,
            latency_ms=latency_ms,
            mode=mode,
        )
        try:
            from .integration import active_omar_runtime

            omar = active_omar_runtime()
            if omar is None or not bool(getattr(omar.cfg, "enabled", False)):
                return
            identity = identity_from(result)
            if identity is None or not identity.complete_for_execution:
                return
            plan = _mapping(getattr(result, "plan", None))
            decision = getattr(result, "decision", None)
            action = _text(getattr(decision, "action", "")) or _text(plan.get("action")) or "trade"
            omar.observe_execution(
                decision_id=identity.decision_id,
                correlation_id=identity.correlation_id,
                execution_id=identity.execution_id,
                status="submitted" if bool(getattr(result, "submitted", False)) else "executed",
                action=action,
                tx_hash=_text(getattr(result, "tx_hash", "")),
                slippage_bps=float(plan.get("slippage_bps") or 0.0),
                gas_wei=int(plan.get("gas_cost_wei") or 0),
                latency_ms=float(latency_ms),
                metadata={
                    "source": "production_runtime_execution_boundary",
                    "block_number": int(bn),
                    "mode": _text(mode),
                    "ok": bool(getattr(result, "ok", False)),
                },
            )
        except _SAFE:
            return

    wrapped._omar_real_learning_hook = True
    wrapped._omar_real_learning_original = original
    ExecutionService.handle_post_execute_bookkeeping = wrapped


def _install_settlement_hook() -> None:
    from ..runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", None)
    if original is None or getattr(original, "_omar_real_learning_hook", False):
        return

    def wrapped(
        self: Any,
        service: Any,
        *,
        tx_hash: str,
        receipt: Any,
        decoded: Any,
        pending: dict,
        status: int,
        submit_to_receipt_ms: int,
        expected_after: int,
        realized_after: int,
        amount_in: int,
        gas_est_wei: int,
        route_id: str,
        reward_trace: dict,
        capture_lane_pending: str,
        capture_relay_pending: str,
        outcome_truth: dict,
    ) -> None:
        original(
            self,
            service,
            tx_hash=tx_hash,
            receipt=receipt,
            decoded=decoded,
            pending=pending,
            status=status,
            submit_to_receipt_ms=submit_to_receipt_ms,
            expected_after=expected_after,
            amount_in=amount_in,
            gas_est_wei=gas_est_wei,
            route_id=route_id,
            reward_trace=reward_trace,
            capture_lane_pending=capture_lane_pending,
            capture_relay_pending=capture_relay_pending,
            outcome_truth=outcome_truth,
            realized_after=realized_after,
        )
        try:
            from .integration import active_omar_runtime

            omar = active_omar_runtime()
            if omar is None or not bool(getattr(omar.cfg, "enabled", False)):
                return
            if int(status) != 1 or not bool((outcome_truth or {}).get("ok", True)):
                return
            reader = getattr(self, "canonical_settled_outcome", None)
            if not callable(reader):
                return
            identity = _pending_identity(pending)
            if identity is None or not identity.decision_id or not identity.correlation_id:
                return
            row = reader(
                tx_hash=str(tx_hash),
                decision_id=identity.decision_id,
                correlation_id=identity.correlation_id,
                opportunity_id=_text(pending.get("opportunity_id")),
            )
            if not isinstance(row, dict):
                return
            omar.observe_settled_ledger_record(row)
        except _SAFE:
            return

    wrapped._omar_real_learning_hook = True
    wrapped._omar_real_learning_original = original
    RuntimeReceiptFacade._safe_finalize_receipt_side_effects = wrapped


def install_production_learning_hooks() -> None:
    """Install canonical decision, execution, and settled-learning callbacks once."""
    _install_decision_hook()
    _install_execution_hook()
    _install_settlement_hook()
