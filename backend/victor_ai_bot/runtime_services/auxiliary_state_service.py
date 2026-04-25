from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping

from ..fund_os.objectives import doctrine_snapshot

from ..jsonsafe import to_json_safe
from ..capital_family_policy import FAMILY_CAPITAL_PLAN_VERSION, build_family_capital_plan
from .control_state import unavailable_state
from ..degraded_state_contract import normalize_surface_contract
from .capital_truth_health_contract import runtime_capital_truth_health
from .capital_truth_read_context import build_capital_truth_read_context

_SAFE_STATE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)
_SAFE_PERSISTENCE_EXCEPTIONS = _SAFE_STATE_EXCEPTIONS + (OSError, sqlite3.Error)


CAPITAL_CONTRACT_VERSION = "canonical_capital_summary_v1"
CAPITAL_POLICY_VERSION = "capital_policy_v1"
CAPITAL_ECONOMIC_MODEL_VERSION = "capital_economic_model_v1"
LIVE_CAPITAL_AUTHORITY_MODE = "live_rebuilt"


@dataclass(frozen=True)
class CapitalTruthSnapshot:
    capital_summary: Dict[str, Any]
    capital_contract: Dict[str, Any]
    capital_policy: Dict[str, Any]
    capital_economic_model: Dict[str, Any]
    authority: Dict[str, Any]


