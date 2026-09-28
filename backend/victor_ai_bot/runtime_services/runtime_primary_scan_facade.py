from __future__ import annotations

import time
from typing import Any, Dict, List

from ..arb_engine import find_three_leg_opportunities, find_two_leg_opportunities
from ..models import Opportunity
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
            opps.sort(key=opportunity_profit_sort_key, reverse=True)
            requests = int(two_leg_telemetry.get("quote_requests", 0)) + int(
                three_leg_telemetry.get("quote_requests", 0)
            )
            successes = int(two_leg_telemetry.get("quote_successes", 0)) + int(
                three_leg_telemetry.get("quote_successes", 0)
            )
            telemetry["quotes"] = {
                "requests": requests,
                "successes": successes,
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
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            telemetry["quote_success_rate"] = (
                float(successes) / float(requests) if requests else 0.0
            )
            self._market_pipeline_telemetry = telemetry
            return opps[:80]
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
            telemetry["scan_error"] = f"{type(exc).__name__}: {exc}"
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            self._market_pipeline_telemetry = telemetry
            raise
