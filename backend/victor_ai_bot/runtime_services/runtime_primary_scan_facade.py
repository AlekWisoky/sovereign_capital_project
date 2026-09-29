from __future__ import annotations

import time
from typing import Any, Dict, List
from urllib.parse import urlsplit

from ..arb_engine import find_three_leg_opportunities, find_two_leg_opportunities
from ..models import Opportunity
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
                cache=self.cache,
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

    async def _scan_primary_opportunities(
        self,
        rpc: Any,
        *,
        current_block: int,
        amount_in: int,
    ) -> List[Opportunity]:
        if int(amount_in) <= 0:
            return []

        scan_started = time.perf_counter()
        extra_v3_pairs = await self._discover_extra_v3_pairs(rpc, current_block=int(current_block))
        venue_pools = {"curve": [], "balancer": []}
        discovery = getattr(self, "_discovery", None)
        discover_venues = getattr(discovery, "maybe_discover_venues", None) if discovery is not None else None
        if callable(discover_venues):
            venue_pools = await discover_venues(rpc, self.cfg, int(current_block))
        extra_curve_pools = list(venue_pools.get("curve") or [])
        extra_balancer_pools = list(venue_pools.get("balancer") or [])

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
            if bool(getattr(self.cfg.flags, "enable_two_leg_loops", True)):
                opps2 = await find_two_leg_opportunities(
                    rpc,
                    self.cfg,
                    self.cache,
                    current_block,
                    amount_in=int(amount_in),
                    slippage_bps=self.cfg.safety.slippage_bps,
                    time_budget_ms=1500,
                    max_opps=60,
                    telemetry=two_leg_telemetry,
                    extra_v3_pairs=extra_v3_pairs,
                    extra_curve_pools=extra_curve_pools,
                    extra_balancer_pools=extra_balancer_pools,
                )

            if bool(
                getattr(self.cfg.flags, "enable_three_leg_loops", False)
                or getattr(self.cfg.flags, "enable_v3_triangular", False)
            ):
                opps3 = await find_three_leg_opportunities(
                    rpc,
                    self.cfg,
                    self.cache,
                    current_block,
                    amount_in=int(amount_in),
                    slippage_bps=self.cfg.safety.slippage_bps,
                    time_budget_ms=1600,
                    max_opps=40,
                    telemetry=three_leg_telemetry,
                    extra_v3_pairs=extra_v3_pairs,
                    extra_curve_pools=extra_curve_pools,
                    extra_balancer_pools=extra_balancer_pools,
                )

            opps = list(opps2) + list(opps3)
            await self._annotate_canonical_after_fee_usd(
                opps=opps,
                rpc=rpc,
                current_block=int(current_block),
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
            self._market_pipeline_telemetry = telemetry
            return opps[:80]
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
            telemetry["scan_error"] = f"{type(exc).__name__}: {exc}"
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            self._market_pipeline_telemetry = telemetry
            raise
