from __future__ import annotations

import time
from collections.abc import Mapping as ABCMapping
from typing import Any, Callable, Dict

from ..alpha_platform.fund_families import default_fund_families
from ..alpha_platform.income_streams import rotation_plan
from ..alpha_platform.registry import alpha_engine_registry
from ..alpha_platform.scorecards import build_alpha_scorecards
from ..alpha_platform.profit_mix import build_profit_mix
from ..fund_os.manifests import build_fund_manifest
from ..fund_os.master_orchestrator import FundMasterOrchestrator
from ..research_pipeline.workspace import ResearchWorkspace
from ..risk_engine.concentration import concentration_summary
from ..risk_engine.controls import risk_controls
from ..risk_engine.dashboard_metrics import cio_dashboard_metrics
from ..risk_engine.portfolio_risk import compute_portfolio_risk
from ..persistence.repositories.capital_recovery_repository import CapitalRecoveryRepository
from ..telemetry.fund_summary import (
    apply_recovery_history,
    apply_recovery_reliability,
    build_fund_health_summary,
)
from .control_state import unavailable_state
from .family_hardening_service import family_hardening_unavailable_summary
from .auxiliary_state_service import AuxiliaryStateService
from .summary_read_contract import build_summary_read_contract
from .capital_truth_read_context import build_capital_truth_read_context

