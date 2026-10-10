from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from urllib.parse import urlsplit

from ..jsonsafe import to_json_safe
from .control_state import unavailable_state
from .runtime_context import public_mode_for_capture as service_public_mode_for_capture
from .fund_service import fund_summary_unavailable_payload
from .family_hardening_service import family_hardening_unavailable_summary

_RUNTIME_STATE_FACADE_FAILURES = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)


def _safe_provider_host(value: Any) -> str:
    """Reduce an endpoint string to a host-only label for public diagnostics."""
    raw = str(value or "").strip()
    try:
        host = urlsplit(raw).hostname
    except ValueError:
        host = None
    if host:
        return str(host)[:128]
    if "://" in raw:
        return "unknown"
    # Compatibility with bare host labels; never retain userinfo, path, or query.
    label = raw.rsplit("@", 1)[-1].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return label[:128] or "unknown"


def _safe_rpc_error_kind(value: Any) -> str:
    """Replace raw provider errors with stable categories safe for a public API."""
    message = str(value or "").lower()
    if any(token in message for token in ("429", "rate limit", "rate_limited")):
        return "rpc_rate_limited"
    if "timeout" in message or "timed out" in message:
        return "rpc_timeout"
    if any(token in message for token in ("connection", "transport", "ssl", "network")):
        return "rpc_transport_or_provider_error"
    if "revert" in message:
        return "quote_reverted"
    return "provider_error"


def _sanitize_rpc_telemetry(value: Any, key: str = "") -> Any:
    """Sanitize nested public RPC telemetry, retaining metrics but removing secrets."""
    lower_key = str(key).lower()
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize_rpc_telemetry(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_rpc_telemetry(item, key) for item in value]
    if isinstance(value, str):
        if lower_key in {"error", "last_error", "quote_last_error", "error_message", "error_text"}:
            return _safe_rpc_error_kind(value) if value else value
        if "://" in value or any(part in lower_key for part in ("url", "endpoint", "uri")):
            return _safe_provider_host(value)
    return value


def _gas_price_integrity_summary(value: Any) -> Dict[str, Any]:
    """Expose useful gas-consensus diagnostics without leaking RPC URLs or credentials."""
    if not isinstance(value, dict):
        return {}

    def _int_or_none(raw: Any) -> int | None:
        try:
            return int(raw)
        except (TypeError, ValueError, OverflowError):
            return None

    raw_observations = [
        row for row in list(value.get("observations") or []) if isinstance(row, dict)
    ][:8]
    observations: list[Dict[str, Any]] = []
    for raw in raw_observations:
        url = str(raw.get("url") or "")
        host = ""
        if url:
            try:
                host = str(urlsplit(url).hostname or "")
            except ValueError:
                host = ""
        if not host:
            # Provider labels from RpcManager are normally hostnames. Strip
            # userinfo, paths, and query strings defensively for compatibility.
            host = _safe_provider_host(raw.get("provider"))
        block_number = _int_or_none(raw.get("block_number"))
        price = _int_or_none(raw.get("gas_price_wei"))
        error_present = bool(raw.get("error"))
        observations.append({
            "provider": host[:128] or "unknown",
            "block_number": block_number,
            "gas_price_wei": str(price) if price is not None and price > 0 else None,
            "ok": bool(
                block_number is not None
                and block_number >= 0
                and price is not None
                and price > 0
                and not error_present
            ),
            "error_present": error_present,
        })

    anomaly_reasons: Dict[str, int] = {}
    for row in list(value.get("anomalies") or []):
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "unspecified")[:80]
        anomaly_reasons[reason] = anomaly_reasons.get(reason, 0) + 1

    selected_price = _int_or_none(value.get("gas_price_wei"))
    provider_count = _int_or_none(value.get("provider_count"))
    observed_at = value.get("observed_at")
    try:
        observed_at = float(observed_at) if observed_at is not None else None
    except (TypeError, ValueError, OverflowError):
        observed_at = None

    return {
        "status": str(value.get("status") or "unknown")[:48],
        "gas_price_wei": (
            str(selected_price) if selected_price is not None and selected_price > 0 else None
        ),
        "provider_count": max(
            0,
            provider_count if provider_count is not None else len(raw_observations),
        ),
        "usable_observation_count": sum(1 for row in observations if row["ok"]),
        "inlier_count": len(
            [row for row in list(value.get("inliers") or []) if isinstance(row, dict)]
        ),
        "observed_at": observed_at,
        "observations": observations,
        "anomaly_reason_counts": anomaly_reasons,
    }


