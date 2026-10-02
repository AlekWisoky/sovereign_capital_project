from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List
from urllib.parse import urlsplit

from ..arb_engine import find_three_leg_opportunities, find_two_leg_opportunities
from ..execution_capture.final_quote import FinalQuoteError, produce_market_price_evidence
from ..cache import PerBlockCache
from ..gas_model import estimate_gas_cost_wei_from_cfg, estimate_route_gas_units
from ..models import Opportunity
from ..rpc import JsonRpcClient
from ..rpc_economic_selector import RpcEconomicEvidence, select_best_rpc_evidence
from ..profitability_state import revalidate_profitability_state
from ..flashloan_providers import observe_flashloan_fee_bps
from ..usd_pricing import gas_wei_to_token_wei, token_to_usd_micro
from .profitability_truth import opportunity_profit_sort_key

_SAFE_SCAN_TELEMETRY_EXCEPTIONS = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)

def _resolve_scan_quoted_amount(meta: Dict[str, Any]) -> int | None:
    """Return the first positive quoted terminal output, preferring the final leg."""
    for key in ("out3", "out2"):
        value = meta.get(key)
        if value is None:
            continue
        try:
            amount = int(value)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            return amount
    return None



def _canonical_route_universe_telemetry(
    two_leg: Dict[str, Any],
    three_leg: Dict[str, Any],
) -> Dict[str, Any]:
    """Return one graph snapshot without double-counting two/three-leg scans."""
    return dict(
        three_leg.get("route_universe")
        or two_leg.get("route_universe")
        or {}
    )


def _reconstruct_nonrepay_economic_profit(row: Dict[str, Any]) -> int | None:
    try:
        return (
            int(row.get("gross_profit_wei") or 0)
            - int(row.get("flashloan_fee_wei") or 0)
            - int(row.get("gas_cost_profit_token_wei") or 0)
        )
    except (TypeError, ValueError):
        return None


def _economic_after_cost_profit(row: Dict[str, Any]) -> int | None:
    """Return signed P&L for sizing while keeping execution fail-closed."""
    explicit = row.get("economic_after_cost_profit_wei")
    if explicit not in (None, ""):
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return None
    try:
        after_cost = int(row.get("after_cost_profit_wei") or 0)
    except (TypeError, ValueError):
        return None
    if row.get("reason") == "does_not_repay_flashloan" or after_cost == -1:
        return _reconstruct_nonrepay_economic_profit(row)
    return after_cost


def _candidate_route_snapshot(candidate: Opportunity) -> tuple[List[Dict[str, str]], str]:
    legs: List[Dict[str, str]] = []
    try:
        for leg in list(getattr(getattr(candidate, "route", None), "legs", []) or [])[:3]:
            legs.append({
                "dex": str(getattr(leg, "dex", "") or ""),
                "venue": str(getattr(leg, "venue", "") or ""),
                "token_in": str(getattr(leg, "token_in", "") or ""),
                "token_out": str(getattr(leg, "token_out", "") or ""),
                "amount_in": str(getattr(leg, "amount_in", "0") or "0"),
                "min_out": str(getattr(leg, "min_out", "0") or "0"),
                "data": str(getattr(leg, "data", "") or ""),
            })
    except (AttributeError, TypeError, ValueError):
        return [], "0"
    return legs, str(legs[0]["amount_in"]) if legs else "0"


def _candidate_economic_fields(
    candidate: Opportunity,
    meta: Dict[str, Any],
    profitability: Dict[str, Any],
    amount_in_value: str,
) -> Dict[str, Any]:
    terminal = meta.get("out3") or meta.get("out2") or ""
    amount_out_wei = int(terminal or 0)
    gross_profit_wei = int(getattr(candidate, "expected_profit_raw", "0") or "0")
    fee = int(profitability.get("flashloan_fee_wei") or "0")
    gas_profit = int(profitability.get("gas_cost_profit_token_wei") or "0")
    gross_minus_fee = gross_profit_wei - fee
    gross_minus_costs = gross_minus_fee - gas_profit
    economic = profitability.get("economic_profit_after_costs_wei")
    if economic in (None, ""):
        try:
            observed_after_cost = int(profitability.get("profit_after_costs_wei") or 0)
        except (TypeError, ValueError):
            observed_after_cost = 0
        if profitability.get("reason") == "does_not_repay_flashloan" or observed_after_cost == -1:
            economic = gross_minus_costs
        else:
            economic = observed_after_cost
    try:
        economic = int(economic)
    except (TypeError, ValueError):
        economic = gross_minus_costs
    return {
        "amount_out_wei": amount_out_wei,
        "gross_profit_wei": gross_profit_wei,
        "gas_cost_profit_token_wei": gas_profit,
        "flashloan_fee_wei": fee,
        "gas_cost_wei": str(
            profitability.get("gas_cost_wei")
            or meta.get("gas_cost_estimate_wei")
            or "0"
        ),
        "gross_minus_flashloan_fee_wei": gross_minus_fee,
        "gross_minus_flashloan_fee_minus_gas_wei": gross_minus_costs,
        "economic_after_cost_profit_wei": economic,
        "repayment_valid": bool(
            amount_in_value
            and amount_out_wei > 0
            and amount_out_wei >= int(amount_in_value) + fee
        ),
    }


def _size_economic_candidate_row(candidate: Opportunity) -> Dict[str, Any]:
    meta = getattr(candidate, "meta", {}) or {}
    profitability = meta.get("profitability") if isinstance(meta, dict) else {}
    if not profitability and isinstance(meta, dict):
        profitability = meta.get("profitability_diagnostic")
    profitability = profitability if isinstance(profitability, dict) else {}
    legs, amount_in_value = _candidate_route_snapshot(candidate)
    fields = _candidate_economic_fields(candidate, meta, profitability, amount_in_value)
    row = {
        "route_id": str(getattr(candidate, "route_id", "") or getattr(candidate, "id", "") or ""),
        "amount_in": amount_in_value,
        "gross_profit_wei": str(fields["gross_profit_wei"]),
        "amount_out_wei": str(fields["amount_out_wei"]),
        "gas_cost_profit_token_wei": str(fields["gas_cost_profit_token_wei"]),
        "min_outs": [str(x) for x in list(getattr(candidate, "min_outs", []) or [])],
        "flashloan_fee_wei": str(fields["flashloan_fee_wei"]),
        "gas_cost_wei": fields["gas_cost_wei"],
        "gross_minus_flashloan_fee_wei": str(fields["gross_minus_flashloan_fee_wei"]),
        "gross_minus_flashloan_fee_minus_gas_wei": str(fields["gross_minus_flashloan_fee_minus_gas_wei"]),
        "repayment_valid": fields["repayment_valid"],
        "after_cost_profit_wei": str(profitability.get("profit_after_costs_wei") or "0"),
        "economic_after_cost_profit_wei": str(fields["economic_after_cost_profit_wei"]),
        "revalidated": bool(profitability.get("revalidated")),
        "authoritative": bool(profitability.get("authoritative")),
        "reason": str(profitability.get("reason") or "unavailable"),
        "diagnostic_only": bool(profitability.get("revalidated")) and not bool(profitability.get("authoritative")),
    }
    if legs:
        row["legs"] = legs
    return row