class AuxiliaryStateService:
    """Snapshot optional runtime subsystems without leaking legacy wiring into RuntimeBundle.

    These endpoints are operator/reporting surfaces, not execution hot paths. Keep them
    deterministic, narrow their exception handling, and centralize optional subsystem access.
    """

    @staticmethod
    def _unavailable_payload(
        reason_code: str = "unavailable",
        *,
        extra: Dict[str, Any] | None = None,
        ok: bool = True,
        include_error: bool = False,
    ) -> Dict[str, Any]:
        payload = unavailable_state(
            reason_code,
            extra=dict(extra or {}),
            include_error=include_error,
        )
        payload["ok"] = bool(ok)
        if ok:
            payload.setdefault("enabled", False)
        return payload

    @staticmethod
    def _error_payload(*, prefix: str, exc: Exception, fallback: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(fallback)
        payload.update({"ok": False, "error": f"{prefix}:{exc}"})
        return payload

    @staticmethod
    def _degraded_payload(
        reason_code: str,
        *,
        extra: Dict[str, Any] | None = None,
        include_reason: bool = True,
        include_error: bool = True,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "status": "degraded",
            "reason_code": str(reason_code),
        }
        if include_reason:
            payload["reason"] = str(reason_code)
        if include_error:
            payload["error"] = str(reason_code)
        if extra:
            payload.update(dict(extra))
        return payload

    @classmethod
    def _optional_component_payload(
        cls,
        component: Any,
        *,
        action: Callable[[Any], Any],
        unavailable: Dict[str, Any],
        failure_prefix: str,
        fallback: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if component is None:
            return dict(unavailable)
        try:
            return to_json_safe(action(component))
        except _SAFE_STATE_EXCEPTIONS as exc:
            return cls._error_payload(
                prefix=failure_prefix,
                exc=exc,
                fallback=fallback if fallback is not None else {"ok": False},
            )

    @classmethod
    async def _optional_component_payload_async(
        cls,
        component: Any,
        *,
        action: Callable[[Any], Any],
        unavailable: Dict[str, Any],
        failure_prefix: str,
        fallback: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if component is None:
            return dict(unavailable)
        try:
            return to_json_safe(await action(component))
        except _SAFE_STATE_EXCEPTIONS as exc:
            return cls._error_payload(
                prefix=failure_prefix,
                exc=exc,
                fallback=fallback if fallback is not None else {"ok": False},
            )

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, Mapping) else {}

    @staticmethod
    def _iter_rows(rows: Iterable[Any] | None) -> list[Any]:
        return list(rows or [])[:100]

    @staticmethod
    def _optional_snapshot(store: Any, *, method: str = "snapshot") -> Dict[str, Any]:
        if store is None or not hasattr(store, method):
            return AuxiliaryStateService._unavailable_payload()
        try:
            value = getattr(store, method)()
            return to_json_safe(value if isinstance(value, Mapping) else dict(value or {}))
        except _SAFE_STATE_EXCEPTIONS:
            return AuxiliaryStateService._unavailable_payload()

    def superstructure_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_super", None),
            action=lambda superstructure: superstructure.state(),
            unavailable=self._unavailable_payload(),
            failure_prefix="superstructure_state_failed",
        )

    def superstructure_command_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_super", None),
            action=lambda superstructure: (
                command.snapshot()
                if (command := getattr(superstructure, "command", None)) is not None
                else AuxiliaryStateService._unavailable_payload()
            ),
            unavailable=self._unavailable_payload(),
            failure_prefix="command_state_failed",
        )

    def governance_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_super", None),
            action=lambda superstructure: (
                governance.snapshot()
                if (governance := getattr(superstructure, "governance", None)) is not None
                else AuxiliaryStateService._unavailable_payload()
            ),
            unavailable=self._unavailable_payload(),
            failure_prefix="governance_state_failed",
        )

    def governance_health(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_super", None),
            action=lambda superstructure: self._governance_health_payload(superstructure),
            unavailable=self._unavailable_payload(),
            failure_prefix="governance_health_failed",
        )

    @staticmethod
    def _governance_health_payload(superstructure: Any) -> Dict[str, Any]:
        governance = getattr(superstructure, "governance", None)
        if governance is None:
            return AuxiliaryStateService._unavailable_payload()
        snap = AuxiliaryStateService._safe_dict(governance.snapshot()).get("governance") or {}
        return {"ok": True, "health": (snap.get("health") or None)}

    def fioa_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_fioa", None),
            action=lambda fioa: fioa.state(),
            unavailable=self._unavailable_payload(),
            failure_prefix="fioa_state_failed",
        )

    def fioa_audit_tail(self, runtime: Any, *, limit: int = 200) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_fioa", None),
            action=lambda fioa: {"ok": True, "items": fioa.audit.tail(limit=int(limit))},
            unavailable=self._unavailable_payload(extra={"items": []}),
            failure_prefix="fioa_audit_failed",
            fallback={"ok": False, "items": []},
        )

    def fioa_governance_report(self, runtime: Any, *, limit_audit: int = 200) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_fioa", None),
            action=lambda fioa: fioa.governance_report(limit_audit=int(limit_audit)),
            unavailable=self._unavailable_payload(),
            failure_prefix="fioa_report_failed",
        )

    def narrative_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_inl", None),
            action=lambda inl: inl.state(runtime),
            unavailable=self._unavailable_payload(),
            failure_prefix="narrative_state_failed",
        )

    def narrative_history(self, runtime: Any, *, limit: int = 100) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_inl", None),
            action=lambda inl: {"ok": True, "items": inl.history(limit=int(limit))},
            unavailable=self._unavailable_payload(extra={"items": []}),
            failure_prefix="narrative_history_failed",
            fallback={"ok": False, "items": []},
        )

    def narrative_report(self, runtime: Any, *, limit: int = 100) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_inl", None),
            action=lambda inl: {"ok": True, "report": inl.narrative_audit_report(limit=int(limit))},
            unavailable=self._unavailable_payload(extra={"report": ""}),
            failure_prefix="narrative_report_failed",
            fallback={"ok": False, "report": ""},
        )

    def narrative_set_level(self, runtime: Any, level: str) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_inl", None),
            action=lambda inl: {"ok": True, "level": inl.set_explanation_level(level)},
            unavailable=self._unavailable_payload(
                "narrative_unavailable", ok=False, include_error=True
            ),
            failure_prefix="narrative_set_level_failed",
        )

    async def narrative_query(
        self, runtime: Any, *, agent_id: str, query_text: str, data_level: str = "INTERNAL_STRATEGY"
    ) -> Dict[str, Any]:
        return await self._optional_component_payload_async(
            getattr(runtime, "_inl", None),
            action=lambda inl: inl.query(
                runtime,
                agent_id=str(agent_id or ""),
                query_text=str(query_text or ""),
                data_level=str(data_level or "INTERNAL_STRATEGY"),
            ),
            unavailable=self._unavailable_payload(
                "narrative_unavailable", ok=False, include_error=True
            ),
            failure_prefix="narrative_query_failed",
        )

    async def narrative_insights(self, runtime: Any) -> Dict[str, Any]:
        return await self._optional_component_payload_async(
            getattr(runtime, "_inl", None),
            action=lambda inl: self._narrative_insights_payload(inl, runtime),
            unavailable=self._unavailable_payload(
                "narrative_unavailable", ok=False, include_error=True
            ),
            failure_prefix="narrative_insights_failed",
        )

    @staticmethod
    async def _narrative_insights_payload(inl: Any, runtime: Any) -> Dict[str, Any]:
        return {"ok": True, "insights": await inl.insights(runtime)}

    def mev_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_component_payload(
            getattr(runtime, "_mev", None),
            action=lambda mev: mev.state(),
            unavailable=self._unavailable_payload(),
            failure_prefix="mev_state_failed",
        )

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return int(default)

    @staticmethod
    def _wei_to_usd(value: Any) -> float:
        try:
            return float(int(str(value or 0))) / 1_000_000_000_000_000_000.0
        except (TypeError, ValueError):
            return 0.0

    def _build_capital_summary(self, runtime: Any) -> Dict[str, Any]:
        ledger_state = self.ledger_state(runtime)
        internal_prime = self.internal_prime_state(runtime)
        capital_state = (
            runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
        )
        capital_engine = (
            dict((capital_state or {}).get("capital_engine") or {})
            if isinstance(capital_state, Mapping)
            else {}
        )
        capital_metrics = (
            dict((capital_state or {}).get("capital_efficiency_metrics") or {})
            if isinstance(capital_state, Mapping)
            else {}
        )
        reinvestment_policy = (
            dict((capital_state or {}).get("reinvestment_policy") or {})
            if isinstance(capital_state, Mapping)
            else {}
        )
        treasury = getattr(runtime, "_treasury", None)
        treasury_snapshot = self._optional_snapshot(treasury)
        treasury_meta = dict(getattr(getattr(treasury, "cfg", None), "meta", {}) or {})
        bankroll = getattr(runtime, "_bankroll", None)
        bankroll_state = getattr(bankroll, "state", None)
        pnl_summary_safe = self._safe_dict(getattr(runtime, "_last_operator_pnl_summary", {}))
        last_settlement = self._safe_dict(getattr(runtime, "_last_settlement_sync", {}))
        balances = self._safe_dict(ledger_state.get("balances"))
        ledger_nav_usd = self._safe_float(balances.get("USD"))
        pnl_nav_usd = self._safe_float(pnl_summary_safe.get("total_realized_profit_after_gas_usd"))
        has_settlement = bool(
            last_settlement.get("receiptId")
            or last_settlement.get("transactionId")
            or ledger_state.get("transactions")
        )
        if has_settlement or ledger_nav_usd != 0.0:
            nav_usd = ledger_nav_usd
            nav_source = "ledger_usd_balance"
        elif pnl_nav_usd != 0.0:
            nav_usd = pnl_nav_usd
            nav_source = "pnl_realized_after_gas_usd"
        else:
            nav_usd = 0.0
            nav_source = "unavailable"
        deployable_usd = self._wei_to_usd(capital_engine.get("deployable_bankroll_wei"))
        reserve_usd = self._wei_to_usd(capital_engine.get("reserve_bankroll_wei"))
        experimental_usd = self._wei_to_usd(capital_engine.get("experimental_bankroll_wei"))
        drawdown_buffer_usd = self._wei_to_usd(capital_engine.get("drawdown_buffer_wei"))
        treasury_offramp_usd = self._wei_to_usd(capital_engine.get("treasury_offramp_wei"))
        deployed_capital_usd = self._wei_to_usd(capital_metrics.get("deployedCapitalWei"))
        estimated_capital_usd = self._wei_to_usd(
            treasury_meta.get("estimated_capital_wei") or treasury_meta.get("estimatedCapitalWei")
        )
        if estimated_capital_usd <= 0.0:
            estimated_capital_usd = max(
                nav_usd,
                deployable_usd
                + reserve_usd
                + experimental_usd
                + drawdown_buffer_usd
                + treasury_offramp_usd,
            )
        if estimated_capital_usd <= 0.0:
            estimated_capital_usd = max(deployable_usd, nav_usd)
        borrowed_usd = self._safe_float(internal_prime.get("borrowedUsd"))
        active_pct = round(
            (
                ((deployed_capital_usd / estimated_capital_usd) * 100.0)
                if estimated_capital_usd > 0
                else 0.0
            ),
            2,
        )
        sandbox_pct = round(
            (
                ((experimental_usd / estimated_capital_usd) * 100.0)
                if estimated_capital_usd > 0
                else 0.0
            ),
            2,
        )
        at_risk_pct = round(
            ((borrowed_usd / estimated_capital_usd) * 100.0) if estimated_capital_usd > 0 else 0.0,
            2,
        )
        idle_pct = round(max(0.0, 100.0 - active_pct - sandbox_pct - at_risk_pct), 2)
        scorecards = (
            runtime.strategy_scorecards_state()
            if hasattr(runtime, "strategy_scorecards_state")
            else {}
        )
        family_metrics = {
            str(item.get("family") or ""): self._safe_dict(item)
            for item in list(self._safe_dict(scorecards).get("families") or [])
            if isinstance(item, Mapping)
        }
        allocations = build_family_capital_plan(
            capital_engine=capital_engine,
            family_metrics=family_metrics,
            deployable_usd=deployable_usd,
        )
        capital_flows = []
        for tx in list(ledger_state.get("transactions") or [])[:20]:
            txd = self._safe_dict(tx)
            metadata = self._safe_dict(txd.get("metadata"))
            net_usd = abs(self._safe_float(metadata.get("net_realized_usd")))
            if net_usd <= 0.0:
                continue
            route_family = str(
                metadata.get("strategy_family")
                or metadata.get("route_family")
                or "flashloan_atomic"
            )
            capital_flows.append(
                {
                    "id": str(txd.get("transaction_id") or txd.get("receipt_id") or ""),
                    "tsMs": self._safe_int(txd.get("ts_ms")),
                    "from": route_family.replace("_", " ").title(),
                    "to": "Treasury",
                    "amountUsd": float(round(abs(net_usd), 6)),
                    "triggeredBy": "system",
                    "why": str(
                        metadata.get("capture_lane") or txd.get("tx_type") or "settlement_sync"
                    ),
                    "riskResult": "approved",
                    "execSummary": str(metadata.get("route_id") or metadata.get("tx_hash") or ""),
                }
            )
        settlement_profitability = self._safe_dict(last_settlement.get("profitabilityChain"))
        terminal_authority = self._safe_dict(
            last_settlement.get("terminalProfitabilityAuthority")
            or settlement_profitability.get("terminalProfitabilityAuthority")
        )
        terminal_profitability = self._safe_dict(
            last_settlement.get("terminalProfitability")
            or settlement_profitability.get("terminalProfitability")
        )
        capital_admission = self._safe_dict(
            last_settlement.get("capitalAdmission")
            or settlement_profitability.get("capitalAdmission")
        )
        if capital_admission:
            capital_admission.setdefault(
                "stateContract",
                {
                    "phase": "capital_admission",
                    "status": (
                        "ok"
                        if capital_admission.get("allowed", capital_admission.get("ok", True))
                        else "blocked"
                    ),
                    "reason_code": str(
                        capital_admission.get("reason_code")
                        or capital_admission.get("reason")
                        or (
                            "ok"
                            if capital_admission.get("allowed", capital_admission.get("ok", True))
                            else "denied"
                        )
                    ),
                    "degraded": False,
                    "blocked": not bool(
                        capital_admission.get("allowed", capital_admission.get("ok", True))
                    ),
                    "denied": not bool(
                        capital_admission.get("allowed", capital_admission.get("ok", True))
                    ),
                    "sticky_cycle": True,
                    "details": dict(capital_admission.get("details") or {}),
                },
            )
        return to_json_safe(
            {
                "ok": True,
                "navUsd": float(round(nav_usd, 6)),
                "navSource": nav_source,
                "deployableUsd": float(round(deployable_usd, 6)),
                "reserveUsd": float(round(reserve_usd, 6)),
                "experimentalUsd": float(round(experimental_usd, 6)),
                "drawdownBufferUsd": float(round(drawdown_buffer_usd, 6)),
                "treasuryOfframpUsd": float(round(treasury_offramp_usd, 6)),
                "estimatedCapitalUsd": float(round(estimated_capital_usd, 6)),
                "deployedCapitalUsd": float(round(deployed_capital_usd, 6)),
                "utilizationPct": float(
                    round(
                        self._safe_float(treasury_meta.get("utilization_rate"), active_pct / 100.0)
                        * 100.0,
                        4,
                    )
                ),
                "exposure": {
                    "activePct": active_pct,
                    "sandboxPct": sandbox_pct,
                    "idlePct": idle_pct,
                    "atRiskPct": at_risk_pct,
                },
                "ledger": ledger_state,
                "bankroll": {
                    "realizedProfitWei": int(
                        getattr(bankroll_state, "realized_profit_wei", 0) or 0
                    ),
                    "lastAmountInWei": int(getattr(bankroll_state, "last_amount_in_wei", 0) or 0),
                    "successStreak": int(getattr(bankroll_state, "success_streak", 0) or 0),
                    "failStreak": int(getattr(bankroll_state, "fail_streak", 0) or 0),
                    "updatedTsMs": int(getattr(bankroll_state, "updated_ts_ms", 0) or 0),
                    "profitUpdatedTsMs": int(
                        getattr(bankroll_state, "profit_updated_ts_ms", 0) or 0
                    ),
                    "sizingUpdatedTsMs": int(
                        getattr(bankroll_state, "sizing_updated_ts_ms", 0) or 0
                    ),
                },
                "treasury": {
                    "snapshot": treasury_snapshot,
                    "meta": treasury_meta,
                    "capitalEngine": capital_engine,
                    "reinvestmentPolicy": reinvestment_policy,
                    "capitalEfficiencyMetrics": capital_metrics,
                },
                "lastSettlement": last_settlement,
                "terminalProfitabilityAuthority": terminal_authority,
                "terminalProfitability": terminal_profitability,
                "capitalAdmission": capital_admission,
                "profitabilityChain": settlement_profitability,
                "internalPrime": {"borrowedUsd": float(round(borrowed_usd, 6))},
                "allocations": allocations,
                "familyCapitalPlanVersion": FAMILY_CAPITAL_PLAN_VERSION,
                "familyCapitalPlan": allocations,
                "capitalFlows": capital_flows,
                "alerts": [],
            }
        )

    def _build_capital_contract(self, capital_summary: Dict[str, Any]) -> Dict[str, Any]:
        summary = dict(capital_summary or {})
        return to_json_safe(
            {
                "ok": True,
                "contractVersion": CAPITAL_CONTRACT_VERSION,
                "navUsd": self._safe_float(summary.get("navUsd")),
                "navSource": str(summary.get("navSource") or "unavailable"),
                "deployableUsd": self._safe_float(summary.get("deployableUsd")),
                "estimatedCapitalUsd": self._safe_float(summary.get("estimatedCapitalUsd")),
                "deployedCapitalUsd": self._safe_float(summary.get("deployedCapitalUsd")),
                "utilizationPct": self._safe_float(summary.get("utilizationPct")),
                "exposure": dict(summary.get("exposure") or {}),
                "lastSettlement": dict(summary.get("lastSettlement") or {}),
                "terminalProfitabilityAuthority": dict(
                    summary.get("terminalProfitabilityAuthority") or {}
                ),
                "terminalProfitability": dict(summary.get("terminalProfitability") or {}),
                "capitalAdmission": dict(summary.get("capitalAdmission") or {}),
                "profitabilityChain": dict(summary.get("profitabilityChain") or {}),
                "alerts": list(summary.get("alerts") or []),
                "internalPrime": dict(summary.get("internalPrime") or {}),
                "allocations": list(summary.get("allocations") or []),
                "capitalFlows": list(summary.get("capitalFlows") or []),
                "capitalSummary": summary,
            }
        )

    def _build_capital_policy(
        self, runtime: Any, capital_summary: Dict[str, Any], capital_contract: Dict[str, Any]
    ) -> Dict[str, Any]:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        paused = bool(getattr(controls, "paused", False)) if controls is not None else False
        sandbox_only = (
            bool(getattr(controls, "sandbox_only", False)) if controls is not None else False
        )
        defensive_mode = (
            bool(getattr(controls, "defensive_mode", False)) if controls is not None else False
        )
        allocations_frozen = (
            bool(getattr(controls, "allocations_frozen", False)) if controls is not None else False
        )
        reduce_exposure_half = (
            bool(getattr(controls, "reduce_exposure_half", False))
            if controls is not None
            else False
        )
        deployable_usd = self._safe_float(capital_summary.get("deployableUsd"))
        nav_source = str(capital_summary.get("navSource") or "unavailable")
        launch_blockers = []
        auto_blockers = []
        full_system_blockers = []
        aggressive_blockers = []
        if nav_source == "unavailable":
            launch_blockers.append("capital_nav_unavailable")
            auto_blockers.append("capital_nav_unavailable")
            full_system_blockers.append("capital_nav_unavailable")
        if deployable_usd <= 0:
            launch_blockers.append("deployable_capital_unavailable")
            auto_blockers.append("deployable_capital_unavailable")
            full_system_blockers.append("deployable_capital_unavailable")
        if paused:
            auto_blockers.append("paused")
        if sandbox_only:
            full_system_blockers.append("sandbox_only")
        if allocations_frozen:
            launch_blockers.append("allocations_frozen")
            auto_blockers.append("allocations_frozen")
            full_system_blockers.append("allocations_frozen")
        if defensive_mode or reduce_exposure_half:
            aggressive_blockers.append("defensive_mode_active")
        max_aggression_mode = (
            "conservative"
            if defensive_mode or reduce_exposure_half
            else ("balanced" if aggressive_blockers else "aggressive")
        )
        return to_json_safe(
            {
                "ok": True,
                "contractVersion": CAPITAL_POLICY_VERSION,
                "enforced": True,
                "navUsd": self._safe_float(capital_summary.get("navUsd")),
                "navSource": nav_source,
                "deployableUsd": deployable_usd,
                "estimatedCapitalUsd": self._safe_float(capital_summary.get("estimatedCapitalUsd")),
                "utilizationPct": self._safe_float(capital_summary.get("utilizationPct")),
                "capitalContractVersion": str(capital_contract.get("contractVersion") or ""),
                "controls": {
                    "paused": paused,
                    "sandboxOnly": sandbox_only,
                    "allocationsFrozen": allocations_frozen,
                    "defensiveMode": defensive_mode,
                    "reduceExposureHalf": reduce_exposure_half,
                },
                "commandCenter": {
                    "autoAllowed": not auto_blockers,
                    "autoBlockers": auto_blockers,
                    "fullSystemAllowed": not full_system_blockers,
                    "fullSystemBlockers": full_system_blockers,
                    "maxAggressionMode": max_aggression_mode,
                    "aggressiveModeBlockers": aggressive_blockers,
                },
                "launch": {
                    "enableAllowed": not launch_blockers,
                    "enableBlockers": launch_blockers,
                    "modeChangeAllowed": not full_system_blockers,
                    "modeChangeBlockers": full_system_blockers,
                },
                "warnings": [],
                "capitalContract": capital_contract,
                "capitalSummary": capital_summary,
                "familyCapitalPlanVersion": FAMILY_CAPITAL_PLAN_VERSION,
                "familyCapitalPlan": list(capital_summary.get("familyCapitalPlan") or []),
            }
        )

    def _build_capital_economic_model(
        self, runtime: Any, capital_summary: Dict[str, Any]
    ) -> Dict[str, Any]:
        chain_cfg = getattr(getattr(runtime, "cfg", None), "chain", None)
        chain_name = str(getattr(chain_cfg, "name", "") or "")
        return to_json_safe(
            {
                "ok": True,
                "modelVersion": CAPITAL_ECONOMIC_MODEL_VERSION,
                "inputs": {"runtime": {"chain": chain_name}},
                "resolved": dict(capital_summary or {}),
                "allocations": list((capital_summary or {}).get("allocations") or []),
                "capitalFlows": list((capital_summary or {}).get("capitalFlows") or []),
                "alerts": list((capital_summary or {}).get("alerts") or []),
            }
        )

    def capital_truth(self, runtime: Any) -> CapitalTruthSnapshot:
        capital_summary = self._build_capital_summary(runtime)
        capital_contract = self._build_capital_contract(capital_summary)
        capital_policy = self._build_capital_policy(runtime, capital_summary, capital_contract)
        capital_economic_model = self._build_capital_economic_model(runtime, capital_summary)
        authority = to_json_safe(
            {
                "ok": True,
                "mode": LIVE_CAPITAL_AUTHORITY_MODE,
                "executionAuthority": bool(
                    (capital_policy.get("commandCenter") or {}).get("autoAllowed", True)
                ),
                "persistedRead": False,
                "updatedTsMs": int(time.time() * 1000),
                "modelVersion": CAPITAL_ECONOMIC_MODEL_VERSION,
                "contractVersion": CAPITAL_CONTRACT_VERSION,
                "policyVersion": CAPITAL_POLICY_VERSION,
            }
        )
        return CapitalTruthSnapshot(
            capital_summary=capital_summary,
            capital_contract=capital_contract,
            capital_policy=capital_policy,
            capital_economic_model=capital_economic_model,
            authority=authority,
        )

    def capital_summary(self, runtime: Any) -> Dict[str, Any]:
        return self.capital_truth(runtime).capital_summary

    def capital_contract(self, runtime: Any) -> Dict[str, Any]:
        return self.capital_truth(runtime).capital_contract

    def capital_policy(self, runtime: Any) -> Dict[str, Any]:
        try:
            return self.capital_truth(runtime).capital_policy
        except _SAFE_STATE_EXCEPTIONS as exc:
            capital_summary = {
                "ok": False,
                "navUsd": 0.0,
                "navSource": "unavailable",
                "deployableUsd": 0.0,
                "estimatedCapitalUsd": 0.0,
                "deployedCapitalUsd": 0.0,
                "utilizationPct": 0.0,
                "exposure": {},
                "alerts": ["capital_truth_unavailable"],
            }
            capital_contract = self._build_capital_contract(capital_summary)
            capital_policy = self._build_capital_policy(runtime, capital_summary, capital_contract)
            warnings = [str(x) for x in list(capital_policy.get("warnings") or []) if str(x)]
            if "capital_truth_unavailable" not in warnings:
                warnings.append("capital_truth_unavailable")
            capital_policy.update(
                {
                    "ok": False,
                    "status": "degraded",
                    "reason_code": "capital_truth_unavailable",
                    "reason": "capital_truth_unavailable",
                    "error": f"capital_truth_unavailable:{exc}",
                    "warnings": warnings,
                    "capitalSummary": capital_summary,
                    "capitalContract": capital_contract,
                    "capitalContractVersion": str(
                        capital_contract.get("contractVersion") or CAPITAL_CONTRACT_VERSION
                    ),
                }
            )
            return to_json_safe(capital_policy)

    def metrics_state(self, runtime: Any) -> Dict[str, Any]:
        eff: Dict[str, Any] = {}
        try:
            eff_store = getattr(runtime, "_eff", None)
            if eff_store is not None and hasattr(eff_store, "snapshot"):
                eff = self._safe_dict(eff_store.snapshot())
        except _SAFE_STATE_EXCEPTIONS:
            eff = {}
        try:
            metrics = getattr(runtime, "metrics", None)
            bankroll = getattr(runtime, "_bankroll", None)
            bankroll_state = getattr(bankroll, "state", None)
            success_rate_pct = (
                float(bankroll.success_rate_pct() / 100.0) if bankroll is not None else 0.0
            )
            return {
                "last_block": int(getattr(metrics, "last_block", 0) or 0),
                "scan_ms": float(getattr(metrics, "scan_ms", 0.0) or 0.0),
                "success_rate": success_rate_pct,
                "fail_streak": int(getattr(bankroll_state, "fail_streak", 0) or 0),
                "gas_mode": str(getattr(metrics, "gas_mode", "standard")),
                "send_mode": str(getattr(metrics, "send_mode", "public")),
                "basefee_gwei": float(getattr(metrics, "basefee_gwei", 0.0) or 0.0),
                "opportunity_rate": float(getattr(metrics, "opportunity_rate", 0.0) or 0.0),
                "realized_profit_raw": str(getattr(metrics, "realized_profit_raw", "0") or "0"),
                "efficiency_pct": float(eff.get("efficiency_pct", 0.0) or 0.0),
            }
        except _SAFE_STATE_EXCEPTIONS:
            return {}

    def wealth_goal_state(self, runtime: Any) -> Dict[str, Any]:
        service = getattr(runtime, "_wealth_goal_service", None)
        if service is None or not hasattr(service, "state"):
            return self._unavailable_payload(
                "wealth_goal_service_unavailable",
                ok=False,
                extra={"state": {}, "history": [], "explanation": {}, "recommendation": {}},
            )
        try:
            return to_json_safe(service.state(runtime))
        except _SAFE_STATE_EXCEPTIONS:
            return self._unavailable_payload(
                "wealth_goal_service_unavailable",
                ok=False,
                extra={"state": {}, "history": [], "explanation": {}, "recommendation": {}},
            )

    def research_pipeline_state(self, runtime: Any) -> Dict[str, Any]:
        store = getattr(runtime, "_research_candidates", None)
        if store is None:
            return {"items": [], "pipelineCounts": {}, "throughput": {}}
        try:
            return to_json_safe(
                {
                    "items": store.items(),
                    "pipelineCounts": store.pipeline_counts(),
                    "throughput": store.throughput_metrics(),
                }
            )
        except _SAFE_PERSISTENCE_EXCEPTIONS:
            return {"items": [], "pipelineCounts": {}, "throughput": {}}

    def doctrine_state(self, runtime: Any) -> Dict[str, Any]:
        del runtime
        try:
            return to_json_safe(doctrine_snapshot())
        except _SAFE_STATE_EXCEPTIONS:
            return {"optimizationObjectives": {}}

    def ledger_state(self, runtime: Any) -> Dict[str, Any]:
        chain = str(
            getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or ""
        )
        repo = getattr(runtime, "_ledger_repo", None)
        ledger = getattr(runtime, "_ledger", None)
        try:
            if repo is not None and hasattr(repo, "tail"):
                tail = repo.tail(chain=chain, limit=50)
            else:
                tail = ledger.tail(50) if ledger is not None and hasattr(ledger, "tail") else []
        except _SAFE_PERSISTENCE_EXCEPTIONS:
            tail = []
        try:
            if repo is not None and hasattr(repo, "transactions_tail"):
                transactions = repo.transactions_tail(chain=chain, limit=50)
            else:
                transactions = (
                    ledger.transactions_tail(50)
                    if ledger is not None and hasattr(ledger, "transactions_tail")
                    else []
                )
        except _SAFE_PERSISTENCE_EXCEPTIONS:
            transactions = []
        balance_report: Dict[str, Any] = {}
        try:
            if repo is not None and hasattr(repo, "transaction_balance_report"):
                balance_report = dict(repo.transaction_balance_report(chain=chain) or {})
            elif ledger is not None and hasattr(ledger, "balance_report"):
                balance_report = dict(ledger.balance_report() or {})
        except _SAFE_PERSISTENCE_EXCEPTIONS:
            balance_report = {}
        if not balance_report:
            try:
                balances = (
                    ledger.balances() if ledger is not None and hasattr(ledger, "balances") else {}
                )
            except _SAFE_PERSISTENCE_EXCEPTIONS:
                balances = {}
            balance_report = {
                "balances": balances,
                "balanceSource": "unknown",
                "transactionCount": 0,
                "legacyEntryCount": 0,
                "accountBalances": {},
                "accounting": {},
            }
        last_settlement = self._safe_dict(getattr(runtime, "_last_settlement_sync", {}))
        return {
            "balances": to_json_safe(balance_report.get("balances") or {}),
            "accountBalances": to_json_safe(balance_report.get("accountBalances") or {}),
            "accounting": to_json_safe(balance_report.get("accounting") or {}),
            "tail": to_json_safe(tail),
            "transactions": to_json_safe(transactions),
            "balanceSource": str(balance_report.get("balanceSource") or "unknown"),
            "transactionCount": int(balance_report.get("transactionCount") or 0),
            "legacyEntryCount": int(balance_report.get("legacyEntryCount") or 0),
            "lastSettlement": to_json_safe(last_settlement),
        }

    def internal_prime_state(self, runtime: Any) -> Dict[str, Any]:
        default = {
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
            "stateReady": False,
            "stateStatus": "unavailable",
            "stateReasonCode": "internal_prime_unavailable",
            "stateReason": "internal_prime_unavailable",
        }
        allocator = getattr(runtime, "_internal_prime", None)
        if allocator is None or not hasattr(allocator, "snapshot"):
            return unavailable_state("internal_prime_unavailable", extra=default)
        try:
            payload = allocator.snapshot()
        except _SAFE_PERSISTENCE_EXCEPTIONS:
            return unavailable_state(
                "internal_prime_state_unavailable",
                extra={
                    **default,
                    "stateReasonCode": "internal_prime_state_unavailable",
                    "stateReason": "internal_prime_state_unavailable",
                },
            )
        if not isinstance(payload, dict):
            return unavailable_state("internal_prime_state_unavailable", extra=default)
        normalized = dict(payload)
        normalized.setdefault("borrowedUsd", 0.0)
        normalized.setdefault("capacityUsd", 0.0)
        normalized.setdefault("utilization", 0.0)
        normalized.setdefault("inventory", {})
        normalized.setdefault("familyExposure", {})
        normalized.setdefault("openLoans", [])
        normalized.setdefault("disputedLoans", [])
        normalized.setdefault("loanCount", 0)
        normalized.setdefault("disputedLoanCount", 0)
        normalized.setdefault("stateReady", True)
        normalized.setdefault(
            "stateStatus", "ok" if normalized.get("stateReady", True) else "unavailable"
        )
        normalized.setdefault(
            "stateReasonCode",
            "" if normalized.get("stateReady", True) else "internal_prime_state_unavailable",
        )
        normalized.setdefault(
            "stateReason",
            normalized.get("stateReasonCode")
            or ("" if normalized.get("stateReady", True) else "internal_prime_state_unavailable"),
        )
        return to_json_safe(normalized)

    def cio_summary_state(self, runtime: Any) -> Dict[str, Any]:
        service = getattr(runtime, "_cio_service", None)
        if service is None or not hasattr(service, "summary"):
            return self._unavailable_payload("cio_service_unavailable", ok=False)
        try:
            return to_json_safe(service.summary(runtime))
        except _SAFE_STATE_EXCEPTIONS:
            return self._unavailable_payload("cio_service_unavailable", ok=False)

    def unified_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_snapshot(getattr(runtime, "_feature_bus", None))

    def spread_opportunities(self, runtime: Any) -> Dict[str, Any]:
        try:
            raw_items = self._iter_rows(getattr(runtime, "_spread_opps", []))
            items: list[Any] = []
            for item in raw_items:
                try:
                    items.append(item.as_dict() if hasattr(item, "as_dict") else dict(item))
                except _SAFE_STATE_EXCEPTIONS:
                    continue
            return to_json_safe(
                {
                    "ok": True,
                    "count": int(len(list(getattr(runtime, "_spread_opps", []) or []))),
                    "opps": items,
                    "last": self._safe_dict(getattr(runtime, "_spread_last", {})),
                }
            )
        except _SAFE_STATE_EXCEPTIONS:
            return {"ok": True, "count": 0, "opps": []}

    def consensus_state(self, runtime: Any) -> Dict[str, Any]:
        try:
            execution_cfg = getattr(getattr(runtime, "cfg", None), "execution", None)
            consensus_cfg = getattr(execution_cfg, "consensus", None)
            return to_json_safe(
                {
                    "ok": True,
                    "last": self._safe_dict(getattr(runtime, "_consensus_last", {})),
                    "cfg": getattr(consensus_cfg, "__dict__", {}),
                }
            )
        except _SAFE_STATE_EXCEPTIONS:
            return {"ok": True, "last": {}}

    def orchestrator_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_snapshot(getattr(runtime, "_orchestrator", None))

    def behaveagent_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_snapshot(getattr(runtime, "_behave", None))

    def treasury_state(
        self, runtime: Any, capital_truth: CapitalTruthSnapshot | None = None
    ) -> Dict[str, Any]:
        direct_payload: Dict[str, Any] | None = None
        guard_name = "_treasury_state_direct_read_in_progress"
        method = getattr(runtime, "treasury_state", None)
        if callable(method) and not bool(getattr(runtime, guard_name, False)):
            try:
                setattr(runtime, guard_name, True)
                direct_value = method()
                if isinstance(direct_value, Mapping):
                    direct_payload = dict(direct_value)
                elif direct_value is not None:
                    direct_payload = dict(direct_value)
            except _SAFE_STATE_EXCEPTIONS:
                direct_payload = None
            finally:
                try:
                    setattr(runtime, guard_name, False)
                except _SAFE_STATE_EXCEPTIONS:
                    pass
        payload = direct_payload or self._optional_snapshot(getattr(runtime, "_treasury", None))
        context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=self,
        )
        truth = capital_truth or context.capital_truth
        payload.setdefault("ok", True)
        payload.setdefault(
            "enabled", bool(getattr(runtime, "_treasury", None) is not None or direct_payload)
        )
        payload["capitalSummary"] = dict(context.capital_summary or truth.capital_summary or {})
        payload["capitalContract"] = dict(context.capital_contract or truth.capital_contract or {})
        payload["capitalContractVersion"] = CAPITAL_CONTRACT_VERSION
        payload["capitalPolicy"] = dict(context.capital_policy or truth.capital_policy or {})
        payload["capitalPolicyVersion"] = CAPITAL_POLICY_VERSION
        payload["capitalTruthHealth"] = dict(context.capital_truth_health or {})
        payload["ledger"] = self.ledger_state(runtime)
        payload["ledger"]["lastSettlement"] = dict(
            (truth.capital_summary or {}).get("lastSettlement") or {}
        )
        payload["terminalProfitabilityAuthority"] = dict(
            (truth.capital_summary or {}).get("terminalProfitabilityAuthority") or {}
        )
        payload["terminalProfitability"] = dict(
            (truth.capital_summary or {}).get("terminalProfitability") or {}
        )
        payload["capitalAdmission"] = dict(
            (truth.capital_summary or {}).get("capitalAdmission") or {}
        )
        payload["profitabilityChain"] = dict(
            (truth.capital_summary or {}).get("profitabilityChain") or {}
        )
        payload["serviceContracts"] = {
            "capitalPolicy": dict(context.capital_policy or truth.capital_policy or {}),
            "capitalTruth": dict(payload["capitalTruthHealth"].get("stateContract") or {}),
            "runtimeDisable": normalize_surface_contract(
                payload,
                phase="treasury",
                default_reason=str(payload.get("reason_code") or "ok"),
            ),
        }
        payload["stateContract"] = payload["serviceContracts"]["runtimeDisable"].get(
            "stateContract"
        )
        return to_json_safe(payload)

    def governance_layer_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_snapshot(getattr(runtime, "_gov", None))

    def blockspace_state(self, runtime: Any) -> Dict[str, Any]:
        return self._optional_snapshot(getattr(runtime, "_blockspace", None))

    def quicksight_state(self, runtime: Any) -> Dict[str, Any]:
        return self._quicksight_payload(
            runtime,
            lambda qs: to_json_safe(qs.state()),
            disabled_payload=self._unavailable_payload(
                "quicksight_unavailable",
                ok=False,
                include_error=True,
                extra={"enabled": False},
            ),
            failure_reason_code="quicksight_state_failed",
            failure_fallback={"enabled": False},
        )

    @staticmethod
    def _quicksight_payload(
        runtime: Any,
        action: Callable[[Any], Any],
        *,
        disabled_payload: Dict[str, Any] | None = None,
        failure_reason_code: str,
        failure_fallback: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        quicksight = getattr(runtime, "_quicksight", None)
        if quicksight is None:
            return dict(
                disabled_payload
                or AuxiliaryStateService._unavailable_payload(
                    "quicksight_unavailable", ok=False, include_error=True
                )
            )
        try:
            return to_json_safe(action(quicksight))
        except _SAFE_STATE_EXCEPTIONS:
            return AuxiliaryStateService._degraded_payload(
                failure_reason_code,
                extra=dict(failure_fallback or {}),
            )

    def quicksight_dataset(self, runtime: Any, name: str) -> Dict[str, Any]:
        dataset = str(name)
        return self._quicksight_payload(
            runtime,
            lambda qs: {
                "ok": True,
                "dataset": dataset,
                "rows": to_json_safe(qs.get_dataset(dataset)),
            },
            failure_reason_code="quicksight_dataset_failed",
            failure_fallback={"dataset": dataset, "rows": []},
        )

    def quicksight_dashboards(self, runtime: Any) -> Dict[str, Any]:
        return self._quicksight_payload(
            runtime,
            lambda qs: {"ok": True, "dashboards": to_json_safe(qs.get_dashboards())},
            failure_reason_code="quicksight_dashboards_failed",
            failure_fallback={"dashboards": []},
        )

    def quicksight_ask(
        self, runtime: Any, *, question: str, role: str, token: str
    ) -> Dict[str, Any]:
        return self._quicksight_payload(
            runtime,
            lambda qs: qs.ask(question=str(question), role=str(role), token=str(token)),
            failure_reason_code="quicksight_ask_failed",
        )

    def quicksight_scenario(
        self, runtime: Any, *, params: Dict[str, Any], role: str, token: str
    ) -> Dict[str, Any]:
        return self._quicksight_payload(
            runtime,
            lambda qs: qs.scenario(params=dict(params or {}), role=str(role), token=str(token)),
            failure_reason_code="quicksight_scenario_failed",
        )

    def agent_hub_state(self, runtime: Any, *, agent_attribution: Dict[str, Any]) -> Dict[str, Any]:
        weights: Dict[str, Any] = {}
        weighting = getattr(runtime, "_agent_weighting", None)
        if weighting is not None and hasattr(weighting, "snapshot"):
            try:
                weights = to_json_safe(weighting.snapshot())
            except _SAFE_STATE_EXCEPTIONS:
                weights = {}
        return to_json_safe(
            {
                "ok": True,
                "state": self._safe_dict(getattr(runtime, "_agent_hub_last", {})),
                "attribution": dict(agent_attribution or {}),
                "weights": weights,
            }
        )