class RuntimeStateFacade:
    @staticmethod
    def _unavailable_state(reason_code: str, *, extra: Optional[Dict[str, Any]] = None, include_reason: bool = True, include_error: bool = False, include_text: bool = False) -> Dict[str, Any]:
        return unavailable_state(reason_code, extra=extra, include_reason=include_reason, include_error=include_error, include_text=include_text)

    def _auxiliary_state_payload(self, method_name: str, *, default: Dict[str, Any], args: tuple[Any, ...] = (), kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        service = getattr(self, "_auxiliary_state_service", None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = getattr(service, method_name)(self, *args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    def _service_payload(self, service_attr: str, *, method_name: str, default: Dict[str, Any], args: tuple[Any, ...] = (), kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        service = getattr(self, service_attr, None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = getattr(service, method_name)(*args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    async def _async_service_payload(self, service_attr: str, *, method_name: str, default: Dict[str, Any], args: tuple[Any, ...] = (), kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        service = getattr(self, service_attr, None)
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(default))
        try:
            payload = await getattr(service, method_name)(*args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(default))
        return to_json_safe(payload)

    def _state_summary_payload(self, method_name: str, *, default: Dict[str, Any], default_factory: Optional[Callable[[], Dict[str, Any]]] = None, args: tuple[Any, ...] = (), kwargs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        service = getattr(self, "_state_summary_service", None)
        def fallback() -> Dict[str, Any]:
            return default_factory() if default_factory is not None else default
        if service is None or not hasattr(service, method_name):
            return to_json_safe(dict(fallback()))
        try:
            payload = getattr(service, method_name)(self, *args, **(kwargs or {}))
        except _RUNTIME_STATE_FACADE_FAILURES:
            return to_json_safe(dict(fallback()))
        return to_json_safe(payload)

    def market_pipeline_telemetry_state(self) -> Dict[str, Any]:
        """Read-only market-pipeline observability; never grants execution authority."""
        telemetry = dict(getattr(self, "_market_pipeline_telemetry", {}) or {})
        opportunities = list(getattr(self, "_opps", []) or [])
        verified = 0
        positive = 0
        route_ready = 0
        route_degraded = 0
        for opportunity in opportunities:
            meta = dict(getattr(opportunity, "meta", {}) or {})
            profitability = meta.get("profitability") if isinstance(meta.get("profitability"), dict) else {}
            if bool(profitability.get("revalidated")) and bool(profitability.get("authoritative")):
                verified += 1
                try:
                    if int(profitability.get("profitAfterCostsUsdMicroInt") or profitability.get("profit_after_costs_usd_micro") or 0) > 0:
                        positive += 1
                except (TypeError, ValueError):
                    pass
            runtime = meta.get("execution_route_runtime") if isinstance(meta.get("execution_route_runtime"), dict) else {}
            if bool(runtime.get("ready")):
                route_ready += 1
            if bool(runtime.get("degraded")):
                route_degraded += 1
        quotes = dict(telemetry.get("quotes") or {})
        selected_adaptive = dict(
            telemetry.get("selected_provider_adaptive") or {}
        )
        scan_sizing = dict(
            telemetry.get("scan_sizing")
            or selected_adaptive.get("scan_sizing")
            or {}
        )
        requests = int(quotes.get("requests") or 0)
        successes = int(quotes.get("successes") or 0)
        discovery = dict(telemetry.get("discovery") or {})
        payload = to_json_safe({
            "ok": True,
            "chain": str(getattr(getattr(self, "cfg", None), "chain", None) and getattr(self.cfg.chain, "name", "") or ""),
            "scanner": {
                "alive": bool(telemetry.get("last_scan")),
                "last_scan": telemetry.get("last_scan"),
                "last_block": telemetry.get("last_block"),
                "scan_latency_ms": telemetry.get("scan_latency_ms"),
                "scan_error": str(telemetry.get("scan_error") or ""),
                "runtime_loop": dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                "pool_event_state": (
                    dict(getattr(self, "_pool_event_cache", None).snapshot() or {})
                    if getattr(self, "_pool_event_cache", None) is not None
                    and callable(getattr(getattr(self, "_pool_event_cache", None), "snapshot", None))
                    else {}
                ),
            },
            "discovery": {
                "pools_seen": int(discovery.get("pools_seen") or 0),
                "routes_considered": int(telemetry.get("routes_considered") or 0),
                "edges_generated": int(telemetry.get("edges_generated") or 0),
                "v3_pairs": int(discovery.get("v3_pairs") or 0),
                "curve_pools": int(discovery.get("curve_pools") or 0),
                "balancer_pools": int(discovery.get("balancer_pools") or 0),
                "constant_product_pools": int(discovery.get("constant_product_pools") or 0),
            },
            "candidate_token_discovery": dict(
                telemetry.get("candidate_token_discovery") or {}
            ),
            "rpc_selection_phase": str(telemetry.get("rpc_selection_phase") or ""),
            "rpc_selection_started_ms": telemetry.get("rpc_selection_started_ms"),
            "rpc_selection_completed_ms": telemetry.get("rpc_selection_completed_ms"),
            "rpc_provider_scan_timeout_s": telemetry.get("rpc_provider_scan_timeout_s"),
            "rpc_selection_progress": dict(
                telemetry.get("rpc_selection_progress") or {}
            ),
            "quotes": {
                "requests": requests,
                "successes": successes,
                "failures": max(0, requests - successes),
                "success_rate": (float(successes) / float(requests)) if requests else 0.0,
                "failure_reasons": dict(quotes.get("failure_reasons") or {}),
            },
            "scan_sizing": scan_sizing,
            "rpc": _sanitize_rpc_telemetry(telemetry.get("rpc") or {}),
            "gas_price_integrity": _gas_price_integrity_summary(
                telemetry.get("gas_price_integrity")
            ),
            "adaptive_size_discovery": dict(telemetry.get("adaptive_size_discovery") or {}),
            "size_economic_matrix": [
                dict(row) for row in (telemetry.get("size_economic_matrix") or [])
                if isinstance(row, dict)
            ],
            "size_economic_evidence": [
                dict(row) for row in (telemetry.get("size_economic_evidence") or [])
                if isinstance(row, dict)
            ],
            "size_economic_diagnostics": [
                dict(row) for row in (telemetry.get("size_economic_diagnostics") or [])
                if isinstance(row, dict)
            ],
            "route_universe": dict(telemetry.get("route_universe") or {}),
            "route_evaluation": dict(telemetry.get("route_evaluation") or {}),
            "route_rejections": dict(telemetry.get("route_rejections") or {}),
            "economics": {
                "gross_candidates": int(len(opportunities)),
                "after_fee_candidates": int(verified),
                "after_fee_positive_candidates": int(positive),
            },
            "liquidity": {
                "status": "candidate_scoped",
                "executable_depth": None,
                "max_size": None,
                "constrained_candidates": None,
            },
            "quality": {
                "route_quality": {"ready_candidates": route_ready, "degraded_candidates": route_degraded},
                "venue_quality": {"status": "candidate_scoped"},
                "provider_quality": {"status": "candidate_scoped"},
            },
            "admission": {
                "status": "see_canonical_execution_quality",
                "capital": None,
                "family": None,
                "treasury": None,
                "flashloan": None,
                "execution": None,
            },
        })
        economics = payload.get("economics", {})
        for key in ("gross_candidates", "after_fee_candidates", "after_fee_positive_candidates"):
            economics[key] = int(economics.get(key) or 0)

        # to_json_safe may normalize nested numeric values; restore the documented
        # numeric telemetry types explicitly at this public API boundary.
        gas_integrity = payload.get("gas_price_integrity", {})
        if isinstance(gas_integrity, dict):
            for key in ("provider_count", "usable_observation_count", "inlier_count"):
                try:
                    gas_integrity[key] = max(0, int(gas_integrity.get(key) or 0))
                except (TypeError, ValueError, OverflowError):
                    gas_integrity[key] = 0
            anomaly_counts = gas_integrity.get("anomaly_reason_counts", {})
            if isinstance(anomaly_counts, dict):
                for key, value in list(anomaly_counts.items()):
                    try:
                        anomaly_counts[key] = max(0, int(value or 0))
                    except (TypeError, ValueError, OverflowError):
                        anomaly_counts[key] = 0
            observations = gas_integrity.get("observations", [])
            if isinstance(observations, list):
                for observation in observations:
                    if not isinstance(observation, dict):
                        continue
                    if observation.get("block_number") is not None:
                        try:
                            observation["block_number"] = int(observation["block_number"])
                        except (TypeError, ValueError, OverflowError):
                            observation["block_number"] = None
                    observation["ok"] = bool(observation.get("ok"))
                    observation["error_present"] = bool(observation.get("error_present"))
        return payload

    def execution_capture_analytics(self) -> Dict[str, Any]: return self._state_summary_payload("execution_capture_analytics", default={"laneSuccess": [], "venueQuality": []})
    def telemetry_summary(self) -> Dict[str, Any]: return self._service_payload("_telemetry_service", method_name="summary", default={"realization": {"families": []}, "agents": {"agents": []}})
    def execution_calibration_state(self) -> Dict[str, Any]: return self._state_summary_payload("execution_calibration", default={"items": []})
    def venue_profiles_state(self) -> Dict[str, Any]: return self._state_summary_payload("venue_profiles", default={"venues": []})
    def endpoint_quality_state(self) -> Dict[str, Any]: return self._state_summary_payload("endpoint_quality", default={"lanes": {}, "relays": {}})
    def venue_scorecards_state(self) -> Dict[str, Any]: return self._state_summary_payload("venue_scorecards", default={"items": []})
    def endpoint_universe_state(self) -> Dict[str, Any]: return self._state_summary_payload("endpoint_universe", default={"read": {}, "public": {}, "protected": {}, "private": {}})
    def execution_live_state(self) -> Dict[str, Any]: return self._state_summary_payload("execution_live", default={"items": []})
    def route_quality_state(self) -> Dict[str, Any]: return self._state_summary_payload("route_quality", default={"items": []})
    def drawdown_state(self) -> Dict[str, Any]: return self._state_summary_payload("drawdown", default={"drawdownPct": 0.0, "intradayLossUsd": 0.0, "familyDrawdown": {}, "hardStop": {"active": False, "reason_codes": []}})
    def kill_switch_state(self) -> Dict[str, Any]: return self._state_summary_payload("kill_switch", default={"metrics": {}, "suppressions": {}, "history": []})
    def risk_memory_state(self) -> Dict[str, Any]: return self._state_summary_payload("risk_memory", default={"failures": {}})
    def path_diversity_state(self) -> Dict[str, Any]: return self._state_summary_payload("path_diversity", default={"paths": []})
    def edge_learning_state(self) -> Dict[str, Any]: return self._state_summary_payload("edge_learning", default={"items": [], "quarantine": {}, "explorationBudget": {}})
    def launch_state(self) -> Dict[str, Any]: return self._state_summary_payload("launch", default=self._unavailable_state("launch_service_unavailable"))
    def rpc_preferences_state(self) -> Dict[str, Any]: return self._state_summary_payload("rpc_preferences", default={"read": [], "send": [], "private": [], "configured": False})
    def strategy_scorecards_state(self) -> Dict[str, Any]: return self._state_summary_payload("strategy_scorecards", default={"families": []})
    def agent_attribution_state(self) -> Dict[str, Any]: return self._state_summary_payload("agent_attribution", default={"agents": []})
    def engine_state(self) -> Dict[str, Any]: return to_json_safe(dict(getattr(self, "_engine_last", {}) or {"items": [], "capabilities": {}, "summary": {"engines": []}}))
    def capital_engine_state(self) -> Dict[str, Any]: return self._state_summary_payload("capital_engine", default={"capital_engine": {}, "reinvestment_policy": {}, "capital_efficiency_metrics": {}})
    def fund_summary_state(self) -> Dict[str, Any]: return self._state_summary_payload("fund_summary", default={}, default_factory=lambda: {**fund_summary_unavailable_payload(None), "capitalTruth": unavailable_state("capital_truth_service_unavailable"), "researchPipeline": {"items": []}})
    def research_pipeline_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("research_pipeline_state", default={"items": [], "pipelineCounts": {}, "throughput": {}})
    def doctrine_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("doctrine_state", default={"optimizationObjectives": {}})
    def ledger_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("ledger_state", default={"balances": {}, "tail": [], "transactions": []})
    def internal_prime_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("internal_prime_state", default={"ok": False, "status": "unavailable", "reason_code": "internal_prime_unavailable", "reason": "internal_prime_unavailable", "borrowedUsd": 0.0, "capacityUsd": 0.0, "utilization": 0.0, "inventory": {}, "familyExposure": {}, "openLoans": [], "disputedLoans": [], "loanCount": 0, "disputedLoanCount": 0, "stateReady": False, "stateStatus": "unavailable", "stateReasonCode": "internal_prime_unavailable", "stateReason": "internal_prime_unavailable"})
    def cio_summary_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("cio_summary_state", default=self._unavailable_state("cio_service_unavailable"))
    def fund_state(self) -> Dict[str, Any]: return self.fund_summary_state()
    def family_hardening_state(self) -> Dict[str, Any]: return self._service_payload("_family_hardening_service", method_name="summary", default=family_hardening_unavailable_summary(), args=(self,))
    def capital_truth(self): return self._auxiliary_state_service.capital_truth(self)
    def capital_summary(self) -> Dict[str, Any]: return self.capital_truth().capital_summary
    def capital_contract(self) -> Dict[str, Any]: return self.capital_truth().capital_contract
    def capital_policy(self) -> Dict[str, Any]: return self._auxiliary_state_service.capital_policy(self)
    def capital_truth_state(self) -> Dict[str, Any]: return self._service_payload("_capital_truth_service", method_name="summary", default=self._unavailable_state("capital_truth_service_unavailable"), args=(self,))
    async def withdraw_all_state(self) -> Dict[str, Any]: return await self._async_service_payload("_withdraw_all_service", method_name="state", default=self._unavailable_state("withdraw_all_service_unavailable"), args=(self,))
    def metrics_state(self) -> dict:
        aux = getattr(self, "_auxiliary_state_service", None)
        if aux is None or not hasattr(aux, "metrics_state"): return {}
        try: return to_json_safe(aux.metrics_state(self))
        except _RUNTIME_STATE_FACADE_FAILURES: return {}
    def brain_state(self) -> dict:
        decision = getattr(self, "_decision", None)
        if decision is None or not hasattr(decision, "brain_state"): return {}
        try: return to_json_safe(decision.brain_state())
        except _RUNTIME_STATE_FACADE_FAILURES: return {}
    def unified_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("unified_state", default=self._unavailable_state("unified_state_unavailable", extra={"enabled": False}))
    def spread_opportunities(self) -> Dict[str, Any]: return self._auxiliary_state_payload("spread_opportunities", default=self._unavailable_state("spread_opportunities_unavailable", extra={"count": 0, "opps": []}))
    def consensus_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("consensus_state", default=self._unavailable_state("consensus_state_unavailable", extra={"last": {}}))
    def orchestrator_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("orchestrator_state", default=self._unavailable_state("orchestrator_state_unavailable", extra={"enabled": False}))
    def behaveagent_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("behaveagent_state", default=self._unavailable_state("behaveagent_state_unavailable", extra={"enabled": False}))
    def treasury_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("treasury_state", default={})
    def governance_layer_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("governance_layer_state", default=self._unavailable_state("governance_layer_unavailable", extra={"enabled": False}))
    def blockspace_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("blockspace_state", default=self._unavailable_state("blockspace_state_unavailable", extra={"enabled": False}))
    def quicksight_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("quicksight_state", default=self._unavailable_state("quicksight_unavailable", extra={"enabled": False}, include_error=True))
    def quicksight_dataset(self, name: str) -> Dict[str, Any]:
        dataset = str(name)
        return self._auxiliary_state_payload("quicksight_dataset", default=self._unavailable_state("quicksight_unavailable", extra={"dataset": dataset, "rows": []}, include_error=True), args=(dataset,))
    def quicksight_dashboards(self) -> Dict[str, Any]: return self._auxiliary_state_payload("quicksight_dashboards", default=self._unavailable_state("quicksight_unavailable", extra={"dashboards": []}, include_error=True))
    def quicksight_ask(self, question: str, role: str = "EXECUTIVE_VIEW", token: str = "") -> Dict[str, Any]: return self._auxiliary_state_payload("quicksight_ask", default=self._unavailable_state("quicksight_unavailable", include_error=True), kwargs={"question": str(question), "role": str(role), "token": str(token)})
    def quicksight_scenario(self, params: Dict[str, Any], role: str = "RISK_MANAGER", token: str = "") -> Dict[str, Any]: return self._auxiliary_state_payload("quicksight_scenario", default=self._unavailable_state("quicksight_unavailable", include_error=True), kwargs={"params": dict(params or {}), "role": str(role), "token": str(token)})
    def agent_hub_state(self) -> Dict[str, Any]: return self._auxiliary_state_payload("agent_hub_state", default=self._unavailable_state("agent_hub_state_unavailable", extra={"state": {}}), kwargs={"agent_attribution": self.agent_attribution_state()})
    def _public_mode_for_capture(self) -> bool: return service_public_mode_for_capture(self)
    def service_health_state(self) -> Dict[str, Any]: return self._state_summary_payload("service_health", default={"admission": self._unavailable_state("admission_service_unavailable"), "execution": self._unavailable_state("execution_service_unavailable"), "receipt": self._unavailable_state("receipt_service_unavailable"), "telemetry": self._unavailable_state("telemetry_service_unavailable")})
    def capital_explain(self, snapshot: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: return self._state_summary_payload("capital_explain", default=self._unavailable_state("capital_explanation_unavailable", extra={"facts": {}, "causal": {}}, include_reason=False, include_text=True), kwargs={"snapshot": snapshot or {}})
    def analytics_state(self) -> Dict[str, Any]: return self._state_summary_payload("analytics", default=self._unavailable_state("analytics_service_unavailable", include_reason=False, include_error=True))