def _merge_size_quote_failure_reasons(
    two_metrics: Dict[str, Any],
    three_metrics: Dict[str, Any],
) -> Dict[str, int]:
    merged = {
        str(k): int(v)
        for k, v in dict(two_metrics.get("quote_failure_reasons") or {}).items()
    }
    for key, value in dict(three_metrics.get("quote_failure_reasons") or {}).items():
        merged[str(key)] = int(merged.get(str(key), 0)) + int(value)
    return merged


def _size_diagnostic_rows(metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for diagnostic in list(metrics.get("size_economic_diagnostics") or []):
        if not isinstance(diagnostic, dict):
            continue
        amount_in = int(diagnostic.get("amount_in") or 0)
        amount_out = int(diagnostic.get("amount_out_wei") or 0)
        gross = int(diagnostic.get("gross_profit_wei") or 0)
        fee = int(diagnostic.get("flashloan_fee_wei") or 0)
        gas = int(diagnostic.get("gas_cost_profit_token_wei") or 0)
        economic = diagnostic.get("economic_after_cost_profit_wei")
        if economic in (None, ""):
            economic = gross - fee - gas
        try:
            economic = int(economic)
        except (TypeError, ValueError):
            economic = gross - fee - gas
        row = {
            "route_id": str(diagnostic.get("route_id") or ""),
            "amount_in": str(amount_in),
            "amount_out_wei": str(amount_out),
            "gross_profit_wei": str(gross),
            "flashloan_fee_wei": str(fee),
            "gas_cost_wei": str(diagnostic.get("gas_cost_wei") or "0"),
            "gas_cost_profit_token_wei": str(gas),
            "gross_minus_flashloan_fee_wei": str(gross - fee),
            "gross_minus_flashloan_fee_minus_gas_wei": str(gross - fee - gas),
            "repayment_valid": bool(amount_out > 0 and amount_out >= amount_in + fee),
            "after_cost_profit_wei": str(diagnostic.get("after_cost_profit_wei") or "0"),
            "economic_after_cost_profit_wei": str(economic),
            "revalidated": bool(diagnostic.get("revalidated")),
            "authoritative": bool(diagnostic.get("authoritative")),
            "reason": str(diagnostic.get("reason") or "diagnostic_only"),
            "diagnostic_only": True,
        }
        legs = [dict(leg) for leg in (diagnostic.get("legs") or []) if isinstance(leg, dict)][:3]
        if legs:
            row["legs"] = legs
        rows.append(row)
    return rows


def _size_route_rows(record: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    two_metrics = dict(record.get("two_metrics") or {})
    three_metrics = dict(record.get("three_metrics") or {})
    candidates = list(record.get("two") or []) + list(record.get("three") or [])
    rows = [_size_economic_candidate_row(candidate) for candidate in candidates]
    diagnostics = _size_diagnostic_rows(two_metrics) + _size_diagnostic_rows(three_metrics)
    existing = {row["route_id"] for row in rows}
    rows.extend(row for row in diagnostics if row["route_id"] and row["route_id"] not in existing)
    return rows, two_metrics, three_metrics


def _size_matrix_selection(rows: List[Dict[str, Any]]) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    positive = [
        row for row in rows
        if row["revalidated"] and row["authoritative"] and int(row["after_cost_profit_wei"]) > 0
    ]
    selected = max(positive, key=lambda row: int(row["after_cost_profit_wei"]), default=None)
    economic_rows = [
        row for row in rows
        if row.get("route_id")
        and (bool(row.get("revalidated")) or bool(row.get("diagnostic_only")))
        and _economic_after_cost_profit(row) is not None
    ]
    economic = max(
        economic_rows,
        key=lambda row: int(_economic_after_cost_profit(row) or 0),
        default=None,
    )
    return selected, economic


def _build_size_matrix_row(
    amount: int,
    rows: List[Dict[str, Any]],
    two_metrics: Dict[str, Any],
    three_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    selected, economic = _size_matrix_selection(rows)
    requests = int(two_metrics.get("quote_requests", 0) or 0) + int(three_metrics.get("quote_requests", 0) or 0)
    successes = int(two_metrics.get("quote_successes", 0) or 0) + int(three_metrics.get("quote_successes", 0) or 0)
    basis = "verified_after_cost_profit" if selected else "no_economic_evidence"
    if economic and not selected:
        basis = "economic_optimum_diagnostic"
        if str(economic.get("reason") or "") == "non_positive_gross_profit":
            basis = "gross_profit_diagnostic_only"
    return {
        "amount_in": str(amount),
        "quote_requests": requests,
        "quote_successes": successes,
        "quote_failures": max(0, requests - successes),
        "quote_failure_reasons": _merge_size_quote_failure_reasons(two_metrics, three_metrics),
        "failed_quote_edge_count": int(two_metrics.get("failed_quote_edge_count", 0) or 0) + int(three_metrics.get("failed_quote_edge_count", 0) or 0),
        "failed_quote_edge_samples": list(dict.fromkeys([
            *list(two_metrics.get("failed_quote_edge_samples") or []),
            *list(three_metrics.get("failed_quote_edge_samples") or []),
        ]))[:256],
        "route_ids": [row["route_id"] for row in rows if row["route_id"]],
        "candidates": rows,
        "selection_basis": basis,
        "selected_route_id": selected["route_id"] if selected else "",
        "selected_after_cost_profit_wei": selected["after_cost_profit_wei"] if selected else "0",
        "economic_optimum_route_id": economic["route_id"] if economic else "",
        "economic_optimum_after_cost_profit_wei": (
            str(_economic_after_cost_profit(economic)) if economic else "0"
        ),
        "economic_optimum_authoritative": bool(economic and economic["authoritative"]),
        "economic_optimum_executable": bool(selected),
    }


def _build_size_economic_matrix(size_scan_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matrix: List[Dict[str, Any]] = []
    for record in size_scan_records:
        rows, two_metrics, three_metrics = _size_route_rows(record)
        matrix.append(
            _build_size_matrix_row(
                int(record.get("amount_in") or 0),
                rows,
                two_metrics,
                three_metrics,
            )
        )
    return matrix



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
        usd_enabled = bool(getattr(execution, "usd_accounting_enabled", False))
        preference = str(getattr(execution, "usd_stable_preference", "usdc") or "usdc")
        scan_cache = cache or self.cache
        flash_provider = str(getattr(getattr(self.cfg, "execution", None), "flash_provider", "aave") or "aave")
        flashloan_fee_observation = await observe_flashloan_fee_bps(
            rpc,
            self.cfg,
            flash_provider,
            block=f"0x{int(current_block):x}",
        )
        native_flashloan_fee_bps = (
            int(flashloan_fee_observation["fee_bps"])
            if bool(flashloan_fee_observation.get("ok"))
            and flashloan_fee_observation.get("fee_bps") is not None
            else None
        )
        observed_gas_price_wei: int | None = None
        try:
            observed_gas_price_wei = await rpc.gas_price()
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
            observed_gas_price_wei = None
        for opportunity in list(opps):
            meta = opportunity.meta if isinstance(getattr(opportunity, "meta", None), dict) else {}
            if isinstance(meta, dict):
                meta["flashloan_fee_observation"] = dict(flashloan_fee_observation)
            # Synthetic/test opportunities may carry a precomputed gas cost
            # without route metadata. Preserve that concrete value when no
            # route-level gas inputs exist; production opportunities always
            # carry legs/venues and therefore use the observed gas price.
            has_route_gas_inputs = bool(
                meta.get("venues")
                or any(isinstance(meta.get(key), dict) for key in ("leg1", "leg2", "leg3"))
            )
            if has_route_gas_inputs:
                gas_units = estimate_route_gas_units(meta)
                gas_cost_wei = int(
                    estimate_gas_cost_wei_from_cfg(
                        self.cfg,
                        gas_units,
                        observed_gas_price_wei=observed_gas_price_wei,
                    )
                )
            else:
                gas_cost_wei = int(meta.get("gas_cost_estimate_wei") or 0)
            gas_cost_in_profit_token_wei: int | None = None
            profit_token = ""
            try:
                legs = list(getattr(getattr(opportunity, "route", None), "legs", []) or [])
                profit_token = str(getattr(legs[0], "token_in", "") or "") if legs else ""
            except (AttributeError, IndexError, TypeError, ValueError):
                profit_token = ""
            if has_route_gas_inputs and profit_token:
                try:
                    gas_cost_in_profit_token_wei = await gas_wei_to_token_wei(
                        rpc,
                        chain=self.cfg.chain,
                        gas_cost_wei=int(gas_cost_wei),
                        token_out=profit_token,
                        block_number=int(current_block),
                        cache=scan_cache,
                    )
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
                    gas_cost_in_profit_token_wei = None

            existing_profitability = meta.get("profitability")
            if (
                isinstance(existing_profitability, dict)
                and bool(existing_profitability.get("revalidated"))
                and bool(existing_profitability.get("authoritative"))
            ):
                state = dict(existing_profitability)
            else:
                try:
                    revalidation_kwargs = {
                        "gas_cost_wei": gas_cost_wei,
                        "quoted_amount_out_wei": _resolve_scan_quoted_amount(meta),
                        "gas_cost_in_profit_token_wei": (
                            gas_cost_in_profit_token_wei
                            if has_route_gas_inputs
                            else gas_cost_wei
                        ),
                    }
                    if native_flashloan_fee_bps is not None:
                        revalidation_kwargs["flashloan_fee_bps_override"] = native_flashloan_fee_bps
                    state = revalidate_profitability_state(
                        opportunity,
                        self.cfg,
                        stage="scan_after_fee_revalidation",
                        source="runtime_primary_scan",
                        **revalidation_kwargs,
                    )
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                    # One malformed candidate must not erase the entire
                    # institutional sizing matrix. Fail closed for this
                    # candidate and retain the concrete diagnostic reason.
                    state = {
                        "stage": "scan_after_fee_revalidation",
                        "source": "runtime_primary_scan",
                        "reason": f"revalidation_exception:{type(exc).__name__}",
                        "revalidated": False,
                        "stale": True,
                        "valid": False,
                        "authoritative": False,
                        "gross_profit_wei": str(getattr(opportunity, "expected_profit_raw", "0") or "0"),
                        "profit_after_costs_wei": "0",
                        "gas_cost_wei": str(max(0, gas_cost_wei)),
                        "flashloan_fee_wei": "0",
                    }
            if has_route_gas_inputs and gas_cost_in_profit_token_wei is None:
                state = {
                    "stage": "scan_after_fee_revalidation",
                    "source": "runtime_primary_scan",
                    "reason": "gas_cost_profit_token_unavailable",
                    "revalidated": False,
                    "stale": True,
                    "valid": False,
                    "authoritative": False,
                    "gross_profit_wei": str(getattr(opportunity, "expected_profit_raw", "0") or "0"),
                    "profit_after_costs_wei": "0",
                    "gas_cost_wei": str(max(0, gas_cost_wei)),
                    "gas_cost_profit_token_wei": "0",
                    "flashloan_fee_wei": "0",
                }
            # Preserve the diagnostic revalidation result for the sizing
            # evidence matrix, but only promote a valid authoritative result to
            # canonical profitability. Invalid states must not poison legacy
            # opportunity ordering or downstream execution metadata.
            meta["profitability_diagnostic"] = dict(state)
            if not bool(state.get("valid")):
                continue
            meta["profitability"] = dict(state)
            profit_after_wei = int(state.get("profit_after_costs_wei") or 0)
            if profit_after_wei <= 0 or not usd_enabled:
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
        # Provider comparison must be economically symmetric at one notional.
        # Running the full institutional size ladder on every RPC multiplies
        # quote traffic and scan latency across providers. The selected provider
        # receives the full sizing pass after economic provider selection.
        if bool(getattr(self, "_rpc_provider_comparison", False)):
            self._adaptive_size_min_opportunities = max(
                1,
                int(os.environ.get("VICTOR_ADAPTIVE_SIZE_MIN_OPPORTUNITIES", "2") or 2),
            )
            return [base]
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
        # are needed after the base scan. User-supplied multipliers remain supported,
        # but an institutional scan must not silently stop at an arbitrary 4x ceiling
        # when an explicit authorized borrow cap is available.
        raw = os.environ.get("VICTOR_ADAPTIVE_SIZE_MULTIPLIERS", "0.5,1.5,2.0,4.0")
        borrow_cap = 0
        try:
            borrow_cap = int(
                getattr(getattr(self, "_bankroll", None), "cfg", None)
                and getattr(self._bankroll.cfg, "max_borrow_amount_wei", 0)
                or 0
            )
        except (AttributeError, TypeError, ValueError):
            borrow_cap = 0
        if borrow_cap <= 0:
            try:
                borrow_cap = int(getattr(getattr(self.cfg, "safety", None), "max_borrow_amount", 0) or 0)
            except (AttributeError, TypeError, ValueError):
                borrow_cap = 0
        borrow_cap = max(0, borrow_cap)
        if borrow_cap > 0:
            base = min(base, borrow_cap)

        # A zero configured borrow cap means the execution bankroll has no
        # explicit operator ceiling. Discovery must not interpret that as
        # permission to scan an unbounded notional, so use a separate,
        # diagnostic-only ceiling. An explicit borrow cap always wins.
        discovery_max_multiplier = 16.0
        try:
            discovery_max_multiplier = float(
                os.environ.get("VICTOR_ADAPTIVE_SIZE_DISCOVERY_MAX_MULTIPLIER", "16.0")
                or 16.0
            )
        except (TypeError, ValueError):
            discovery_max_multiplier = 16.0
        discovery_max_multiplier = max(1.0, min(64.0, discovery_max_multiplier))

        multipliers: List[float] = []
        for item in str(raw).split(","):
            try:
                value = float(item.strip())
            except (TypeError, ValueError):
                continue
            if value > 0.0 and value != 1.0:
                multipliers.append(value)
        # Preserve the established user/default probes, but bound them so the
        # cap-aware ladder cannot be displaced by an oversized environment value.
        multipliers = list(dict.fromkeys(multipliers))[:4]

        # Always retain the explicit configured probes first. Then add a bounded
        # geometric ladder toward the authorized cap. This is discovery-only:
        # every point is still requoted and economically revalidated before it can
        # influence the retained opportunity, and no point grants execution
        # authority by itself.
        target_ratio = (
            float(borrow_cap) / float(base)
            if borrow_cap > base
            else float(discovery_max_multiplier)
        )
        if target_ratio > 1.0:
            # At most three interpolated larger probes plus the exact target.
            # Logarithmic spacing avoids a large blind spot without creating an
            # unbounded RPC fan-out. When a real borrow cap exists it is the
            # target; otherwise this is discovery-only and never changes the
            # execution cap.
            for step in range(1, 4):
                fraction = float(step) / 4.0
                multipliers.append(target_ratio ** fraction)
            multipliers.append(target_ratio)

        # Preserve smaller probes and deduplicate after rounding to wei. Hard cap
        # the total number of alternative sizes to eight.
        amounts: List[int] = [base]
        for multiplier in multipliers:
            candidate = max(1, int(round(float(base) * multiplier)))
            if borrow_cap > 0:
                candidate = min(candidate, borrow_cap)
            if candidate not in amounts:
                amounts.append(candidate)
            if len(amounts) >= 9:
                break
        # The attribute is intentionally stored only for diagnostics/tests.
        self._adaptive_size_min_opportunities = min_opportunities
        return amounts

    async def _build_token_scan_amounts(
        self,
        rpc: Any,
        *,
        current_block: int,
        base_amount_in: int,
        cache: PerBlockCache,
    ) -> tuple[Dict[str, int], Dict[str, Any]]:
        """Translate the reference borrow notional into raw units per input token."""
        chain = getattr(self.cfg, "chain", None)
        tokens = [str(token) for token in (getattr(chain, "token_universe", []) or []) if token]
        weth = str(getattr(chain, "weth", "") or "")
        telemetry: Dict[str, Any] = {
            "enabled": False,
            "source": "",
            "reference_token": weth,
            "base_amount_in": str(int(base_amount_in)),
            "amounts_by_token": {},
            "unpriced_tokens": [],
        }
        if not tokens or not weth:
            return {}, telemetry
        try:
            evidence = await produce_market_price_evidence(
                rpc,
                cfg=self.cfg,
                tokens=[(token, "scan_input") for token in tokens],
                block_number=int(current_block),
            )
        except (FinalQuoteError, OSError, RuntimeError, TypeError, ValueError):
            telemetry["source"] = "reference_token_fallback"
            telemetry["amounts_by_token"] = {weth.lower(): str(max(1, int(base_amount_in)))}
            telemetry["unpriced_tokens"] = [
                token for token in tokens if token.lower() != weth.lower()
            ]
            return {weth.lower(): max(1, int(base_amount_in))}, telemetry
        ref = evidence.get(weth.lower())
        if not isinstance(ref, dict):
            telemetry["source"] = "reference_token_unpriced"
            telemetry["unpriced_tokens"] = list(tokens)
            return {}, telemetry
        try:
            ref_decimals = int(ref["decimals"])
            ref_price = float(ref["price_usd"])
            reference_usd = (
                float(base_amount_in) / float(10 ** ref_decimals)
            ) * ref_price
            if reference_usd <= 0:
                raise ValueError("reference_usd_non_positive")
        except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
            telemetry["source"] = "reference_token_invalid"
            telemetry["unpriced_tokens"] = list(tokens)
            return {}, telemetry
        amounts: Dict[str, int] = {}
        for token in tokens:
            row = evidence.get(token.lower())
            if not isinstance(row, dict):
                telemetry["unpriced_tokens"].append(token)
                continue
            try:
                decimals = int(row["decimals"])
                price_usd = float(row["price_usd"])
                raw = int(max(1.0, round(reference_usd / price_usd * float(10 ** decimals))))
            except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
                telemetry["unpriced_tokens"].append(token)
                continue
            amounts[token.lower()] = raw
        telemetry["enabled"] = bool(amounts)
        telemetry["source"] = "quote_derived_usd_notional"
        telemetry["reference_notional_usd"] = float(reference_usd)
        telemetry["amounts_by_token"] = {token: str(amount) for token, amount in amounts.items()}
        return amounts, telemetry

    async def _scan_primary_opportunities(
        self,
        rpc: Any,
        *,
        current_block: int,
        amount_in: int,
        cache: PerBlockCache | None = None,
        discovery_context: Dict[str, List[Any]] | None = None,
        telemetry_sink: Dict[str, Any] | None = None,
        shared_token_scan_amounts: Dict[str, int] | None = None,
        force_adaptive_size_scan: bool = False,
    ) -> List[Opportunity]:
        if int(amount_in) <= 0:
            return []

        scan_started = time.perf_counter()
        scan_cache = cache or self.cache
        if discovery_context is None:
            discovery_context = await self._build_discovery_context(
                rpc,
                current_block=int(current_block),
            )
        extra_v3_pairs = list(discovery_context.get("v3_pairs") or [])
        extra_curve_pools = list(discovery_context.get("curve_pools") or [])
        extra_balancer_pools = list(discovery_context.get("balancer_pools") or [])

        discovery = getattr(self, "_discovery", None)
        candidate_token_telemetry = (
            discovery.candidate_token_telemetry(self.cfg)
            if discovery is not None
            and callable(getattr(discovery, "candidate_token_telemetry", None))
            else {
                "execution_universe": [
                    str(token).lower()
                    for token in (
                        getattr(getattr(self, "cfg", None), "chain", None)
                        and getattr(self.cfg.chain, "token_universe", [])
                        or []
                    )
                    if token
                ],
                "observed_tokens": [],
                "observed_not_admitted": [],
                "observed_count": 0,
                "observed_not_admitted_count": 0,
                "observation_cap": 0,
                "observation_truncated": False,
                "admission_mutated": False,
                "sources": {},
            }
        )
        telemetry: Dict[str, Any] = {
            "last_scan": int(time.time() * 1000),
            "last_block": int(current_block),
            "scan_status": "running",
            "scan_error": "",
            "discovery": {
                "v3_pairs": len(extra_v3_pairs),
                "curve_pools": len(extra_curve_pools),
                "balancer_pools": len(extra_balancer_pools),
            },
            "candidate_token_discovery": candidate_token_telemetry,
        }
        two_leg_telemetry: Dict[str, Any] = {}
        three_leg_telemetry: Dict[str, Any] = {}
        opps2: List[Opportunity] = []
        opps3: List[Opportunity] = []
        observed_gas_price_wei: int | None = None
        try:
            observed_gas_price_wei = await rpc.gas_price()
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
            observed_gas_price_wei = None
        if shared_token_scan_amounts is None:
            token_scan_amounts, token_scan_telemetry = await self._build_token_scan_amounts(
                rpc,
                current_block=int(current_block),
                base_amount_in=int(amount_in),
                cache=scan_cache,
            )
        else:
            token_scan_amounts = {
                str(token).lower(): max(1, int(raw))
                for token, raw in dict(shared_token_scan_amounts).items()
                if str(token) and int(raw) > 0
            }
            token_scan_telemetry = {
                "enabled": bool(token_scan_amounts),
                "source": "shared_provider_comparison",
                "reference_token": str(getattr(getattr(self.cfg, "chain", None), "weth", "") or ""),
                "base_amount_in": str(int(amount_in)),
                "amounts_by_token": {token: str(raw) for token, raw in token_scan_amounts.items()},
                "unpriced_tokens": [],
            }
        telemetry["scan_sizing"] = dict(token_scan_telemetry)
        try:
            size_amounts = [int(amount_in)]
            adaptive_amounts = self._adaptive_scan_amounts(int(amount_in))
            size_scan_records: List[Dict[str, Any]] = []
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
                        amount_in_by_token={
                            token: max(1, int(round(raw * float(size_amount) / float(max(1, int(amount_in))))))
                            for token, raw in token_scan_amounts.items()
                        },
                        observed_gas_price_wei=observed_gas_price_wei,
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
                        amount_in_by_token={
                            token: max(1, int(round(raw * float(size_amount) / float(max(1, int(amount_in))))))
                            for token, raw in token_scan_amounts.items()
                        },
                        observed_gas_price_wei=observed_gas_price_wei,
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
            size_scan_records.append({
                "amount_in": int(amount_in),
                "two": list(base_two),
                "three": list(base_three),
                "two_metrics": dict(base_two_metrics),
                "three_metrics": dict(base_three_metrics),
            })
            candidates_before_probe = len(opps2) + len(opps3)

            def _authoritative_positive_after_cost_count(
                candidates: List[Opportunity],
            ) -> int:
                count = 0
                for candidate in candidates:
                    meta = getattr(candidate, "meta", {}) or {}
                    profitability = meta.get("profitability") if isinstance(meta, dict) else None
                    if not isinstance(profitability, dict):
                        continue
                    if not bool(profitability.get("revalidated")) or not bool(
                        profitability.get("authoritative")
                    ):
                        continue
                    try:
                        if int(profitability.get("profit_after_costs_wei") or 0) > 0:
                            count += 1
                    except (TypeError, ValueError):
                        continue
                return count

            # Probe sufficiency must be measured in authoritative after-cost
            # opportunities, not merely gross candidates. Otherwise two gross
            # near-misses can suppress institutional size discovery even though
            # neither candidate can pay the flashloan fee and gas.
            authoritative_positive_candidates_before_probe = 0
            probe_basis = "gross_candidate_count"
            if candidates_before_probe >= min_opportunities:
                await self._annotate_canonical_after_fee_usd(
                    opps=[*opps2, *opps3],
                    rpc=rpc,
                    current_block=int(current_block),
                    cache=scan_cache,
                )
                authoritative_positive_candidates_before_probe = (
                    _authoritative_positive_after_cost_count([*opps2, *opps3])
                )
                probe_basis = "authoritative_after_cost_positive_count"

            should_probe = (
                force_adaptive_size_scan
                or candidates_before_probe < min_opportunities
                or (
                    candidates_before_probe >= min_opportunities
                    and authoritative_positive_candidates_before_probe < min_opportunities
                )
            )

            # Only expand the discovery universe when the base notional does not
            # provide enough authoritative after-cost opportunities. Alternative
            # sizes are discovery probes, not execution decisions, and are never
            # broadcast automatically.
            if should_probe and len(adaptive_amounts) > 1:
                size_amounts.extend(adaptive_amounts[1:])
                for probe_amount in adaptive_amounts[1:]:
                    probe_two, probe_three, probe_two_metrics, probe_three_metrics = await _run_size_scan(
                        int(probe_amount)
                    )
                    opps2.extend(probe_two)
                    opps3.extend(probe_three)
                    size_scan_records.append({
                        "amount_in": int(probe_amount),
                        "two": list(probe_two),
                        "three": list(probe_three),
                        "two_metrics": dict(probe_two_metrics),
                        "three_metrics": dict(probe_three_metrics),
                    })

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
                        if source.get("size_economic_diagnostics"):
                            target.setdefault("size_economic_diagnostics", [])
                            target["size_economic_diagnostics"].extend(
                                list(source.get("size_economic_diagnostics") or [])
                            )
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

            def _candidate_after_cost(candidate: Opportunity) -> int | None:
                meta = getattr(candidate, "meta", {}) or {}
                if not isinstance(meta, dict):
                    return None
                profitability = meta.get("profitability")
                diagnostic = meta.get("profitability_diagnostic")
                state = profitability if isinstance(profitability, dict) else diagnostic
                if not isinstance(state, dict):
                    return None
                # Authoritative state is preferred, but a fully revalidated
                # loss-making state is still the canonical economic diagnostic.
                # It must participate in sizing/route optimization even though
                # it cannot execute.
                if not bool(state.get("revalidated")):
                    return None
                if "profit_after_costs_wei" not in state and "economic_profit_after_costs_wei" not in state:
                    return None
                try:
                    explicit_economic = state.get("economic_profit_after_costs_wei")
                    if explicit_economic not in (None, ""):
                        return int(explicit_economic)
                    after_cost = int(state.get("profit_after_costs_wei") or 0)
                    if str(state.get("reason") or "") == "does_not_repay_flashloan" or after_cost == -1:
                        return (
                            int(state.get("gross_profit_wei") or 0)
                            - int(state.get("flashloan_fee_wei") or 0)
                            - int(state.get("gas_cost_profit_token_wei") or 0)
                        )
                    return after_cost
                except (TypeError, ValueError):
                    return None

            # Revalidate every scanned candidate before route-size
            # deduplication. Otherwise the sizing selector cannot see the
            # authoritative after-cost economics it is supposed to optimize.
            await self._annotate_canonical_after_fee_usd(
                opps=[*opps2, *opps3],
                rpc=rpc,
                current_block=int(current_block),
                cache=scan_cache,
            )

            def _candidate_profitability(candidate: Opportunity) -> Dict[str, Any]:
                meta = getattr(candidate, "meta", {}) or {}
                if not isinstance(meta, dict):
                    return {}
                state = meta.get("profitability")
                if isinstance(state, dict):
                    return state
                diagnostic = meta.get("profitability_diagnostic")
                return diagnostic if isinstance(diagnostic, dict) else {}

            def _candidate_selection_key(candidate: Opportunity) -> tuple[int, int]:
                after_cost = _candidate_after_cost(candidate)
                return (
                    int(after_cost) if after_cost is not None else -1,
                    int(getattr(candidate, "expected_profit_raw", 0) or 0),
                )

            # Preserve the full diagnostic sizing matrix before route-level
            # deduplication. This is evidence only; it never grants execution authority.
            telemetry["size_economic_diagnostics"] = [
                *list(two_leg_telemetry.get("size_economic_diagnostics") or []),
                *list(three_leg_telemetry.get("size_economic_diagnostics") or []),
            ]
            telemetry["size_economic_evidence"] = [
                {
                    "route_id": _candidate_route_key(candidate),
                    "amount_in": _candidate_amount_in(candidate),
                    "amount_out_wei": str(_candidate_profitability(candidate).get("amount_out_wei") or getattr(candidate, "meta", {}).get("out3") or getattr(candidate, "meta", {}).get("out2") or ""),
                    "gross_profit_wei": str(getattr(candidate, "expected_profit_raw", "0") or "0"),
                    "gas_cost_profit_token_wei": str(_candidate_profitability(candidate).get("gas_cost_profit_token_wei") or "0"),
                    "revalidated": bool(_candidate_profitability(candidate).get("revalidated")),
                    "authoritative": bool(_candidate_profitability(candidate).get("authoritative")),
                    "reason": str(_candidate_profitability(candidate).get("reason") or "unavailable"),
                    "flashloan_fee_wei": str(_candidate_profitability(candidate).get("flashloan_fee_wei") or "0"),
                    "gas_cost_wei": str(
                        _candidate_profitability(candidate).get("gas_cost_wei")
                        or getattr(candidate, "meta", {}).get("gas_cost_estimate_wei")
                        or "0"
                    ),
                    "after_cost_profit_wei": str(
                        _candidate_profitability(candidate).get("profit_after_costs_wei") or "0"
                    ),
                    "economic_after_cost_profit_wei": str(
                        _candidate_after_cost(candidate) or 0
                    ),
                }
                for candidate in [*opps2, *opps3]
            ]
            telemetry["size_economic_evidence"].extend(
                list(telemetry.get("size_economic_diagnostics") or [])
            )

            # Preserve one bounded row per scanned size so production can distinguish
            # "no route quoted" from "route quoted but economically rejected".
            size_matrix = _build_size_economic_matrix(size_scan_records)
            telemetry["size_economic_matrix"] = size_matrix

            telemetry["adaptive_size_discovery"] = {
                "enabled": bool(len(adaptive_amounts) > 1),
                "base_amount_in": str(int(amount_in)),
                "amounts_scanned": [str(int(x)) for x in size_amounts],
                "probe_triggered": bool(len(size_amounts) > 1),
                "minimum_opportunities": int(min_opportunities),
                "candidates_before_probe": int(candidates_before_probe),
                "candidates_after_probe": int(candidates_after_probe),
                "probe_candidate_delta": int(candidates_after_probe - candidates_before_probe),
                "authoritative_positive_candidates_before_probe": int(
                    authoritative_positive_candidates_before_probe
                ),
                "probe_basis": str(probe_basis),
                "distinct_route_ids_before_probe": len({
                    _candidate_route_key(candidate) for candidate in [*base_two, *base_three]
                }),
                "distinct_route_ids_after_probe": len({
                    _candidate_route_key(candidate) for candidate in [*opps2, *opps3]
                }),
                "best_sizing_variants": [
                    {
                        "route_id": _candidate_route_key(candidate),
                        "amount_in": _candidate_amount_in(candidate),
                        "expected_profit_raw": str(getattr(candidate, "expected_profit_raw", "0") or "0"),
                        "revalidated": bool(
                            ((getattr(candidate, "meta", {}) or {}).get("profitability") or {}).get("revalidated")
                        ),
                        "after_cost_profit_wei": str(_candidate_after_cost(candidate) or 0),
                        "selection_basis": (
                            "after_cost_profit"
                            if _candidate_after_cost(candidate) is not None
                            else "gross_profit_fallback"
                        ),
                    }
                    for candidate in sorted(
                        [*opps2, *opps3],
                        key=_candidate_selection_key,
                        reverse=True,
                    )[:80]
                ],
                "borrow_cap_wei": str(
                    max(
                        0,
                        int(
                            getattr(getattr(self, "_bankroll", None), "cfg", None)
                            and getattr(self._bankroll.cfg, "max_borrow_amount_wei", 0)
                            or getattr(getattr(self.cfg, "safety", None), "max_borrow_amount", 0)
                            or 0
                        ),
                    )
                ),
                "size_economic_evidence": list(telemetry.get("size_economic_evidence") or []),
                "economic_matrix_complete": bool(
                    size_amounts
                    and {str(row.get("amount_in")) for row in size_matrix if row.get("amount_in")}
                    .issuperset({str(int(x)) for x in size_amounts})
                ),
            }

            # A route at different sizes is a sizing variant, not a separate
            # venue/route opportunity. Prefer the highest verified after-cost
            # result; gross profit is only a deterministic fallback.
            best_by_route: Dict[str, Opportunity] = {}
            for candidate in [*opps2, *opps3]:
                route_key = _candidate_route_key(candidate)
                current = best_by_route.get(route_key)
                if current is None or _candidate_selection_key(candidate) > _candidate_selection_key(current):
                    best_by_route[route_key] = candidate
            all_opps = list(best_by_route.values())
            opps2 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("two-leg:")]
            opps3 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("tri:")]
            other_opps = [
                o for o in all_opps
                if o not in opps2 and o not in opps3
            ]
            opps = list(opps2) + list(opps3) + other_opps
            # Rank authoritative after-cost truth first. For legacy/unverified
            # candidates, preserve the established after-gas-then-gross numeric ordering
            # so diagnostic scan ordering remains deterministic.
            def _scan_sort_key(candidate: Opportunity) -> tuple[int, int, str]:
                route_id = str(getattr(candidate, "route_id", "") or getattr(candidate, "id", "") or "")
                diagnostic_after_cost = _candidate_after_cost(candidate)
                if diagnostic_after_cost is not None:
                    meta = getattr(candidate, "meta", {}) or {}
                    profitability = meta.get("profitability") if isinstance(meta, dict) else None
                    authoritative = (
                        isinstance(profitability, dict)
                        and bool(profitability.get("revalidated"))
                        and bool(profitability.get("authoritative"))
                    )
                    # Revalidated diagnostic P&L is economically authoritative for
                    # ranking even when it is not executable. Keep the execution
                    # gate separate from this ordering decision.
                    return (3 if authoritative else 2, int(diagnostic_after_cost), route_id)
                meta = getattr(candidate, "meta", {}) or {}
                if isinstance(meta, dict):
                    try:
                        meta_after = meta.get("profit_after_costs")
                        safety = meta.get("safety") if isinstance(meta.get("safety"), dict) else {}
                        safety_after = safety.get("profit_after_costs_wei")
                        if meta_after is not None or safety_after is not None:
                            values = [int(v) for v in (meta_after, safety_after) if v is not None]
                            if values and len(set(values)) == 1:
                                return (3, values[0], route_id)
                    except (TypeError, ValueError):
                        pass
                    try:
                        legacy_value = meta.get("profit_after_gas_estimate_wei")
                        if legacy_value is not None:
                            return (2, int(legacy_value), route_id)
                    except (TypeError, ValueError):
                        pass
                try:
                    gross_value = int(getattr(candidate, "expected_profit_raw", 0) or 0)
                except (TypeError, ValueError):
                    gross_value = 0
                return (2, gross_value, route_id)

            opps.sort(key=_scan_sort_key, reverse=True)
            requests = int(two_leg_telemetry.get("quote_requests", 0)) + int(
                three_leg_telemetry.get("quote_requests", 0)
            )
            successes = int(two_leg_telemetry.get("quote_successes", 0)) + int(
                three_leg_telemetry.get("quote_successes", 0)
            )
            quote_failure_reasons: Dict[str, int] = {}
            route_rejections: Dict[str, int] = {}
            failed_quote_edge_samples: List[str] = []
            for source in (two_leg_telemetry, three_leg_telemetry):
                for key, value in dict(source.get("quote_failure_reasons") or {}).items():
                    quote_failure_reasons[str(key)] = quote_failure_reasons.get(str(key), 0) + int(value)
                for key, value in dict(source.get("route_rejections") or {}).items():
                    route_rejections[str(key)] = route_rejections.get(str(key), 0) + int(value)
                failed_quote_edge_samples.extend(
                    list(source.get("failed_quote_edge_samples") or [])
                )
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
            telemetry["route_universe"] = _canonical_route_universe_telemetry(
                two_leg_telemetry,
                three_leg_telemetry,
            )
            telemetry["gross_candidates"] = len(opps)
            telemetry["route_rejections"] = route_rejections
            telemetry["failed_quote_edge_samples"] = list(
                dict.fromkeys(failed_quote_edge_samples)
            )[:256]
            telemetry["failed_quote_edge_count"] = int(
                len(failed_quote_edge_samples)
            )
            telemetry["scan_latency_ms"] = float(
                (time.perf_counter() - scan_started) * 1000.0
            )
            telemetry["scan_status"] = "completed"
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
            telemetry["scan_status"] = "failed"
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
        shared_token_scan_amounts, shared_token_scan_telemetry = await self._build_token_scan_amounts(
            bootstrap_rpc,
            current_block=int(current_block),
            base_amount_in=int(amount_in),
            cache=PerBlockCache(),
        )
        force_symmetric_sizing = str(
            os.environ.get("VICTOR_RPC_ECONOMIC_SYMMETRIC_SIZING", "1")
        ).strip().lower() not in {"0", "false", "no", "off"}

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
                        shared_token_scan_amounts=shared_token_scan_amounts,
                        force_adaptive_size_scan=force_symmetric_sizing,
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
                            shared_token_scan_amounts=shared_token_scan_amounts,
                            force_adaptive_size_scan=force_symmetric_sizing,
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

        # Provider selection is a comparison gate, not the institutional sizing
        # pass. Keep all providers on the same base notional so quote volume and
        # latency remain bounded; the selected provider gets the full adaptive
        # economic curve below.
        self._rpc_provider_comparison = True
        try:
            results = await asyncio.gather(*(scan_one(url) for url in candidates))
        finally:
            self._rpc_provider_comparison = False
        evidence = [item[4] for item in results]
        selected, ordered = select_best_rpc_evidence(evidence)
        if selected is None:
            selected_url = bootstrap_url or candidates[0]
            selected_result = next(item for item in results if item[0] == selected_url)
        else:
            selected_url = selected.endpoint
            selected_result = next(item for item in results if item[0] == selected_url)

        _, selected_opps, selected_cache, selected_telemetry, _ = selected_result

        # Now that the read provider is selected on comparable base-size
        # economics, perform institutional adaptive sizing exactly once on that
        # provider. This preserves economic-optimum modeling without multiplying
        # the size ladder across every RPC candidate.
        adaptive_cache = PerBlockCache()
        adaptive_telemetry: Dict[str, Any] = {}
        adaptive_opps: List[Opportunity] = []
        selected_provider_url = str(selected_url)
        try:
            if selected_provider_url == bootstrap_url:
                selected_provider_rpc = bootstrap_rpc
                adaptive_opps = await self._scan_primary_opportunities(
                    selected_provider_rpc,
                    current_block=int(current_block),
                    amount_in=int(amount_in),
                    cache=adaptive_cache,
                    discovery_context=discovery_context,
                    telemetry_sink=adaptive_telemetry,
                    shared_token_scan_amounts=shared_token_scan_amounts,
                    force_adaptive_size_scan=True,
                )
            else:
                async with JsonRpcClient(
                    selected_provider_url, timeout_s=10.0, max_concurrency=30, max_batch=80
                ) as selected_provider_rpc:
                    adaptive_opps = await self._scan_primary_opportunities(
                        selected_provider_rpc,
                        current_block=int(current_block),
                        amount_in=int(amount_in),
                        cache=adaptive_cache,
                        discovery_context=discovery_context,
                        telemetry_sink=adaptive_telemetry,
                        shared_token_scan_amounts=shared_token_scan_amounts,
                        force_adaptive_size_scan=True,
                    )
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
            adaptive_telemetry.setdefault("scan_error", f"{type(exc).__name__}: {exc}")
            adaptive_opps = []

        if adaptive_telemetry:
            selected_telemetry = dict(adaptive_telemetry)
            selected_telemetry["rpc"] = dict(selected_telemetry.get("rpc") or {})
            selected_telemetry["rpc"].update({
                "endpoint": selected_url,
                "provider": str(urlsplit(selected_url).hostname or ""),
            })
        if adaptive_opps:
            selected_opps = list(adaptive_opps)
            selected_cache = adaptive_cache

        discovery_runtime = dict(discovery_context.get("runtime") or {})
        if discovery_runtime:
            selected_telemetry.setdefault("discovery", {})["runtime"] = discovery_runtime

        # Provider scans are parallel discovery passes, not mutually exclusive
        # markets. A route can be unquotable on one RPC while quoting normally on
        # another. Keep the economically verified union of healthy provider
        # candidates so provider-local quote failures do not erase opportunities
        # before the execution revalidation gate.
        candidate_by_key: Dict[tuple[str, str], Opportunity] = {}
        provider_candidate_counts: Dict[str, int] = {}
        provider_eligible: Dict[str, bool] = {}
        for url, provider_opps, _cache, _provider_telemetry, provider_evidence in results:
            provider_eligible[str(url)] = bool(provider_evidence.economically_eligible)
            provider_candidate_counts[str(url)] = len(provider_opps or [])
            if not provider_evidence.economically_eligible:
                continue
            for opportunity in list(provider_opps or []):
                route_id = str(getattr(opportunity, "route_id", "") or "")
                meta = getattr(opportunity, "meta", None)
                meta = meta if isinstance(meta, dict) else {}
                try:
                    amount_key = str(
                        getattr(getattr(opportunity, "route", None).legs[0], "amount_in", "")
                    )
                except (AttributeError, IndexError, TypeError):
                    amount_key = ""
                key = (route_id, amount_key)
                if not route_id:
                    key = (str(getattr(opportunity, "id", "") or ""), amount_key)
                meta["quote_provider_endpoint"] = str(url)
                meta["quote_provider"] = str(urlsplit(url).hostname or "")
                existing = candidate_by_key.get(key)
                if existing is None:
                    candidate_by_key[key] = opportunity
                    continue
                existing_meta = getattr(existing, "meta", None)
                existing_meta = existing_meta if isinstance(existing_meta, dict) else {}
                existing_usd = int(
                    ((existing_meta.get("canonical_after_fee_usd") or {}).get(
                        "profit_after_costs_usd_micro"
                    )) or 0
                )
                candidate_usd = int(
                    ((meta.get("canonical_after_fee_usd") or {}).get(
                        "profit_after_costs_usd_micro"
                    )) or 0
                )
                if candidate_usd > existing_usd:
                    candidate_by_key[key] = opportunity

        provider_union_opps = sorted(
            candidate_by_key.values(),
            key=lambda opportunity: (
                -int(
                    (
                        ((getattr(opportunity, "meta", {}) or {}).get(
                            "canonical_after_fee_usd"
                        ) or {}).get("profit_after_costs_usd_micro")
                    )
                    or 0
                ),
                -int(getattr(opportunity, "expected_profit_raw", "0") or "0"),
                str(getattr(opportunity, "route_id", "") or ""),
            ),
        )
        if provider_union_opps:
            selected_opps = provider_union_opps

        provider_symmetry: List[Dict[str, Any]] = []
        route_universes: List[Dict[str, Any]] = []
        size_ladders: List[tuple[str, ...]] = []
        token_ladders: List[tuple[tuple[str, str], ...]] = []
        for url, _opps, _cache, provider_telemetry, _provider_evidence in results:
            adaptive = dict(provider_telemetry.get("adaptive_size_discovery") or {})
            sizing = dict(provider_telemetry.get("scan_sizing") or {})
            universe = dict(provider_telemetry.get("route_universe") or {})
            quotes = dict(provider_telemetry.get("quotes") or {})
            failures = dict(quotes.get("failure_reasons") or {})
            route_rejections = dict(provider_telemetry.get("route_rejections") or {})
            amounts_scanned = tuple(str(x) for x in adaptive.get("amounts_scanned") or [])
            amounts_by_token = tuple(
                sorted(
                    (str(k), str(v))
                    for k, v in dict(sizing.get("amounts_by_token") or {}).items()
                )
            )
            route_universes.append(universe)
            size_ladders.append(amounts_scanned)
            token_ladders.append(amounts_by_token)
            provider_symmetry.append({
                "endpoint": url,
                "provider": str(urlsplit(url).hostname or ""),
                "block_number": int(current_block),
                "route_universe": universe,
                "amounts_scanned": list(amounts_scanned),
                "amounts_by_token": dict(sizing.get("amounts_by_token") or {}),
                "quote_requests": int(quotes.get("requests", 0) or 0),
                "quote_successes": int(quotes.get("successes", 0) or 0),
                "quote_failure_reasons": failures,
                "route_rejections": route_rejections,
                "failed_quote_edge_count": int(
                    provider_telemetry.get("failed_quote_edge_count", 0) or 0
                ),
                "failed_quote_edge_samples": list(
                    provider_telemetry.get("failed_quote_edge_samples") or []
                )[:256],
                "failed_quotes_removed_from_candidates": True,
            })
        route_universe_equal = bool(route_universes) and all(
            universe == route_universes[0] for universe in route_universes[1:]
        )
        size_ladder_equal = bool(size_ladders) and all(
            ladder == size_ladders[0] for ladder in size_ladders[1:]
        )
        token_ladder_equal = bool(token_ladders) and all(
            ladder == token_ladders[0] for ladder in token_ladders[1:]
        )

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
            "provider_scan_symmetry": {
                "route_universe_identical": route_universe_equal,
                "size_ladder_identical": size_ladder_equal,
                "token_size_ladder_identical": token_ladder_equal,
                "same_block": all(
                    int(row.get("block_number") or -1) == int(current_block)
                    for row in provider_symmetry
                ),
                "failure_classification_shared": True,
                "failed_quotes_are_non_candidates": True,
                "shared_token_sizing": dict(shared_token_scan_telemetry),
                "providers": provider_symmetry,
                "opportunity_union": {
                    "enabled": True,
                    "healthy_provider_count": int(sum(1 for value in provider_eligible.values() if value)),
                    "provider_candidate_counts": dict(provider_candidate_counts),
                    "unique_route_amount_candidates": int(len(candidate_by_key)),
                    "selected_provider_remains_execution_context": True,
                },
            },
        }
        return {
            "selected_endpoint": selected_url,
            "opps": selected_opps,
            "cache": selected_cache,
            "telemetry": selected_telemetry,
            "evidence": evidence,
        }

    @staticmethod
    def _discovery_timeout_s() -> float:
        """Return the bounded discovery budget for one discovery stage."""
        try:
            configured = float(
                os.environ.get("VICTOR_DISCOVERY_TIMEOUT_S", "2.0") or 2.0
            )
        except (TypeError, ValueError):
            configured = 2.0
        return max(0.25, min(configured, 10.0))

    async def _build_discovery_context(
        self,
        rpc: Any,
        *,
        current_block: int,
    ) -> Dict[str, Any]:
        """Build discovery context without allowing discovery to starve scanning.

        Discovery is an opportunity-expansion input, not a prerequisite for
        operating on the already-persisted/configured route universe. Each
        discovery stage therefore gets its own bounded budget and falls back to
        persisted observations when the provider is slow or unavailable.
        """
        timeout_s = self._discovery_timeout_s()
        discovery = getattr(self, "_discovery", None)
        v3_fallback = (
            list(discovery.v3_pairs())
            if discovery is not None
            and callable(getattr(discovery, "v3_pairs", None))
            else []
        )
        venue_fallback = {
            "curve": (
                list(discovery.curve_pools())
                if discovery is not None
                and callable(getattr(discovery, "curve_pools", None))
                else []
            ),
            "balancer": (
                list(discovery.balancer_pools())
                if discovery is not None
                and callable(getattr(discovery, "balancer_pools", None))
                else []
            ),
        }
        stages: List[Dict[str, Any]] = []

        async def bounded_stage(
            name: str,
            operation: Any,
            fallback: Any,
        ) -> Any:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(operation, timeout=timeout_s)
                stages.append(
                    {
                        "stage": name,
                        "status": "completed",
                        "elapsed_ms": float(
                            (time.perf_counter() - started) * 1000.0
                        ),
                        "timeout_s": float(timeout_s),
                    }
                )
                return result
            except (TimeoutError, asyncio.TimeoutError):
                stages.append(
                    {
                        "stage": name,
                        "status": "timed_out",
                        "elapsed_ms": float(
                            (time.perf_counter() - started) * 1000.0
                        ),
                        "timeout_s": float(timeout_s),
                    }
                )
                return fallback
            except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                stages.append(
                    {
                        "stage": name,
                        "status": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsed_ms": float(
                            (time.perf_counter() - started) * 1000.0
                        ),
                        "timeout_s": float(timeout_s),
                    }
                )
                return fallback

        extra_v3_pairs = await bounded_stage(
            "univ3",
            self._discover_extra_v3_pairs(
                rpc, current_block=int(current_block)
            ),
            v3_fallback,
        )

        venue_pools = venue_fallback
        discover_venues = (
            getattr(discovery, "maybe_discover_venues", None)
            if discovery is not None
            else None
        )
        if callable(discover_venues):
            venue_pools = await bounded_stage(
                "venues",
                discover_venues(rpc, self.cfg, int(current_block)),
                venue_fallback,
            )

        return {
            "v3_pairs": list(extra_v3_pairs or []),
            "curve_pools": list(venue_pools.get("curve") or []),
            "balancer_pools": list(venue_pools.get("balancer") or []),
            "runtime": {
                "budget_timeout_s": float(timeout_s),
                "stages": stages,
                "used_persisted_fallback": any(
                    stage.get("status") != "completed" for stage in stages
                ),
            },
        }