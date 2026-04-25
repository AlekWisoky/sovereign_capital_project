from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict

from ..fund_os.fund_stage import default_fund_stages
from ..internal_prime.contracts import PrimeBorrowRequest
from ..treasury.loan_policy import loan_admission
from ..profitability_state import (
    has_profitability_contract,
    post_mutation_revalidation_view,
    profitability_state_view,
)
from ..degraded_state_contract import decision_contract
from .capital_truth_health_contract import runtime_capital_truth_health
from .auxiliary_state_service import AuxiliaryStateService
from .treasury_service import TreasuryService
from .treasury_governance_truth import treasury_governance_view


@dataclass(frozen=True)
class PreTradeCapitalAdmission:
    allowed: bool
    reason_code: str
    strategy_family: str
    capital_source: str
    requested_notional_usd: float
    projected_realized_edge_usd: float
    confidence: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        details = dict(out.get("details") or {})
        contract = (
            details.get("stateContract") if isinstance(details.get("stateContract"), dict) else None
        )
        if contract is None:
            contract = decision_contract(
                phase="capital_admission",
                reason_code=str(
                    self.reason_code or ("ok" if self.allowed else "capital_admission_denied")
                ),
                degraded=not bool(self.allowed),
                blocked=not bool(self.allowed),
                denied=not bool(self.allowed),
                sticky_cycle=True,
                details={
                    "capitalSource": str(self.capital_source or ""),
                    "strategyFamily": str(self.strategy_family or ""),
                    "requestedNotionalUsd": float(self.requested_notional_usd or 0.0),
                    "projectedRealizedEdgeUsd": float(self.projected_realized_edge_usd or 0.0),
                },
            )
            details["stateContract"] = dict(contract)
            out["details"] = details
        out["stateContract"] = dict(contract)
        return out