_FUND_SUMMARY_COMPONENT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _component_payload(
    runtime: Any,
    *,
    method_name: str,
    unavailable_reason: str,
    extra: dict[str, Any] | None = None,
    unavailable_factory: Callable[[], Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    def _fallback() -> Dict[str, Any]:
        if unavailable_factory is not None:
            payload = unavailable_factory()
            if isinstance(payload, ABCMapping):
                return dict(payload)
        return unavailable_state(unavailable_reason, extra=extra)

    if not hasattr(runtime, method_name):
        return _fallback()
    try:
        payload = getattr(runtime, method_name)()
    except _FUND_SUMMARY_COMPONENT_FAILURES:
        return _fallback()
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return _fallback()


def _optional_runtime_mapping(
    runtime: Any,
    *,
    method_name: str,
    default: Dict[str, Any],
) -> Dict[str, Any]:
    if not hasattr(runtime, method_name):
        return dict(default)
    try:
        payload = getattr(runtime, method_name)()
    except _FUND_SUMMARY_COMPONENT_FAILURES:
        return dict(default)
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return dict(default)


def _summary_stage(runtime: Any | None) -> str:
    stage = "internal_capital"
    if runtime is None:
        return stage
    try:
        stage = str(
            (
                (
                    runtime._cc.snapshot()
                    if getattr(runtime, "_cc", None) is not None
                    and hasattr(runtime._cc, "snapshot")
                    else {}
                )
                or {}
            ).get("fundStage")
            or "internal_capital"
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        stage = "internal_capital"
    return stage


def _fallback_research_pipeline(runtime: Any) -> Dict[str, Any]:
    if hasattr(runtime, "research_pipeline_state"):
        try:
            payload = runtime.research_pipeline_state()
        except _FUND_SUMMARY_COMPONENT_FAILURES:
            payload = None
        if isinstance(payload, ABCMapping):
            return dict(payload)
    try:
        cfg = getattr(runtime, "cfg", None)
        chain_obj = getattr(cfg, "chain", None)
        workspace = ResearchWorkspace(
            data_dir=str(getattr(runtime, "data_dir", "data")),
            chain=str(
                getattr(chain_obj, "name", "default") if chain_obj is not None else "default"
            ),
        ).snapshot()
        if isinstance(workspace, ABCMapping):
            return dict(workspace)
    except _FUND_SUMMARY_COMPONENT_FAILURES:
        pass
    return {"items": [], "pipelineCounts": {}, "throughput": {}}


def fund_summary_unavailable_payload(runtime: Any | None = None) -> Dict[str, Any]:
    stage = _summary_stage(runtime)
    doctrine = (
        _component_payload(
            runtime,
            method_name="doctrine_state",
            unavailable_reason="doctrine_unavailable",
            extra={"optimizationObjectives": {}},
        )
        if runtime is not None
        else unavailable_state(
            "doctrine_unavailable",
            extra={"optimizationObjectives": {}},
        )
    )
    ledger = (
        _component_payload(
            runtime,
            method_name="ledger_state",
            unavailable_reason="ledger_unavailable",
            extra={"balances": {}, "tail": [], "transactions": []},
        )
        if runtime is not None
        else unavailable_state(
            "ledger_unavailable",
            extra={"balances": {}, "tail": [], "transactions": []},
        )
    )
    internal_prime = (
        _component_payload(
            runtime,
            method_name="internal_prime_state",
            unavailable_reason="internal_prime_unavailable",
            extra={
                "borrowedUsd": 0.0,
                "capacityUsd": 0.0,
                "utilization": 0.0,
                "inventory": {},
                "familyExposure": {},
                "openLoans": [],
                "disputedLoans": [],
                "loanCount": 0,
                "disputedLoanCount": 0,
            },
        )
        if runtime is not None
        else unavailable_state(
            "internal_prime_unavailable",
            extra={
                "borrowedUsd": 0.0,
                "capacityUsd": 0.0,
                "utilization": 0.0,
                "inventory": {},
                "familyExposure": {},
                "openLoans": [],
                "disputedLoans": [],
                "loanCount": 0,
                "disputedLoanCount": 0,
            },
        )
    )
    capital_truth = (
        _component_payload(
            runtime,
            method_name="capital_truth_state",
            unavailable_reason="capital_truth_unavailable",
        )
        if runtime is not None
        else unavailable_state("capital_truth_unavailable")
    )
    family_hardening = (
        _component_payload(
            runtime,
            method_name="family_hardening_state",
            unavailable_reason="family_hardening_unavailable",
            extra={"items": []},
            unavailable_factory=family_hardening_unavailable_summary,
        )
        if runtime is not None
        else family_hardening_unavailable_summary()
    )
    endpoint_quality = (
        _optional_runtime_mapping(runtime, method_name="endpoint_quality_state", default={})
        if runtime is not None
        else {}
    )
    endpoint_universe = (
        _optional_runtime_mapping(runtime, method_name="endpoint_universe_state", default={})
        if runtime is not None
        else {}
    )
    route_quality = (
        _optional_runtime_mapping(runtime, method_name="route_quality_state", default={})
        if runtime is not None
        else {}
    )
    payload = unavailable_state("fund_service_unavailable")
    payload.update(
        {
            "fundOs": build_fund_manifest(stage=stage),
            "profitDoctrine": doctrine,
            "fundMaster": {},
            "alphaPlatform": {"registry": {}, "fundFamilies": {}, "scorecards": {"engines": []}},
            "researchPipeline": (
                _fallback_research_pipeline(runtime)
                if runtime is not None
                else {"items": [], "pipelineCounts": {}, "throughput": {}}
            ),
            "capital": (
                _optional_runtime_mapping(runtime, method_name="capital_engine_state", default={})
                if runtime is not None
                else {}
            ),
            "capitalTruth": capital_truth,
            "risk": {},
            "riskControls": {},
            "concentration": {},
            "ledger": ledger,
            "internalPrime": internal_prime,
            "cioSummary": {},
            "health": {"fundStage": stage},
            "executionQuality": {
                "endpointQuality": endpoint_quality,
                "endpointUniverse": endpoint_universe,
                "routeQuality": route_quality,
            },
            "profitMix": {},
            "incomeRotation": {},
            "familyHardening": family_hardening,
        }
    )
    return payload


class FundService:
    def summary(self, runtime: Any) -> Dict[str, Any]:
        stage = _summary_stage(runtime)
        fund_os = build_fund_manifest(stage=stage)
        capital = _optional_runtime_mapping(
            runtime,
            method_name="capital_engine_state",
            default={},
        )
        engines = _optional_runtime_mapping(
            runtime,
            method_name="engine_state",
            default={},
        )
        telemetry = _optional_runtime_mapping(
            runtime,
            method_name="telemetry_summary",
            default={},
        )
        scorecards = _optional_runtime_mapping(
            runtime,
            method_name="strategy_scorecards_state",
            default={"families": []},
        )
        family_covariance = getattr(runtime, "_family_covariance", None)
        covariance = dict(
            family_covariance.snapshot()
            if family_covariance is not None and hasattr(family_covariance, "snapshot")
            else {}
        )
        drawdown_state = _optional_runtime_mapping(
            runtime,
            method_name="drawdown_state",
            default={},
        )
        kill_switch = _optional_runtime_mapping(
            runtime,
            method_name="kill_switch_state",
            default={},
        )
        endpoint_quality = _optional_runtime_mapping(
            runtime,
            method_name="endpoint_quality_state",
            default={},
        )
        endpoint_universe = _optional_runtime_mapping(
            runtime,
            method_name="endpoint_universe_state",
            default={},
        )
        route_quality = _optional_runtime_mapping(
            runtime,
            method_name="route_quality_state",
            default={},
        )
        risk = compute_portfolio_risk(
            capital_state=capital,
            covariance_penalties=dict(covariance.get("penalties") or {}),
            engine_state=engines,
            scorecards=scorecards,
            drawdown_state=drawdown_state,
        )
        controls = risk_controls(
            risk_score=float(risk.get("riskScore") or 0.0),
            fund_stage=((fund_os or {}).get("fund_os") or {}).get("stage_policy") or {},
        )
        alpha = {
            "registry": alpha_engine_registry(),
            "fundFamilies": {k: v.to_dict() for k, v in default_fund_families().items()},
            "scorecards": build_alpha_scorecards(
                family_scorecards=scorecards, engine_state=engines
            ),
        }
        workspace = _fallback_research_pipeline(runtime)
        ledger = _component_payload(
            runtime,
            method_name="ledger_state",
            unavailable_reason="ledger_unavailable",
            extra={"balances": {}, "tail": [], "transactions": []},
        )
        doctrine = _component_payload(
            runtime,
            method_name="doctrine_state",
            unavailable_reason="doctrine_unavailable",
            extra={"optimizationObjectives": {}},
        )
        internal_prime = _component_payload(
            runtime,
            method_name="internal_prime_state",
            unavailable_reason="internal_prime_unavailable",
            extra={
                "borrowedUsd": 0.0,
                "capacityUsd": 0.0,
                "utilization": 0.0,
                "inventory": {},
                "familyExposure": {},
                "openLoans": [],
                "disputedLoans": [],
                "loanCount": 0,
                "disputedLoanCount": 0,
            },
        )
        capital_truth = _component_payload(
            runtime,
            method_name="capital_truth_state",
            unavailable_reason="capital_truth_unavailable",
        )
        family_hardening = _component_payload(
            runtime,
            method_name="family_hardening_state",
            unavailable_reason="family_hardening_unavailable",
            extra={"items": []},
            unavailable_factory=family_hardening_unavailable_summary,
        )
        capital_eff = dict((capital or {}).get("capital_efficiency_metrics") or {})
        family_metrics = {
            str(x.get("family")): {
                "realizedPnlUsd": float(x.get("realizedPnlUsd") or 0.0),
                "capitalEfficiency": float(x.get("gasEfficiency") or 0.0),
                "stability": float(x.get("stability") or 0.0),
                "drawdownPenalty": float(x.get("drawdownPenaltyUsd") or 0.0),
            }
            for x in list((scorecards or {}).get("families") or [])
            if isinstance(x, dict)
        }
        health = build_fund_health_summary(
            fund_os=fund_os,
            alpha=alpha,
            research=workspace,
            capital=capital,
            risk=risk,
            engines=engines,
            telemetry=telemetry,
            capital_truth=capital_truth,
            internal_prime=internal_prime,
            family_hardening=family_hardening,
            drawdown=drawdown_state,
            kill_switch=kill_switch,
            endpoint_quality=endpoint_quality,
        )
        recovery_repo = getattr(runtime, "_capital_recovery_repo", None)
        if recovery_repo is None and getattr(runtime, "_db", None) is not None:
            try:
                cfg = getattr(runtime, "cfg", None)
                chain_obj = getattr(cfg, "chain", None)
                recovery_repo = CapitalRecoveryRepository(
                    runtime._db,
                    chain=str(
                        getattr(chain_obj, "name", "default")
                        if chain_obj is not None
                        else "default"
                    ),
                )
                runtime._capital_recovery_repo = recovery_repo
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                recovery_repo = None
        histories: dict[str, dict[str, Any]] = {}
        history_now_ms = int(health.get("capitalTruthObservedTsMs") or time.time() * 1000)
        if recovery_repo is not None:
            try:
                capital_truth_codes = [
                    str(x) for x in list(health.get("capitalTruthReasonCodes") or []) if str(x)
                ]
                receipt_outcome_truth_codes = [
                    str(x)
                    for x in list(health.get("receiptOutcomeTruthReasonCodes") or [])
                    if str(x)
                ]
                internal_prime_codes = [
                    str(x) for x in list(health.get("internalPrimeReasonCodes") or []) if str(x)
                ]
                family_hardening_codes = [
                    str(x) for x in list(health.get("familyHardeningReasonCodes") or []) if str(x)
                ]
                histories["capital_truth"] = recovery_repo.observe(
                    component="capital_truth",
                    degraded=bool(capital_truth_codes),
                    ts_ms=history_now_ms,
                    reason_code=str(capital_truth_codes[0] if capital_truth_codes else "ok"),
                )
                histories["receipt_outcome_truth"] = recovery_repo.observe(
                    component="receipt_outcome_truth",
                    degraded=bool(receipt_outcome_truth_codes),
                    ts_ms=history_now_ms,
                    reason_code=str(
                        receipt_outcome_truth_codes[0] if receipt_outcome_truth_codes else "ok"
                    ),
                )
                histories["internal_prime_reconciliation"] = recovery_repo.observe(
                    component="internal_prime_reconciliation",
                    degraded=bool(internal_prime_codes),
                    ts_ms=history_now_ms,
                    reason_code=str(internal_prime_codes[0] if internal_prime_codes else "ok"),
                )
                histories["family_hardening"] = recovery_repo.observe(
                    component="family_hardening",
                    degraded=bool(family_hardening_codes),
                    ts_ms=history_now_ms,
                    reason_code=str(family_hardening_codes[0] if family_hardening_codes else "ok"),
                )
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                histories = {}
        health = apply_recovery_history(health, histories=histories, now_ms=history_now_ms)
        health = apply_recovery_reliability(health)
        fund_master = FundMasterOrchestrator().compose(
            stage=stage,
            nav_usd=(
                float((capital_eff or {}).get("deployedCapitalWei", 0.0) or 0.0) / 1e18
                if float((capital_eff or {}).get("deployedCapitalWei", 0.0) or 0.0) > 1e9
                else float((capital_eff or {}).get("deployedCapitalWei", 0.0) or 0.0)
            ),
            family_targets=dict(
                (capital or {}).get("capital_engine", {}).get("family_targets") or {}
            ),
            income_metrics=family_metrics,
            capital_metrics=capital_eff,
            fund_health={
                "realizedPnlUsd": float(health.get("deployedCapitalWei") or 0.0),
                "capitalEfficiency": float(
                    capital_eff.get("failureAdjustedCapitalEfficiency") or 0.0
                ),
                "stabilityScore": float(health.get("riskScore") or 0.0),
                "executionCostUsd": 0.0,
                "failureRate": float(
                    (telemetry or {}).get("realization", {}).get("falseAdmissionRate", 0.0) or 0.0
                ),
                "competitionScore": 1.0 - float((risk or {}).get("riskScore") or 0.0),
            },
        )
        cio = cio_dashboard_metrics(
            capital=capital,
            risk=risk,
            alpha=alpha,
            research=workspace,
            internal_prime=internal_prime,
        )
        profit_mix = build_profit_mix(scorecards)
        capital_context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=AuxiliaryStateService(),
            fund_summary=health,
            include_operator_projection=False,
        )
        capital_truth_snapshot = capital_context.capital_truth
        capital_truth_health = dict(capital_context.capital_truth_health or {})
        capital_surface = dict(capital_context.capital_surface or {})
        payload = {
            "fundOs": fund_os,
            "profitDoctrine": doctrine,
            "fundMaster": fund_master,
            "alphaPlatform": alpha,
            "researchPipeline": workspace,
            "capital": capital,
            **capital_surface,
            "capitalTruth": capital_truth,
            "risk": risk,
            "riskControls": controls,
            "concentration": concentration_summary(capital_state=capital, engine_state=engines),
            "ledger": ledger,
            "internalPrime": internal_prime,
            "cioSummary": cio,
            "health": health,
            "executionQuality": {
                "endpointQuality": endpoint_quality,
                "endpointUniverse": endpoint_universe,
                "routeQuality": route_quality,
            },
            "profitMix": profit_mix,
            "incomeRotation": rotation_plan(metrics=family_metrics),
            "familyHardening": family_hardening,
        }
        payload["summaryContract"] = build_summary_read_contract(
            family="fund",
            payload=payload,
            capital_contract=capital_truth_snapshot.capital_contract,
            capital_policy=capital_truth_snapshot.capital_policy,
            source_contracts={
                "capitalContract": capital_truth_snapshot.capital_contract,
                "capitalPolicy": capital_truth_snapshot.capital_policy,
                "capitalTruth": capital_truth,
            },
            phase="fund_summary",
        )
        return payload
