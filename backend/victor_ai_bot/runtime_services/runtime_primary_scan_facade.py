from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List
from urllib.parse import urlsplit

from ..arb_engine import find_three_leg_opportunities, find_two_leg_opportunities
from ..cache import PerBlockCache
from ..models import Opportunity
from ..rpc import JsonRpcClient
from ..rpc_economic_selector import RpcEconomicEvidence, select_best_rpc_evidence
from ..profitability_state import revalidate_profitability_state
from ..usd_pricing import token_to_usd_micro
from .profitability_truth import opportunity_profit_sort_key

_SAFE_SCAN_TELEMETRY_EXCEPTIONS = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)


class RuntimePrimaryScanFacade:
    """Primary DEX loop-scan compatibility facade.

    This isolates the top-level two-leg / three-leg opportunity assembly from
    RuntimeBundle's scan loop while preserving current behavior:
    - no local swallowing of ordinary scan bugs
    - same discovery, scan, sort, and truncate semantics
    - no routing or execution-submission changes
    """

    async def _discover_extra_v3_pairs(self, rpc: Any, *, current_block: int) -> List[Any]:
        discovery = getattr(self, "_discovery", None)
        if discovery is None:
            return []
        pairs = await discovery.maybe_discover_univ3(rpc, self.cfg, int(current_block))
        return list(pairs or [])

    async def _annotate_canonical_after_fee_usd(
        self,
        *,
        opps: List[Opportunity],
        rpc: Any,
        current_block: int,
        cache: PerBlockCache | None = None,
    ) -> None:
        """Attach explicit USD value for canonical scan-time after-fee truth.

        The global selector must compare like-for-like USD economics across
        runtime bundles. Scan-time gross/gas USD projections are not sufficient
        because they omit the canonical flashloan/gas after-fee contract.
        This enrichment is fail-closed and only writes an explicit USD value
        when the canonical after-fee state is valid and a quote-derived USD
        conversion is available.
        """
        execution = getattr(self.cfg, "execution", None)
        if not bool(getattr(execution, "usd_accounting_enabled", False)):
            return
        preference = str(getattr(execution, "usd_stable_preference", "usdc") or "usdc")
        scan_cache = cache or self.cache
        for opportunity in list(opps[:80]):
            meta = opportunity.meta if isinstance(getattr(opportunity, "meta", None), dict) else {}
            gas_cost_wei = int(meta.get("gas_cost_estimate_wei") or 0)
            state = revalidate_profitability_state(
                opportunity,
                self.cfg,
                stage="scan_after_fee_revalidation",
                source="runtime_primary_scan",
                gas_cost_wei=gas_cost_wei,
            )
            if not bool(state.get("valid")):
                continue
            profit_after_wei = int(state.get("profit_after_costs_wei") or 0)
            if profit_after_wei <= 0:
                continue
            try:
                profit_token = str(opportunity.route.legs[0].token_in)
            except (AttributeError, IndexError, TypeError, ValueError):
                continue
            usd_after = await token_to_usd_micro(
                rpc,
                chain=self.cfg.chain,
                token=profit_token,
                amount_wei=profit_after_wei,
                block_number=int(current_block),
                cache=scan_cache,
                preference=preference,
            )
            if usd_after is None or int(usd_after) <= 0:
                continue
            state["profit_after_costs_usd_micro"] = int(usd_after)
            meta["profitability"] = dict(state)
            safety = meta.get("safety") if isinstance(meta.get("safety"), dict) else {}
            safety["profit_after_costs_usd_micro"] = str(int(usd_after))
            safety["profit_after_costs_usd_source"] = "quote_derived_canonical_after_fee"
            meta["safety"] = safety
            meta["canonical_after_fee_usd"] = {
                "verified": True,
                "source": "quote_derived_canonical_after_fee",
                "profit_token": profit_token,
                "profit_after_costs_wei": str(profit_after_wei),
                "profit_after_costs_usd_micro": str(int(usd_after)),
                "block_number": int(current_block),
            }

    def _adaptive_scan_amounts(self, amount_in: int) -> List[int]:
        """Return a bounded size ladder for discovery without changing execution sizing.

        The base amount is always scanned first. Alternative sizes are only probed
        when the base scan yields fewer than the configured minimum number of
        opportunities. This keeps normal scans cheap while preventing a single
        fixed notional from defining the entire opportunity universe.
        """
        base = max(1, int(amount_in))
        enabled = str(os.environ.get("VICTOR_ADAPTIVE_SIZE_DISCOVERY", "1")).strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return [base]

        try:
            min_opportunities = max(
                1, int(os.environ.get("VICTOR_ADAPTIVE_SIZE_MIN_OPPORTUNITIES", "2") or 2)
            )
        except (TypeError, ValueError):
            min_opportunities = 2

        # Keep the public helper deterministic; the caller decides whether probes
        # are needed after the base scan. These are deliberately coarse probes.
        raw = os.environ.get("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,2.0")
        multipliers: List[float] = []
        for item in str(raw).split(","):
            try:
                value = float(item.strip())
            except (TypeError, ValueError):
                continue
            if value > 0.0 and value != 1.0:
                multipliers.append(value)
        multipliers = list(dict.fromkeys(multipliers))[:4]

        amounts: List[int] = [base]
        for multiplier in multipliers:
            candidate = max(1, int(round(float(base) * multiplier)))
            if candidate not in amounts:
                amounts.append(candidate)
        # The attribute is intentionally stored only for diagnostics/tests.
        self._adaptive_size_min_opportunities = min_opportunities
        return amounts

    async def _scan_primary_opportunities(
        self,
        rpc: Any,
        *,
        current_block: int,
        amount_in: int,
        cache: PerBlockCache | None = None,
        discovery_context: Dict[str, List[Any]] | None = None,
        telemetry_sink: Dict[str, Any] | None = None,
    ) -> List[Opportunity]:
        if int(amount_in) <= 0:
            return []

        scan_started = time.perf_counter()
        scan_cache = cache or self.cache
        if discovery_context is None:
            extra_v3_pairs = await self._discover_extra_v3_pairs(
                rpc, current_block=int(current_block)
            )
            venue_pools = {"curve": [], "balancer": []}
            discovery = getattr(self, "_discovery", None)
            discover_venues = (
                getattr(discovery, "maybe_discover_venues", None)
                if discovery is not None
                else None
            )
            if callable(discover_venues):
                venue_pools = await discover_venues(rpc, self.cfg, int(current_block))
            discovery_context = {
                "v3_pairs": list(extra_v3_pairs),
                "curve_pools": list(venue_pools.get("curve") or []),
                "balancer_pools": list(venue_pools.get("balancer") or []),
            }
        extra_v3_pairs = list(discovery_context.get("v3_pairs") or [])
        extra_curve_pools = list(discovery_context.get("curve_pools") or [])
        extra_balancer_pools = list(discovery_context.get("balancer_pools") or [])

        telemetry: Dict[str, Any] = {
            "last_scan": int(time.time() * 1000),
            "last_block": int(current_block),
            "scan_error": "",
            "discovery": {
                "v3_pairs": len(extra_v3_pairs),
                "curve_pools": len(extra_curve_pools),
                "balancer_pools": len(extra_balancer_pools),
            },
        }
        two_leg_telemetry: Dict[str, Any] = {}
        three_leg_telemetry: Dict[str, Any] = {}
        opps2: List[Opportunity] = []
        opps3: List[Opportunity] = []
        try:
            size_amounts = [int(amount_in)]
            adaptive_amounts = self._adaptive_scan_amounts(int(amount_in))
            try:
                min_opportunities = int(
                    getattr(self, "_adaptive_size_min_opportunities", 2) or 2
                )
            except (TypeError, ValueError):
                min_opportunities = 2

            async def _run_size_scan(size_amount: int) -> tuple[List[Opportunity], List[Opportunity], Dict[str, Any], Dict[str, Any]]:
                two: List[Opportunity] = []
                three: List[Opportunity] = []
                two_metrics: Dict[str, Any] = {}
                three_metrics: Dict[str, Any] = {}

                if bool(getattr(self.cfg.flags, "enable_two_leg_loops", True)):
                    two = await find_two_leg_opportunities(
                        rpc,
                        self.cfg,
                        scan_cache,
                        current_block,
                        amount_in=int(size_amount),
                        slippage_bps=self.cfg.safety.slippage_bps,
                        time_budget_ms=1500,
                        max_opps=60,
                        telemetry=two_metrics,
                        extra_v3_pairs=extra_v3_pairs,
                        extra_curve_pools=extra_curve_pools,
                        extra_balancer_pools=extra_balancer_pools,
                    )

                if bool(
                    getattr(self.cfg.flags, "enable_three_leg_loops", False)
                    or getattr(self.cfg.flags, "enable_v3_triangular", False)
                ):
                    three = await find_three_leg_opportunities(
                        rpc,
                        self.cfg,
                        scan_cache,
                        current_block,
                        amount_in=int(size_amount),
                        slippage_bps=self.cfg.safety.slippage_bps,
                        time_budget_ms=1600,
                        max_opps=40,
                        telemetry=three_metrics,
                        extra_v3_pairs=extra_v3_pairs,
                        extra_curve_pools=extra_curve_pools,
                        extra_balancer_pools=extra_balancer_pools,
                    )
                return list(two), list(three), two_metrics, three_metrics

            # Base-size scan is authoritative for the normal path.
            base_two, base_three, base_two_metrics, base_three_metrics = await _run_size_scan(
                int(amount_in)
            )
            opps2.extend(base_two)
            opps3.extend(base_three)
            two_leg_telemetry.update(base_two_metrics)
            three_leg_telemetry.update(base_three_metrics)
            candidates_before_probe = len(opps2) + len(opps3)

            # Only expand the discovery universe when the base notional does not
            # provide enough candidates. Alternative sizes are discovery probes,
            # not execution decisions, and are never broadcast automatically.
            if (
                len(opps2) + len(opps3) < min_opportunities
                and len(adaptive_amounts) > 1
            ):
                size_amounts.extend(adaptive_amounts[1:])
                for probe_amount in adaptive_amounts[1:]:
                    probe_two, probe_three, probe_two_metrics, probe_three_metrics = await _run_size_scan(
                        int(probe_amount)
                    )
                    opps2.extend(probe_two)
                    opps3.extend(probe_three)

                    for target, source in (
                        (two_leg_telemetry, probe_two_metrics),
                        (three_leg_telemetry, probe_three_metrics),
                    ):
                        for key in (
                            "quote_requests",
                            "quote_successes",
                            "routes_considered",
                            "edges_generated",
                            "gross_candidates",
                            "candidate_count",
                            "route_groups_evaluated",
                            "quote_phase_ms",
                            "route_evaluation_ms",
                        ):
                            if key in source:
                                target[key] = (
                                    float(target.get(key, 0) or 0) + float(source.get(key, 0) or 0)
                                )
                        for key in ("quote_failure_reasons", "route_rejections"):
                            merged = dict(target.get(key) or {})
                            for reason, count in dict(source.get(key) or {}).items():
                                merged[str(reason)] = int(merged.get(str(reason), 0)) + int(count)
                            if merged:
                                target[key] = merged
                        target["budget_exhausted_after_quote"] = bool(
                            target.get("budget_exhausted_after_quote", False)
                            or source.get("budget_exhausted_after_quote", False)
                        )

            candidates_after_probe = len(opps2) + len(opps3)

            def _candidate_route_key(candidate: Opportunity) -> str:
                return str(
                    getattr(candidate, "route_id", "")
                    or getattr(candidate, "id", "")
                    or ""
                )

            def _candidate_amount_in(candidate: Opportunity) -> str:
                try:
                    legs = list(getattr(getattr(candidate, "route", None), "legs", []) or [])
                    return str(int(getattr(legs[0], "amount_in", 0) or 0)) if legs else ""
                except (AttributeError, IndexError, TypeError, ValueError):
                    return ""

            # A route at different sizes is a sizing variant, not a separate
            # venue/route opportunity. Keep the most profitable verified raw
            # variant per route_id while preserving distinct routes.
            best_by_route: Dict[str, Opportunity] = {}
            for candidate in [*opps2, *opps3]:
                route_key = _candidate_route_key(candidate)
                current = best_by_route.get(route_key)
                if current is None or int(candidate.expected_profit_raw) > int(current.expected_profit_raw):
                    best_by_route[route_key] = candidate
            all_opps = list(best_by_route.values())
            opps2 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("two-leg:")]
            opps3 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("tri:")]
            other_opps = [
                o for o in all_opps
                if o not in opps2 and o not in opps3
            ]
            opps = list(opps2) + list(opps3) + other_opps
            telemetry["adaptive_size_discovery"] = {
                "enabled": bool(len(adaptive_amounts) > 1),
                "base_amount_in": str(int(amount_in)),
                "amounts_scanned": [str(int(x)) for x in size_amounts],
                "probe_triggered": bool(len(size_amounts) > 1),
                "minimum_opportunities": int(min_opportunities),
                "candidates_before_probe": int(candidates_before_probe),
                "candidates_after_probe": int(candidates_after_probe),
                "probe_candidate_delta": int(candidates_after_probe - candidates_before_probe),
                "distinct_route_ids_before_probe": len({
                    _candidate_route_key(candidate) for candidate in [*base_two, *base_three]
                }),
                "distinct_route_ids_after_probe": len({
                    _candidate_route_key(candidate) for candidate in [*opps2, *opps3, *other_opps]
                }),
                "best_sizing_variants": [
                    {
                        "route_id": _candidate_route_key(candidate),
                        "amount_in": _candidate_amount_in(candidate),
                        "expected_profit_raw": str(getattr(candidate, "expected_profit_raw", "0") or "0"),
                    }
                    for candidate in sorted(
                        list(opps),
                        key=lambda item: int(getattr(item, "expected_profit_raw", 0) or 0),
                        reverse=True,
                    )[:80]
                ],
            }
            await self._annotate_canonical_after_fee_usd(
                opps=opps,
                rpc=rpc,
                current_block=int(current_block),
                cache=scan_cache,
            )
            opps.sort(key=opportunity_profit_sort_key, reverse=True)
            requests = int(two_leg_telemetry.get("quote_requests", 0)) + int(
                three_leg_telemetry.get("quote_requests", 0)
            )
            successes = int(two_leg_telemetry.get("quote_successes", 0)) + int(
                three_leg_telemetry.get("quote_successes", 0)
            )
            quote_failure_reasons: Dict[str, int] = {}
            route_rejections: Dict[str, int] = {}
            for source in (two_leg_telemetry, three_leg_telemetry):
                for key, value in dict(source.get("quote_failure_reasons") or {}).items():
                    quote_failure_reasons[str(key)] = quote_failure_reasons.get(str(key), 0) + int(value)
                for key, value in dict(source.get("route_rejections") or {}).items():
                    route_rejections[str(key)] = route_rejections.get(str(key), 0) + int(value)
            telemetry["quotes"] = {
                "requests": requests,
                "successes": successes,
                "failure_reasons": quote_failure_reasons,
            }
            telemetry["discovery"]["pools_seen"] = (
                len(extra_v3_pairs) + len(extra_curve_pools) + len(extra_balancer_pools)
            )
            telemetry["routes_considered"] = int(
                two_leg_telemetry.get("routes_considered", 0)
            ) + int(three_leg_telemetry.get("routes_considered", 0))
            telemetry["edges_generated"] = int(
                two_leg_telemetry.get("edges_generated", 0)
            ) + int(three_leg_telemetry.get("edges_generated", 0))
            telemetry["route_evaluation"] = {
                "quote_phase_ms": float(
                    two_leg_telemetry.get("quote_phase_ms", 0.0)
                ) + float(three_leg_telemetry.get("quote_phase_ms", 0.0)),
                "route_evaluation_ms": float(
                    two_leg_telemetry.get("route_evaluation_ms", 0.0)
                ) + float(three_leg_telemetry.get("route_evaluation_ms", 0.0)),
                "route_groups_evaluated": int(
                    two_leg_telemetry.get("route_groups_evaluated", 0)
                ) + int(three_leg_telemetry.get("route_groups_evaluated", 0)),
                "budget_exhausted_after_quote": bool(
                    two_leg_telemetry.get("budget_exhausted_after_quote", False)
                    or three_leg_telemetry.get("budget_exhausted_after_quote", False)
                ),
            }
            # Both scanners build the same route graph; expose one canonical
            # pre-quote universe snapshot rather than summing duplicate edges.
            # Prefer the three-leg snapshot because it also carries adjacency
            # pruning telemetry, falling back to two-leg when unavailable.
            telemetry["route_universe"] = dict(
                three_leg_telemetry.get("route_universe")
                or two_leg_telemetry.get("route_universe")
                or {}
            )
            telemetry["gross_candidates"] = len(opps)
            telemetry["route_rejections"] = route_rejections
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            telemetry["quote_success_rate"] = (
                float(successes) / float(requests) if requests else 0.0
            )
            rpc_url = str(getattr(rpc, "url", "") or "")
            rpc_host = str(urlsplit(rpc_url).hostname or "") if rpc_url else ""
            rpc_snapshot = {}
            try:
                rpc_snapshot = dict(self.rpc_manager.snapshot() or {})
            except (AttributeError, KeyError, TypeError, ValueError):
                rpc_snapshot = {}
            selected_rpc = next(
                (
                    dict(row)
                    for row in list(rpc_snapshot.get("read") or [])
                    if str(row.get("url") or "") == rpc_url
                ),
                {},
            )
            telemetry["rpc"] = {
                "endpoint": rpc_url,
                "provider": rpc_host,
                "score": selected_rpc.get("score"),
                "ok": selected_rpc.get("ok"),
                "quote_failures": selected_rpc.get("quote_failures", 0),
                "quote_successes": selected_rpc.get("quote_successes", 0),
                "quote_last_error": selected_rpc.get("quote_last_error"),
                "quote_unhealthy_until": selected_rpc.get("quote_unhealthy_until", 0.0),
            }
            if telemetry_sink is not None:
                telemetry_sink.clear()
                telemetry_sink.update(telemetry)
            else:
                self._market_pipeline_telemetry = telemetry
            return opps[:80]
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
            telemetry["scan_error"] = f"{type(exc).__name__}: {exc}"
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            if telemetry_sink is not None:
                telemetry_sink.clear()
                telemetry_sink.update(telemetry)
            else:
                self._market_pipeline_telemetry = telemetry
            raise

    async def _select_rpc_and_scan(
        self,
        *,
        bootstrap_rpc: Any,
        current_block: int,
        amount_in: int,
    ) -> Dict[str, Any]:
        """Race healthy read RPCs on the same route universe using read-only economics."""
        manager = self.rpc_manager
        candidates = list(manager.read_candidates() or [])
        bootstrap_url = str(getattr(bootstrap_rpc, "url", "") or "")
        if bootstrap_url and bootstrap_url not in candidates:
            candidates.insert(0, bootstrap_url)
        candidates = list(dict.fromkeys(candidates))
        max_providers = max(
            1,
            int(os.environ.get("VICTOR_RPC_ECONOMIC_MAX_PROVIDERS", "8") or 8),
        )
        candidates = candidates[:max_providers]
        if not candidates:
            return {
                "selected_endpoint": bootstrap_url,
                "opps": [],
                "cache": self.cache,
                "telemetry": dict(getattr(self, "_market_pipeline_telemetry", {}) or {}),
                "evidence": [],
            }

        discovery_context = await self._build_discovery_context(
            bootstrap_rpc,
            current_block=int(current_block),
        )

        async def scan_one(url: str) -> tuple[str, List[Opportunity], PerBlockCache, Dict[str, Any], RpcEconomicEvidence]:
            scan_cache = PerBlockCache()
            telemetry: Dict[str, Any] = {}
            started = time.perf_counter()
            try:
                if url == bootstrap_url:
                    opps = await self._scan_primary_opportunities(
                        bootstrap_rpc,
                        current_block=int(current_block),
                        amount_in=int(amount_in),
                        cache=scan_cache,
                        discovery_context=discovery_context,
                        telemetry_sink=telemetry,
                    )
                else:
                    async with JsonRpcClient(
                        url, timeout_s=10.0, max_concurrency=30, max_batch=80
                    ) as provider_rpc:
                        opps = await self._scan_primary_opportunities(
                            provider_rpc,
                            current_block=int(current_block),
                            amount_in=int(amount_in),
                            cache=scan_cache,
                            discovery_context=discovery_context,
                            telemetry_sink=telemetry,
                        )
            except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                telemetry.setdefault("scan_error", f"{type(exc).__name__}: {exc}")
                telemetry["scan_latency_ms"] = float((time.perf_counter() - started) * 1000.0)
                opps = []

            quotes = dict(telemetry.get("quotes") or {})
            quote_requests = int(quotes.get("requests", 0) or 0)
            quote_successes = int(quotes.get("successes", 0) or 0)
            try:
                manager.observe_quote_telemetry(
                    url,
                    requests=quote_requests,
                    successes=quote_successes,
                    failure_reasons=dict(quotes.get("failure_reasons") or {}),
                )
            except (AttributeError, TypeError, ValueError):
                pass

            snapshot = {}
            try:
                snapshot = dict(manager.snapshot() or {})
            except (AttributeError, KeyError, TypeError, ValueError):
                snapshot = {}
            row = next(
                (dict(item) for item in list(snapshot.get("read") or []) if str(item.get("url") or "") == url),
                {},
            )
            profit_micro = max(
                (
                    int(
                        ((getattr(opp, "meta", {}) or {}).get("canonical_after_fee_usd") or {}).get(
                            "profit_after_costs_usd_micro"
                        )
                        or 0
                    )
                    for opp in opps
                ),
                default=0,
            )
            profitable_count = sum(
                1
                for opp in opps
                if int(
                    ((getattr(opp, "meta", {}) or {}).get("canonical_after_fee_usd") or {}).get(
                        "profit_after_costs_usd_micro"
                    )
                    or 0
                )
                > 0
            )
            quote_quarantined = float(row.get("quote_unhealthy_until", 0.0) or 0.0) > time.time()
            evidence = RpcEconomicEvidence(
                endpoint=url,
                provider=str(urlsplit(url).hostname or ""),
                profit_after_costs_usd_micro=int(profit_micro),
                profitable_opportunity_count=int(profitable_count),
                quote_requests=quote_requests,
                quote_successes=quote_successes,
                operational_score=float(row.get("score") or 1e18),
                block_number=int(current_block),
                scan_latency_ms=float(telemetry.get("scan_latency_ms") or 0.0),
                healthy=bool(row.get("ok", True)) and not bool(telemetry.get("scan_error")),
                quote_quarantined=quote_quarantined,
            )
            telemetry["rpc"] = dict(telemetry.get("rpc") or {})
            telemetry["rpc"].update(
                {
                    "endpoint": url,
                    "provider": str(urlsplit(url).hostname or ""),
                    "score": row.get("score"),
                    "ok": row.get("ok"),
                    "quote_failures": row.get("quote_failures", 0),
                    "quote_successes": row.get("quote_successes", 0),
                    "quote_last_error": row.get("quote_last_error"),
                    "quote_unhealthy_until": row.get("quote_unhealthy_until", 0.0),
                }
            )
            return url, list(opps or []), scan_cache, telemetry, evidence

        results = await asyncio.gather(*(scan_one(url) for url in candidates))
        evidence = [item[4] for item in results]
        selected, ordered = select_best_rpc_evidence(evidence)
        if selected is None:
            selected_url = bootstrap_url or candidates[0]
            selected_result = next(item for item in results if item[0] == selected_url)
        else:
            selected_url = selected.endpoint
            selected_result = next(item for item in results if item[0] == selected_url)

        _, selected_opps, selected_cache, selected_telemetry, _ = selected_result
        selected_telemetry["rpc"]["economic_selection"] = {
            "mode": "read_only_economic",
            "selected_endpoint": selected_url,
            "selected_provider": str(urlsplit(selected_url).hostname or ""),
            "candidates": [
                {
                    "endpoint": item.endpoint,
                    "provider": item.provider,
                    "profit_after_costs_usd_micro": item.profit_after_costs_usd_micro,
                    "profitable_opportunity_count": item.profitable_opportunity_count,
                    "quote_requests": item.quote_requests,
                    "quote_successes": item.quote_successes,
                    "quote_success_rate": item.quote_success_rate,
                    "operational_score": item.operational_score,
                    "block_number": item.block_number,
                    "scan_latency_ms": item.scan_latency_ms,
                    "healthy": item.healthy,
                    "quote_quarantined": item.quote_quarantined,
                    "selected": item.endpoint == selected_url,
                }
                for item in ordered
            ],
            "active_chain_changed": False,
            "broadcast_attempted": False,
            "auto_trade_enabled": False,
        }
        return {
            "selected_endpoint": selected_url,
            "opps": selected_opps,
            "cache": selected_cache,
            "telemetry": selected_telemetry,
            "evidence": evidence,
        }

    async def _build_discovery_context(
        self,
        rpc: Any,
        *,
        current_block: int,
    ) -> Dict[str, List[Any]]:
        extra_v3_pairs = await self._discover_extra_v3_pairs(
            rpc, current_block=int(current_block)
        )
        venue_pools = {"curve": [], "balancer": []}
        discovery = getattr(self, "_discovery", None)
        discover_venues = (
            getattr(discovery, "maybe_discover_venues", None)
            if discovery is not None
            else None
        )
        if callable(discover_venues):
            venue_pools = await discover_venues(rpc, self.cfg, int(current_block))
        return {
            "v3_pairs": list(extra_v3_pairs),
            "curve_pools": list(venue_pools.get("curve") or []),
            "balancer_pools": list(venue_pools.get("balancer") or []),
        }