class CapitalAdmissionService:
    def __init__(
        self,
        *,
        auxiliary_state: AuxiliaryStateService | None = None,
        treasury_service: TreasuryService | None = None,
    ) -> None:
        self.auxiliary_state = auxiliary_state or AuxiliaryStateService()
        self.treasury_service = treasury_service or TreasuryService()

    def _safe_dict(self, value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, dict) else {}

    def _strategy_family(self, opp: Any, decision: Any | None) -> str:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        decision_meta = self._safe_dict(getattr(decision, "metadata", None))
        envelope = self._safe_dict(decision_meta.get("envelope"))
        return str(
            opp_meta.get("strategy_family")
            or envelope.get("strategy_family")
            or envelope.get("route_family")
            or opp_meta.get("route_family")
            or getattr(opp, "strategy", "")
            or "flashloan_atomic"
        )

    def _effective_notional_multiplier(self, decision: Any | None) -> float:
        try:
            size_mult = float(getattr(decision, "size_mult", 1.0) or 1.0)
        except (AttributeError, TypeError, ValueError):
            size_mult = 1.0
        try:
            borrow_mult = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
        except (AttributeError, TypeError, ValueError):
            borrow_mult = 1.0
        return max(0.10, float(size_mult) * float(borrow_mult))

    def _base_requested_notional_usd(self, opp: Any, decision: Any | None) -> float:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        decision_meta = self._safe_dict(getattr(decision, "metadata", None))
        envelope = self._safe_dict(decision_meta.get("envelope"))
        unit_econ = self._safe_dict(opp_meta.get("unit_econ"))
        candidates = [
            getattr(opp, "capital_required_usd", None),
            opp_meta.get("capital_required_usd"),
            envelope.get("capital_required_usd"),
            opp_meta.get("entry_notional_usd"),
            unit_econ.get("entry_notional_usd"),
            self._safe_dict(decision_meta.get("capitalAdmission")).get("base_notional_usd"),
        ]
        for candidate in candidates:
            try:
                value = float(candidate or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value
        try:
            micros = int(unit_econ.get("entry_notional_usd_micro") or 0)
        except (TypeError, ValueError):
            micros = 0
        if micros > 0:
            return float(micros) / 1_000_000.0
        return 0.0

    def _requested_notional_usd(self, opp: Any, decision: Any | None) -> float:
        base_notional = float(self._base_requested_notional_usd(opp, decision) or 0.0)
        if base_notional <= 0.0:
            return 0.0
        return float(base_notional) * float(self._effective_notional_multiplier(decision))

    def _notional_truth(
        self, *, capital_source: str, base_notional_usd: float, requested_notional_usd: float
    ) -> Dict[str, Any]:
        available = (
            float(base_notional_usd or 0.0) > 0.0 and float(requested_notional_usd or 0.0) > 0.0
        )
        borrowed = str(capital_source or "") in {"flashloan", "internal_prime"}
        reason = (
            "ok"
            if available
            else (
                f"{capital_source}_notional_unavailable"
                if borrowed
                else "capital_notional_unavailable"
            )
        )
        return {
            "available": bool(available),
            "complete": bool(available),
            "strict": bool(borrowed),
            "borrowedCapital": bool(borrowed),
            "baseNotionalUsd": round(float(base_notional_usd or 0.0), 6),
            "requestedNotionalUsd": round(float(requested_notional_usd or 0.0), 6),
            "reason": reason,
        }

    def _state_contract(
        self,
        *,
        allowed: bool,
        reason_code: str,
        capital_source: str,
        strategy_family: str,
        requested_notional_usd: float,
        projected_realized_edge_usd: float,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        notional_truth = self._safe_dict(details.get("notionalTruth"))
        return decision_contract(
            phase="capital_admission",
            reason_code=str(reason_code or ("ok" if allowed else "capital_admission_denied")),
            degraded=not bool(allowed),
            blocked=not bool(allowed),
            denied=not bool(allowed),
            sticky_cycle=True,
            details={
                "capitalSource": str(capital_source or ""),
                "strategyFamily": str(strategy_family or ""),
                "requestedNotionalUsd": round(float(requested_notional_usd or 0.0), 6),
                "projectedRealizedEdgeUsd": round(float(projected_realized_edge_usd or 0.0), 6),
                "notionalTruth": dict(notional_truth),
            },
        )

    def _result(
        self,
        *,
        allowed: bool,
        reason_code: str,
        strategy_family: str,
        capital_source: str,
        requested_notional_usd: float,
        projected_realized_edge_usd: float,
        confidence: float,
        details: Dict[str, Any],
    ) -> PreTradeCapitalAdmission:
        out_details = dict(details)
        out_details["stateContract"] = self._state_contract(
            allowed=allowed,
            reason_code=reason_code,
            capital_source=capital_source,
            strategy_family=strategy_family,
            requested_notional_usd=requested_notional_usd,
            projected_realized_edge_usd=projected_realized_edge_usd,
            details=out_details,
        )
        return PreTradeCapitalAdmission(
            allowed=allowed,
            reason_code=reason_code,
            strategy_family=strategy_family,
            capital_source=capital_source,
            requested_notional_usd=requested_notional_usd,
            projected_realized_edge_usd=projected_realized_edge_usd,
            confidence=confidence,
            details=out_details,
        )

    def _profitability(self, opp: Any) -> Dict[str, Any]:
        try:
            return profitability_state_view(opp)
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}

    def _projected_realized_edge_usd(self, opp: Any, decision: Any | None) -> float:
        profitability = self._profitability(opp)
        try:
            after_costs_usd = (
                float(profitability.get("profitAfterCostsUsdMicroInt") or 0) / 1_000_000.0
            )
        except (TypeError, ValueError):
            after_costs_usd = 0.0
        if after_costs_usd > 0.0:
            return after_costs_usd
        try:
            expected_profit_usd = float(profitability.get("expectedProfitUsd") or 0.0)
        except (TypeError, ValueError):
            expected_profit_usd = 0.0
        if expected_profit_usd > 0.0:
            gross_wei = 0
            after_costs_wei = 0
            try:
                gross_wei = int(profitability.get("grossProfitWeiInt") or 0)
            except (TypeError, ValueError):
                gross_wei = 0
            try:
                after_costs_wei = int(profitability.get("profitAfterCostsWeiInt") or 0)
            except (TypeError, ValueError):
                after_costs_wei = 0
            if gross_wei > 0 and after_costs_wei > 0:
                ratio = min(1.0, max(0.0, float(after_costs_wei) / float(gross_wei)))
                scaled = float(expected_profit_usd) * float(ratio)
                if scaled > 0.0:
                    return scaled
            return expected_profit_usd
        candidates = [
            getattr(decision, "expected_realized_value", None),
            getattr(opp, "expected_realized_profit_usd", None),
            getattr(opp, "expected_profit_usd", None),
        ]
        for candidate in candidates:
            try:
                value = float(candidate or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value
        return 0.0

    def _confidence(self, opp: Any, decision: Any | None) -> float:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        candidates = [
            getattr(decision, "success_probability", None),
            getattr(opp, "confidence", None),
            opp_meta.get("confidence"),
        ]
        for candidate in candidates:
            try:
                value = float(candidate or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value
        return 0.0

    def _capital_source(self, opp: Any, decision: Any | None) -> str:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        decision_meta = self._safe_dict(getattr(decision, "metadata", None))
        envelope = self._safe_dict(decision_meta.get("envelope"))
        explicit = [
            getattr(opp, "loan_source", None),
            opp_meta.get("loan_source"),
            envelope.get("loan_source"),
            opp_meta.get("capital_source"),
            envelope.get("capital_source"),
        ]
        for candidate in explicit:
            src = str(candidate or "").strip().lower()
            if src in {"flashloan", "internal_prime", "bankroll"}:
                return src
        flashloan = self._safe_dict(decision_meta.get("flashloan_resilience"))
        route_family = str(envelope.get("route_family") or opp_meta.get("route_family") or "")
        strategy_family = self._strategy_family(opp, decision)
        if flashloan or "flash" in route_family or strategy_family == "flashloan_atomic":
            return "flashloan"
        return "bankroll"

    def _stage_policy(self, runtime: Any) -> Dict[str, Any]:
        stage = "internal_capital"
        try:
            cc = getattr(runtime, "_cc", None)
            if cc is not None and hasattr(cc, "snapshot"):
                stage = str((cc.snapshot() or {}).get("fundStage") or stage)
        except (AttributeError, KeyError, TypeError, ValueError):
            stage = "internal_capital"
        stages = default_fund_stages()
        return stages.get(stage, stages["internal_capital"]).to_dict()

    def _request_collateral_units(self, opp: Any, decision: Any | None = None) -> float:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        decision_meta = self._safe_dict(getattr(decision, "metadata", None))
        unit_econ = self._safe_dict(opp_meta.get("unit_econ"))
        candidates = [
            opp_meta.get("collateral_units"),
            opp_meta.get("inventory_units"),
            unit_econ.get("collateral_units"),
            unit_econ.get("entry_amount_units"),
            decision_meta.get("collateral_units"),
        ]
        for candidate in candidates:
            try:
                value = float(candidate or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value
        return 0.0

    def _request_asset_price_usd(self, opp: Any, decision: Any | None = None) -> float:
        opp_meta = self._safe_dict(getattr(opp, "meta", None))
        decision_meta = self._safe_dict(getattr(decision, "metadata", None))
        unit_econ = self._safe_dict(opp_meta.get("unit_econ"))
        candidates = [
            opp_meta.get("asset_price_usd"),
            opp_meta.get("entry_asset_price_usd"),
            unit_econ.get("asset_price_usd"),
            unit_econ.get("entry_asset_price_usd"),
            unit_econ.get("entry_token_price_usd"),
            decision_meta.get("asset_price_usd"),
        ]
        for candidate in candidates:
            try:
                value = float(candidate or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0.0:
                return value
        asset = self._request_asset(opp)
        if str(asset or "").upper() in {"USD", "USDC", "USDT", "DAI", "USDE", "PYUSD", "FDUSD"}:
            return 1.0
        return 0.0

    def _request_asset(self, opp: Any) -> str:
        try:
            legs = list(getattr(getattr(opp, "route", None), "legs", []) or [])
            if legs:
                token_in = str(getattr(legs[0], "token_in", "") or "")
                if token_in:
                    return token_in
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            token_path = list(getattr(opp, "token_path", []) or [])
            if token_path:
                return str(token_path[0] or "")
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        return "USD"

    def evaluate(
        self, runtime: Any, opp: Any, *, decision: Any | None = None
    ) -> PreTradeCapitalAdmission:
        strategy_family = self._strategy_family(opp, decision)
        capital_source = self._capital_source(opp, decision)
        base_notional_usd = float(self._base_requested_notional_usd(opp, decision) or 0.0)
        effective_notional_multiplier = float(self._effective_notional_multiplier(decision) or 1.0)
        requested_notional_usd = float(self._requested_notional_usd(opp, decision) or 0.0)
        projected_realized_edge_usd = float(self._projected_realized_edge_usd(opp, decision) or 0.0)
        confidence = float(self._confidence(opp, decision) or 0.0)
        stage_policy = self._stage_policy(runtime)
        capital_state = (
            runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
        )
        capital_truth = (
            runtime.capital_truth()
            if hasattr(runtime, "capital_truth")
            else self.auxiliary_state.capital_truth(runtime)
        )
        capital_summary = self._safe_dict(getattr(capital_truth, "capital_summary", None))
        capital_truth_health = runtime_capital_truth_health(
            runtime,
            fund_summary=(
                runtime.fund_summary_state() if hasattr(runtime, "fund_summary_state") else None
            ),
        )
        treasury_state = self._safe_dict(capital_state)
        treasury_governance = treasury_governance_view(treasury_state)
        flashloan_sizing = self._safe_dict(
            self._safe_dict(
                self._safe_dict(getattr(decision, "metadata", None)).get("flashloan_resilience")
            ).get("sizing")
        )
        profitability = self._profitability(opp)
        post_mutation_revalidation = post_mutation_revalidation_view(opp)
        details: Dict[str, Any] = {
            "fundStagePolicy": dict(stage_policy),
            "familyAdmission": {
                "admitted": False,
                "reason": "pending_family_admission",
                "limits": {},
            },
            "capitalTruthHealth": dict(capital_truth_health),
            "baseNotionalUsd": round(base_notional_usd, 6),
            "notionalMultiplier": round(effective_notional_multiplier, 6),
            "requestedNotionalUsd": round(requested_notional_usd, 6),
            "projectedRealizedEdgeUsd": round(projected_realized_edge_usd, 6),
            "notionalTruth": self._notional_truth(
                capital_source=capital_source,
                base_notional_usd=base_notional_usd,
                requested_notional_usd=requested_notional_usd,
            ),
            "confidence": round(confidence, 6),
            "capitalSummary": {
                "deployableUsd": float(capital_summary.get("deployableUsd") or 0.0),
                "navUsd": float(capital_summary.get("navUsd") or 0.0),
                "utilizationPct": float(capital_summary.get("utilizationPct") or 0.0),
            },
            "treasuryBorrowCap": float(
                treasury_governance.get("effective_borrow_mult_target_cap") or 1.0
            ),
            "treasuryGovernance": dict(treasury_governance),
            "capitalSource": capital_source,
            "profitability": dict(profitability),
            "postMutationRevalidation": dict(post_mutation_revalidation),
        }
        profitability_reason = str(profitability.get("reason") or "")
        if has_profitability_contract(opp) and profitability_reason != "gas_cost_unavailable":
            if (not bool(profitability.get("authoritative", False))) or bool(
                profitability.get("stale", True)
            ):
                return self._result(
                    allowed=False,
                    reason_code=f"profitability_contract:{str(profitability.get('reason') or 'stale')}",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
            if (not bool(profitability.get("valid", False))) or int(
                profitability.get("profitAfterCostsWeiInt") or 0
            ) <= 0:
                return self._result(
                    allowed=False,
                    reason_code=f"profitability_contract:{str(profitability.get('reason') or 'non_positive_after_costs')}",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
        capital_truth_contract = self._safe_dict(capital_truth_health.get("stateContract"))
        if capital_truth_health.get("blocked", False) or capital_truth_contract.get(
            "blocked", False
        ):
            capital_truth_reason = str(
                capital_truth_health.get("reasonCode")
                or capital_truth_health.get("freshnessReasonCode")
                or capital_truth_contract.get("reason_code")
                or "capital_truth_unavailable"
            )
            return self._result(
                allowed=False,
                reason_code=f"capital_truth_health:{capital_truth_reason}",
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )

        treasury_admission = self.treasury_service.check_family_admission(
            capital_state=capital_state,
            strategy_family=strategy_family,
            expected_value=projected_realized_edge_usd,
        )
        details["familyAdmission"] = {
            "admitted": bool(treasury_admission.admitted),
            "reason": str(treasury_admission.reason),
            "limits": dict(treasury_admission.limits or {}),
        }
        if not bool(treasury_admission.admitted):
            return self._result(
                allowed=False,
                reason_code=str(treasury_admission.reason or "family_cap_zero"),
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )

        if capital_source == "flashloan":
            details["flashloanSizing"] = dict(flashloan_sizing)
            if flashloan_sizing and not bool(flashloan_sizing.get("allowed", True)):
                return self._result(
                    allowed=False,
                    reason_code="flashloan_size_not_viable",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
            if requested_notional_usd > 0.0:
                policy = loan_admission(
                    family=strategy_family,
                    stage=str(stage_policy.get("stage") or "internal_capital"),
                    notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    source="flashloan",
                    confidence=confidence,
                )
                details["loanPolicy"] = dict(policy)
                if not bool(policy.get("allowed", True)):
                    return self._result(
                        allowed=False,
                        reason_code=f"loan_policy:{str(policy.get('reason') or 'denied')}",
                        strategy_family=strategy_family,
                        capital_source=capital_source,
                        requested_notional_usd=requested_notional_usd,
                        projected_realized_edge_usd=projected_realized_edge_usd,
                        confidence=confidence,
                        details=details,
                    )
                return self._result(
                    allowed=True,
                    reason_code="ok",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
            details["loanPolicy"] = {
                "allowed": False,
                "reason": "flashloan_notional_unavailable",
                "requiredConfidence": 0.70,
                "borrowCostUsd": 0.0,
                "evaluated": False,
                "strict": True,
            }
            return self._result(
                allowed=False,
                reason_code="flashloan_notional_unavailable",
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )

        if requested_notional_usd <= 0.0:
            return self._result(
                allowed=False,
                reason_code="capital_notional_unavailable",
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )

        if capital_source == "internal_prime":
            policy = loan_admission(
                family=strategy_family,
                stage=str(stage_policy.get("stage") or "internal_capital"),
                notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                source="internal_prime",
                confidence=confidence,
            )
            details["loanPolicy"] = dict(policy)
            asset = self._request_asset(opp)
            preview = {"allowed": False, "reason": "internal_prime_unavailable"}
            if getattr(runtime, "_internal_prime", None) is not None:
                req = PrimeBorrowRequest(
                    family=strategy_family,
                    capital_source="internal_prime",
                    notional_usd=requested_notional_usd,
                    asset=str(asset or "USD"),
                    horizon_minutes=180.0,
                    confidence=confidence,
                    collateral_units=self._request_collateral_units(opp, decision),
                    asset_price_usd=self._request_asset_price_usd(opp, decision),
                    metadata={
                        "opportunity_id": str(getattr(opp, "id", "") or ""),
                        "route_id": str(getattr(opp, "route_id", "") or ""),
                    },
                )
                preview = runtime._internal_prime.preview(req, stage_policy=dict(stage_policy))
            details["internalPrimePreview"] = dict(preview)
            if not bool(preview.get("allowed", False)):
                return self._result(
                    allowed=False,
                    reason_code=f"internal_prime:{str(preview.get('reason') or 'denied')}",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
            if not bool(policy.get("allowed", True)):
                return self._result(
                    allowed=False,
                    reason_code=f"loan_policy:{str(policy.get('reason') or 'denied')}",
                    strategy_family=strategy_family,
                    capital_source=capital_source,
                    requested_notional_usd=requested_notional_usd,
                    projected_realized_edge_usd=projected_realized_edge_usd,
                    confidence=confidence,
                    details=details,
                )
            return self._result(
                allowed=True,
                reason_code="ok",
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )

        deployable_usd = float(capital_summary.get("deployableUsd") or 0.0)
        details["bankrollAdmission"] = {
            "deployableUsd": deployable_usd,
            "allowed": bool(deployable_usd > 0.0 and requested_notional_usd <= deployable_usd),
        }
        if not bool(details["bankrollAdmission"]["allowed"]):
            return self._result(
                allowed=False,
                reason_code="deployable_capital_exceeded",
                strategy_family=strategy_family,
                capital_source=capital_source,
                requested_notional_usd=requested_notional_usd,
                projected_realized_edge_usd=projected_realized_edge_usd,
                confidence=confidence,
                details=details,
            )
        return self._result(
            allowed=True,
            reason_code="ok",
            strategy_family=strategy_family,
            capital_source=capital_source,
            requested_notional_usd=requested_notional_usd,
            projected_realized_edge_usd=projected_realized_edge_usd,
            confidence=confidence,
            details=details,
        )
