from __future__ import annotations

"""Read-only global opportunity selection across configured runtime bundles.

This module deliberately stops at selection evidence. It does not switch the
active chain, enable auto-trading, size an order, mutate an opportunity, or
submit a transaction.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from ..profitability_state import profitability_state_view
from .profitability_truth import inspect_profit_after_costs_truth
from .route_runtime_truth import execution_route_truth


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _nested(mapping: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _bool(mapping: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in mapping:
            return bool(mapping.get(key))
    return None


def _number(
    mapping: Mapping[str, Any], *keys: str, as_int: bool = False
) -> float | int | None:
    for key in keys:
        if key not in mapping or mapping.get(key) in (None, ""):
            continue
        try:
            value = int(str(mapping.get(key))) if as_int else float(mapping.get(key))
        except (TypeError, ValueError):
            continue
        return value
    return None


def _first_nested(mapping: Mapping[str, Any], *parents: str) -> dict[str, Any]:
    for parent in parents:
        value = mapping.get(parent)
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _profitability_blocking_reason(
    truth: Any, after_fee_usd_micro: int | None
) -> str:
    if not truth.verified:
        return str(truth.reason_code)
    if not truth.positive:
        return str(truth.reason_code)
    if after_fee_usd_micro is None:
        return "cross_runtime_usd_profit_unavailable"
    if after_fee_usd_micro <= 0:
        return "profit_after_costs_usd_not_positive"
    return ""


def _execution_blocking_reason(state: Mapping[str, Any]) -> str:
    liquidity_capacity = state.get("liquidity_capacity")
    required_notional = state.get("required_notional")
    if not state.get("route_ready"):
        return str(state.get("route_reason") or "execution_route_not_ready")
    if state.get("route_degraded"):
        return "execution_route_runtime_degraded"
    if (
        liquidity_capacity is not None
        and required_notional is not None
        and liquidity_capacity < required_notional
    ):
        return "insufficient_liquidity_capacity"
    if not state.get("sizing_available"):
        return "sizing_unavailable"
    if not state.get("capital_authority"):
        return "capital_authority_unavailable"
    if not state.get("flashloan_eligible"):
        return "flashloan_ineligible"
    return ""


def _governance_blocking_reason(state: Mapping[str, Any]) -> str:
    if not state.get("admission_allowed"):
        return str(state.get("admission_reason") or "capital_admission_blocked")
    if not state.get("gate_allowed"):
        return str(state.get("gate_reason") or "auto_trade_gate_unavailable")
    if not state.get("recovery_ready"):
        return str(state.get("recovery_reason") or "auto_trade_recovery_blocked")
    if not state.get("execution_ready"):
        return str(state.get("execution_reason") or "execution_not_ready")
    return ""


@dataclass(frozen=True)
class RuntimeOpportunityEvidence:
    runtime: str
    candidate_count: int
    opportunity_id: str
    route_id: str
    strategy: str
    after_fee_verified: bool
    after_fee_positive: bool
    after_fee_usd_micro: int | None
    after_fee_wei: int
    canonical_profitability: bool
    projected_profit_usd: float | None
    route_ready: bool
    route_degraded: bool
    route_reason_code: str
    liquidity_capacity_usd: float | None
    required_notional_usd: float | None
    provider: str
    provider_capacity_usd: float | None
    sizing_available: bool
    size_multiplier: float | None
    borrow_multiplier: float | None
    capital_authority_available: bool
    flashloan_eligible: bool
    admission_allowed: bool
    gate_allowed: bool
    gate_reason_code: str
    recovery_ready: bool
    execution_ready: bool
    execution_block_reason: str
    eligible: bool
    blocking_reason: str
    selection_score: tuple[int, int, int, int, int, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime": self.runtime,
            "candidate_count": self.candidate_count,
            "opportunity_id": self.opportunity_id,
            "route_id": self.route_id,
            "strategy": self.strategy,
            "after_fee": {
                "verified": self.after_fee_verified,
                "positive": self.after_fee_positive,
                "usd_micro": self.after_fee_usd_micro,
                "wei": str(self.after_fee_wei),
                "canonical": self.canonical_profitability,
                "projected_profit_usd": self.projected_profit_usd,
            },
            "liquidity": {
                "capacity_usd": self.liquidity_capacity_usd,
                "required_notional_usd": self.required_notional_usd,
            },
            "provider": {
                "selected": self.provider,
                "capacity_usd": self.provider_capacity_usd,
            },
            "sizing": {
                "available": self.sizing_available,
                "size_multiplier": self.size_multiplier,
                "borrow_multiplier": self.borrow_multiplier,
            },
            "capital_authority_available": self.capital_authority_available,
            "flashloan_eligible": self.flashloan_eligible,
            "admission": {
                "allowed": self.admission_allowed,
                "gate_allowed": self.gate_allowed,
                "reason_code": self.gate_reason_code,
                "recovery_ready": self.recovery_ready,
            },
            "execution": {
                "ready": self.execution_ready,
                "route_ready": self.route_ready,
                "route_degraded": self.route_degraded,
                "reason_code": self.execution_block_reason,
            },
            "eligible": self.eligible,
            "blocking_reason": self.blocking_reason,
            "selection_score": list(self.selection_score[:-1]) + [self.selection_score[-1]],
        }


class MultiRuntimeOpportunitySelector:
    """Select the best *eligible* candidate across all runtime bundles.

    The selector compares explicit USD after-fee truth across runtimes. Raw
    wei/native units are retained as evidence but never used as the global
    profitability comparator.
    """

    def _candidate_evidence(
        self,
        runtime_name: str,
        candidate_count: int,
        candidate: Any,
        summary: Mapping[str, Any],
    ) -> RuntimeOpportunityEvidence:
        meta = _mapping(getattr(candidate, "meta", None))
        profitability = profitability_state_view(candidate)
        truth = inspect_profit_after_costs_truth(candidate)
        route = execution_route_truth(meta)

        gate = _first_nested(summary, "auto_trade_gate", "autoTradeGate")
        recovery = _first_nested(summary, "auto_trade_recovery", "autoTradeRecovery")
        admission = _first_nested(
            meta,
            "capitalAdmission",
            "capital_admission",
            "admission",
        )
        admission_details = _nested(admission, "details")
        sizing = _first_nested(
            admission_details,
            "institutionalSizing",
            "institutional_sizing",
        )
        sizing_body = _first_nested(sizing, "sizing", "result")
        capture = _first_nested(
            meta,
            "execution_capture",
            "executionCapture",
            "capture",
            "execution",
        )
        liquidity = _first_nested(
            capture,
            "liquidity",
            "liquidity_context",
        )
        if not liquidity:
            liquidity = _first_nested(meta, "liquidity", "liquidity_context")

        provider = str(
            capture.get("selectedProvider")
            or capture.get("selected_provider")
            or meta.get("selectedProvider")
            or meta.get("selected_provider")
            or ""
        )
        provider_capacity = _number(
            capture,
            "provider_capacity_usd",
            "providerCapacityUsd",
        )
        if provider_capacity is None:
            provider_capacity = _float(liquidity, "provider_capacity_usd", "providerCapacityUsd")

        route_capacity = _float(
            capture,
            "route_capacity_usd",
            "routeCapacityUsd",
            "executable_depth_usd",
            "executableDepthUsd",
        )
        liquidity_capacity = _float(
            liquidity,
            "available_usd",
            "availableUsd",
            "depth_usd",
            "depthUsd",
            "pool_depth_cap_usd",
            "poolDepthCapUsd",
        )
        capacities = [
            x for x in (route_capacity, provider_capacity, liquidity_capacity) if x is not None
        ]
        if capacities:
            liquidity_capacity = min(capacities)

        required_notional = _float(
            sizing_body,
            "requested_notional_usd",
            "requestedNotionalUsd",
            "target_notional_usd",
            "targetNotionalUsd",
        )
        if required_notional is None:
            required_notional = _float(
                admission_details,
                "capital_required_usd",
                "capitalRequiredUsd",
                "requested_notional_usd",
                "requestedNotionalUsd",
            )
        if required_notional is None:
            required_notional = _float(
                capture,
                "capital_required_usd",
                "capitalRequiredUsd",
            )

        sizing_available = _bool(
            sizing_body,
            "execution_allowed",
            "executionAllowed",
            "valid",
            "available",
        )
        if sizing_available is None:
            sizing_available = _bool(admission_details, "sizing_available", "sizingAvailable")
        if sizing_available is None:
            sizing_available = bool(sizing_body)

        capital_authority = _bool(
            sizing_body,
            "capital_authority_available",
            "capitalAuthorityAvailable",
        )
        if capital_authority is None:
            capital = _first_nested(sizing_body, "capital", "capital_authority")
            capital_authority = (
                str(capital.get("status") or "").lower() == "ok"
                and str(capital.get("freshness") or capital.get("freshness_class") or "").lower()
                not in {"stale", "unavailable"}
            )
        if capital_authority is None:
            capital_authority = _bool(
                admission_details,
                "capital_authority_available",
                "capitalAuthorityAvailable",
            )

        admission_for_flashloan = _first_nested(
            meta, "capitalAdmission", "capital_admission", "admission"
        )
        admission_flashloan_details = _nested(admission_for_flashloan, "details")
        flashloan = {}
        for key in (
            "flashloanSizing",
            "flashloan_sizing",
            "flashloan",
            "flashloanEligibility",
            "flashloan_eligibility",
        ):
            value = admission_flashloan_details.get(key)
            if isinstance(value, Mapping):
                flashloan = dict(value)
                break
        flashloan_eligible = _bool(
            flashloan,
            "eligible",
            "allowed",
            "execution_allowed",
            "executionAllowed",
        )
        if flashloan_eligible is None:
            flashloan_eligible = _bool(
                meta,
                "flashloan_eligible",
                "flashloanEligible",
            )
        if flashloan_eligible is None:
            # Flash loans are optional for strategies that do not declare one.
            # An explicitly declared eligibility value is authoritative.
            flashloan_eligible = True

        route_ready = bool(route.get("ready", False))
        route_degraded = bool(route.get("runtime_degraded", False))
        route_reason = str(route.get("reason") or route.get("runtime_reason") or "ok")

        execution_ready = _bool(
            capture,
            "execution_ready",
            "executionReady",
            "exec_ready",
        )
        if execution_ready is None:
            execution_ready = _bool(meta, "execution_ready", "executionReady", "exec_ready")
        if execution_ready is None:
            execution_ready = bool(getattr(candidate, "can_execute", False))

        execution_block_reason = str(
            capture.get("reason_code")
            or capture.get("reason")
            or meta.get("execution_reason_code")
            or ""
        )

        candidate_gate = _first_nested(meta, "auto_trade_gate", "autoTradeGate")
        candidate_recovery = _first_nested(
            meta, "auto_trade_recovery", "autoTradeRecovery"
        )
        gate_allowed = bool(gate.get("allowed", False)) and (
            not candidate_gate or bool(candidate_gate.get("allowed", False))
        )
        gate_reason = str(
            candidate_gate.get("reason_code")
            or candidate_gate.get("reason")
            or gate.get("reason_code")
            or gate.get("reason")
            or "auto_trade_gate_unavailable"
        )
        recovery_ready = (
            bool(recovery.get("ready", False))
            and not bool(recovery.get("blocked", False))
            and (
                not candidate_recovery
                or (
                    bool(candidate_recovery.get("ready", False))
                    and not bool(candidate_recovery.get("blocked", False))
                )
            )
        )
        admission_allowed = _bool(
            admission,
            "allowed",
            "admitted",
            "execution_allowed",
            "executionAllowed",
        )
        if admission_allowed is None:
            admission_allowed = gate_allowed

        after_fee_usd_micro = _number(
            profitability,
            "profitAfterCostsUsdMicroInt",
            as_int=True,
        )
        projected_profit_usd = _float(
            profitability,
            "expectedProfitUsd",
        )

        blocking_state = {
            "route_ready": route_ready,
            "route_degraded": route_degraded,
            "route_reason": route_reason,
            "liquidity_capacity": liquidity_capacity,
            "required_notional": required_notional,
            "sizing_available": sizing_available,
            "capital_authority": capital_authority,
            "flashloan_eligible": flashloan_eligible,
            "admission_allowed": admission_allowed,
            "admission_reason": admission.get("reason_code"),
            "gate_allowed": gate_allowed,
            "gate_reason": gate_reason,
            "recovery_ready": recovery_ready,
            "recovery_reason": recovery.get("reason_code") or recovery.get("reason"),
            "execution_ready": execution_ready,
            "execution_reason": execution_block_reason,
        }
        blocking_reason = _profitability_blocking_reason(truth, after_fee_usd_micro)
        if not blocking_reason:
            blocking_reason = _execution_blocking_reason(blocking_state)
        if not blocking_reason:
            blocking_reason = _governance_blocking_reason(blocking_state)

        eligible = not bool(blocking_reason)

        profit_rank = int(after_fee_usd_micro or 0) if eligible else 0
        capacity_rank = int(max(0.0, liquidity_capacity or 0.0) * 1000.0) if eligible else 0
        route_rank = 1 if eligible and route_ready and not route_degraded else 0
        readiness_rank = 1 if eligible and execution_ready else 0
        selection_score = (
            1 if eligible else 0,
            profit_rank,
            capacity_rank,
            route_rank,
            readiness_rank,
            str(getattr(candidate, "id", "") or ""),
        )

        return RuntimeOpportunityEvidence(
            runtime=runtime_name,
            candidate_count=int(candidate_count),
            opportunity_id=str(getattr(candidate, "id", "") or ""),
            route_id=str(getattr(candidate, "route_id", "") or ""),
            strategy=str(getattr(candidate, "strategy", "") or ""),
            after_fee_verified=bool(truth.verified),
            after_fee_positive=bool(truth.positive),
            after_fee_usd_micro=after_fee_usd_micro,
            after_fee_wei=int(truth.value_wei),
            canonical_profitability=bool(profitability.get("authoritative", False)),
            projected_profit_usd=projected_profit_usd,
            route_ready=route_ready,
            route_degraded=route_degraded,
            route_reason_code=route_reason,
            liquidity_capacity_usd=liquidity_capacity,
            required_notional_usd=required_notional,
            provider=provider,
            provider_capacity_usd=provider_capacity,
            sizing_available=bool(sizing_available),
            size_multiplier=_float(meta, "size_multiplier", "sizeMultiplier"),
            borrow_multiplier=_float(meta, "borrow_multiplier", "borrowMultiplier"),
            capital_authority_available=bool(capital_authority),
            flashloan_eligible=bool(flashloan_eligible),
            admission_allowed=bool(admission_allowed),
            gate_allowed=gate_allowed,
            gate_reason_code=gate_reason,
            recovery_ready=recovery_ready,
            execution_ready=bool(execution_ready),
            execution_block_reason=execution_block_reason,
            eligible=eligible,
            blocking_reason=blocking_reason,
            selection_score=selection_score,
        )

    async def _runtime_evidence(
        self, runtime_name: str, runtime: Any
    ) -> tuple[list[RuntimeOpportunityEvidence], str | None]:
        try:
            summary = await runtime.summary()
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            summary = {}
            error = f"summary_failed:{exc}"
        else:
            error = None

        opportunities = list(getattr(runtime, "_opps", []) or [])
        evidence = [
            self._candidate_evidence(
                runtime_name,
                len(opportunities),
                candidate,
                _mapping(summary),
            )
            for candidate in opportunities
        ]
        return evidence, error

    async def select(self, runtimes: Mapping[str, Any]) -> dict[str, Any]:
        """Inspect every configured runtime without changing active-chain state."""

        evidence: list[RuntimeOpportunityEvidence] = []
        runtime_errors: dict[str, str] = {}

        for runtime_name, runtime in runtimes.items():
            runtime_evidence, runtime_error = await self._runtime_evidence(
                str(runtime_name), runtime
            )
            evidence.extend(runtime_evidence)
            if runtime_error:
                runtime_errors[str(runtime_name)] = runtime_error

        eligible = [item for item in evidence if item.eligible]
        selected = max(eligible, key=lambda item: item.selection_score) if eligible else None

        return {
            "ok": True,
            "selected_runtime": selected.runtime if selected else "",
            "selected_opportunity_id": selected.opportunity_id if selected else "",
            "selected": selected.to_dict() if selected else None,
            "runtime_count": len(runtimes),
            "runtimes_inspected": [str(name) for name in runtimes.keys()],
            "candidates": [item.to_dict() for item in evidence],
            "blocked_candidates": [
                item.to_dict() for item in evidence if not item.eligible
            ],
            "runtime_errors": runtime_errors,
            "selection_authority": "read_only_evidence",
            "active_chain_changed": False,
            "auto_trade_enabled": False,
            "broadcast_attempted": False,
        }
