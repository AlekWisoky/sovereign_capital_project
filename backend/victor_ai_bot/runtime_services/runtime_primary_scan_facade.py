from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List
from urllib.parse import urlsplit

from ..arb_engine import build_edges, find_three_leg_opportunities, find_two_leg_opportunities, requote_opportunity
from ..execution_capture.final_quote import FinalQuoteError, produce_market_price_evidence
from ..cache import PerBlockCache
from ..gas_model import BASE_CHAIN_ID, estimate_base_l1_fee_wei, estimate_gas_cost_wei_from_cfg, estimate_route_gas_units
from ..models import Opportunity
from ..calldata_builder import build_execute_calldata
from ..rpc import JsonRpcClient
from ..rpc_economic_selector import RpcEconomicEvidence, select_best_rpc_evidence
from ..profitability_state import revalidate_profitability_state
from ..flashloan_providers import observe_flashloan_fee_bps
from ..usd_pricing import gas_wei_to_token_wei, token_to_usd_micro
from .profitability_truth import opportunity_profit_sort_key

_SAFE_SCAN_TELEMETRY_EXCEPTIONS = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)


async def _gather_selected_provider_scan_batch(
    tasks: List[asyncio.Task],
    chunk_indices: List[int],
    scan_errors: List[Dict[str, Any]],
) -> None:
    """Wait for every rescue chunk and contain unexpected per-task failures."""
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for chunk_index, result in zip(chunk_indices, results):
        if isinstance(result, asyncio.CancelledError):
            scan_errors.append({
                "chunk": int(chunk_index),
                "reason": "selected_provider_full_scan_chunk_cancelled",
            })
        elif isinstance(result, Exception):
            scan_errors.append({
                "chunk": int(chunk_index),
                "reason": f"{type(result).__name__}: {result}",
            })
        elif isinstance(result, BaseException):
            raise result


def _selected_provider_full_scan_chunk_order(
    *,
    graph_edge_count: int,
    chunk_size: int,
    rotation_index: int,
) -> List[int]:
    """Rotate the first graph slice each block so a bounded scan eventually covers all edges."""
    edge_count = max(0, int(graph_edge_count))
    size = max(1, int(chunk_size))
    chunk_count = max(1, (edge_count + size - 1) // size)
    start = max(0, int(rotation_index)) % chunk_count
    return [(start + offset) % chunk_count for offset in range(chunk_count)]


def _selected_provider_chunk_accounting(
    *,
    graph_edge_count: int,
    chunk_size: int,
    chunk_statuses: Dict[int, str],
    chunk_status_reasons: Dict[int, str],
) -> Dict[str, Any]:
    """Account for every scheduled, failed, timed-out, or budget-skipped graph slice."""
    edge_count = max(0, int(graph_edge_count))
    size = max(1, int(chunk_size))
    total = max(1, (edge_count + size - 1) // size)
    statuses = {int(index): str(status) for index, status in chunk_statuses.items()}
    reasons = {int(index): str(reason) for index, reason in chunk_status_reasons.items()}
    for index in range(total):
        status = statuses.get(index, "pending")
        if status == "pending":
            statuses[index] = "skipped_budget"
            reasons[index] = "budget_exhausted_before_schedule"
        elif status == "running":
            # A task that escaped its local exception boundary is not left unaccounted.
            statuses[index] = "failed"
            reasons[index] = "task_failed_outside_chunk_boundary"
    rows = [
        {
            "index": index,
            "offset": index * size,
            "edges": min(size, max(0, edge_count - index * size)),
            "status": statuses[index],
            **({"reason": reasons[index]} if index in reasons else {}),
        }
        for index in range(total)
    ]
    final_statuses = [row["status"] for row in rows]
    return {
        "chunk_accounting": rows,
        "chunks_timed_out": sum(status == "timed_out" for status in final_statuses),
        "chunks_failed": sum(status == "failed" for status in final_statuses),
        "chunks_skipped": sum(status == "skipped_budget" for status in final_statuses),
        "chunks_accounted": sum(
            status in {"completed", "timed_out", "failed", "skipped_budget"}
            for status in final_statuses
        ),
    }


def _selected_provider_frontier_slice_offset(
    *,
    graph_edge_count: int,
    edge_cap: int,
    seed_index: int,
    seed_count: int,
    rotation_index: int = 0,
) -> int:
    """Spread bounded frontier probes over the graph and rotate coverage each block."""
    edge_count = max(0, int(graph_edge_count))
    cap = max(1, int(edge_cap))
    count = max(1, int(seed_count))
    max_offset = max(0, edge_count - cap)
    if count == 1:
        base_offset = max_offset // 2
    else:
        index = max(0, min(int(seed_index), count - 1))
        base_offset = int(round(float(max_offset) * float(index) / float(count - 1)))

    # Keep the initial evenly-spaced sampling stable, but do not repeatedly scan
    # the same three graph windows forever. Rotating by bounded edge-sized slots
    # lets successive blocks cover the graph without increasing per-tick quote work.
    rotation = max(0, int(rotation_index))
    if rotation == 0 or max_offset <= 0:
        return base_offset
    chunk_count = max(1, (edge_count + cap - 1) // cap)
    base_chunk = min(chunk_count - 1, base_offset // cap)
    rotated_chunk = (base_chunk + rotation) % chunk_count
    return min(max_offset, int(rotated_chunk * cap))


class _FrozenProviderScanPoolEventCache:
    """Immutable provider-comparison graph and edge-priority view for one tick."""

    def __init__(
        self,
        edges: List[Any],
        telemetry: Dict[str, Any],
        priorities: Dict[int, int],
        route_universe_edges: List[Any] | None = None,
    ) -> None:
        self._edges = list(edges or [])
        self._route_universe_edges = list(
            route_universe_edges if route_universe_edges is not None else self._edges
        )
        self._telemetry = dict(telemetry or {})
        self._priorities = dict(priorities or {})

    def refresh_edges(self, *args: Any, **kwargs: Any) -> None:
        return None

    def candidate_edges(
        self,
        edges: List[Any],
        *,
        current_block: int,
        max_candidates: int = 768,
        exploration_ratio: float = 0.10,
    ) -> tuple[List[Any], Dict[str, Any]]:
        del edges, current_block, max_candidates, exploration_ratio
        return list(self._edges), dict(self._telemetry)

    def edge_priority(self, edge: Any, *, current_block: int) -> int:
        del current_block
        return int(self._priorities.get(id(edge), 1))

    def edge_count(self) -> int:
        return int(len(self._edges))

    def route_universe_edges(self) -> List[Any]:
        """Return the immutable route universe retained across bounded scan slices."""
        return list(self._route_universe_edges)

    def slice(self, start: int, limit: int) -> "_FrozenProviderScanPoolEventCache":
        offset = max(0, int(start))
        count = max(0, int(limit))
        selected = list(self._edges[offset: offset + count])
        telemetry = dict(self._telemetry)
        telemetry["candidate_edge_count"] = int(len(selected))
        telemetry["candidate_edges_full"] = int(self._telemetry.get("candidate_edges_full") or len(self._edges))
        telemetry["candidate_edges_pruned"] = int(
            max(0, int(telemetry["candidate_edges_full"]) - len(selected))
        )
        telemetry["provider_comparison_slice_offset"] = int(offset)
        telemetry["provider_comparison_slice_limit"] = int(count)
        priorities = {id(edge): int(self._priorities.get(id(edge), 1)) for edge in selected}
        return _FrozenProviderScanPoolEventCache(
            selected,
            telemetry,
            priorities,
            route_universe_edges=self._route_universe_edges,
        )



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


def _candidate_economic_after_cost_for_sizing(candidate: Any) -> int | None:
    """Return signed P&L for sizing diagnostics only, never execution authority."""
    meta = getattr(candidate, "meta", {}) or {}
    if not isinstance(meta, dict):
        return None
    state = meta.get("profitability")
    if not isinstance(state, dict):
        state = meta.get("profitability_diagnostic")
    if not isinstance(state, dict) or not bool(state.get("revalidated")):
        return None
    explicit = state.get("economic_profit_after_costs_wei")
    if explicit not in (None, ""):
        try:
            return int(explicit)
        except (TypeError, ValueError, OverflowError):
            return None
    try:
        after_cost = int(state.get("profit_after_costs_wei"))
    except (TypeError, ValueError, OverflowError):
        return None
    if str(state.get("reason") or "") == "does_not_repay_flashloan" or after_cost == -1:
        gas_token_raw = state.get("gas_cost_profit_token_wei")
        # Do not subtract native gas units from profit-token units.
        if gas_token_raw in (None, ""):
            return None
        try:
            gross_raw = state.get("gross_profit_wei")
            gross = int(
                gross_raw if gross_raw not in (None, "")
                else getattr(candidate, "expected_profit_raw", 0)
            )
            fee = int(state.get("flashloan_fee_wei") or 0)
            gas_token = int(gas_token_raw)
        except (TypeError, ValueError, OverflowError):
            return None
        return gross - fee - gas_token
    return after_cost


def _candidate_sizing_sort_key(candidate: Any) -> tuple[int, int, int, int, str]:
    """Prefer verified executable positives, then best signed economic evidence."""
    meta = getattr(candidate, "meta", {}) or {}
    meta = meta if isinstance(meta, dict) else {}
    state = meta.get("profitability")
    if not isinstance(state, dict):
        state = meta.get("profitability_diagnostic")
    state = state if isinstance(state, dict) else {}
    economic = _candidate_economic_after_cost_for_sizing(candidate)
    try:
        canonical_after_cost = int(state.get("profit_after_costs_wei") or 0)
    except (TypeError, ValueError, OverflowError):
        canonical_after_cost = 0
    executable_positive = bool(
        state.get("revalidated")
        and state.get("authoritative")
        and state.get("valid")
        and canonical_after_cost > 0
    )
    try:
        gross = int(getattr(candidate, "expected_profit_raw", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        gross = 0
    route_id = str(
        getattr(candidate, "route_id", "") or getattr(candidate, "id", "") or ""
    )
    return (
        int(executable_positive),
        int(economic is not None),
        int(economic) if economic is not None else gross,
        gross,
        route_id,
    )


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
        "after_cost_profit_usd_micro": str((meta.get("canonical_after_fee_usd") or {}).get("profit_after_costs_usd_micro") or "0"),
        "economic_after_cost_profit_wei": str(fields["economic_after_cost_profit_wei"]),
        "revalidated": bool(profitability.get("revalidated")),
        "authoritative": bool(profitability.get("authoritative")),
        "valid": bool(profitability.get("valid")),
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


def _attach_quote_economic_size_curves(
    opportunities: List[Opportunity], size_matrix: List[Dict[str, Any]]
) -> None:
    """Attach the observed quote-derived economic frontier to each route."""
    curves: Dict[str, List[Dict[str, Any]]] = {}
    bases: Dict[str, int] = {}
    for matrix_row in list(size_matrix or []):
        for candidate in list(matrix_row.get("candidates") or []):
            if not isinstance(candidate, dict):
                continue
            route_id = str(candidate.get("route_id") or "")
            if not route_id:
                continue
            try:
                candidate_amount = int(candidate.get("amount_in") or 0)
                usd_micro = int(candidate.get("after_cost_profit_usd_micro") or 0)
            except (TypeError, ValueError):
                continue
            if candidate_amount <= 0:
                continue
            bases[route_id] = min(bases.get(route_id, candidate_amount), candidate_amount)
            curves.setdefault(route_id, []).append(
                {
                    "amount_in": candidate_amount,
                    "after_cost_profit_usd": float(usd_micro) / 1_000_000.0,
                }
            )
    for opportunity in list(opportunities or []):
        route_id = str(getattr(opportunity, "route_id", "") or getattr(opportunity, "id", "") or "")
        points = curves.get(route_id) or []
        base = int(bases.get(route_id) or 0)
        if not points or base <= 0:
            continue
        points.sort(key=lambda row: int(row.get("amount_in") or 0))
        meta = getattr(opportunity, "meta", None)
        if not isinstance(meta, dict):
            continue
        meta["quote_economic_size_curve"] = [
            {
                "size_mult": float(int(point["amount_in"]) / base),
                "after_cost_profit_usd": float(point["after_cost_profit_usd"]),
            }
            for point in points[:16]
        ]


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




def _merge_size_economic_matrices(
    *matrices: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge sampled and route-requoted evidence without losing per-size economics."""
    merged_by_amount: Dict[str, Dict[str, Any]] = {}
    sources_by_amount: Dict[str, List[str]] = {}
    samples_by_amount: Dict[str, List[Dict[str, Any]]] = {}

    def candidate_key(row: Dict[str, Any]) -> tuple[str, str]:
        return (
            str(row.get("route_id") or ""),
            str(row.get("amount_in") or ""),
        )

    def candidate_rank(row: Dict[str, Any]) -> tuple[int, int, int, int]:
        try:
            after_cost = int(row.get("after_cost_profit_wei") or 0)
        except (TypeError, ValueError, OverflowError):
            after_cost = 0
        try:
            economic = int(_economic_after_cost_profit(row) or 0)
        except (TypeError, ValueError, OverflowError):
            economic = after_cost
        valid_authority = bool(
            row.get("revalidated") and row.get("authoritative") and row.get("valid")
        )
        return (
            int(valid_authority and after_cost > 0),
            int(valid_authority),
            int(bool(row.get("revalidated") or row.get("diagnostic_only"))),
            economic,
        )

    for matrix in matrices:
        for source_row in list(matrix or []):
            if not isinstance(source_row, dict):
                continue
            amount = str(source_row.get("amount_in") or "")
            try:
                if int(amount) <= 0:
                    continue
            except (TypeError, ValueError, OverflowError):
                continue

            incoming = dict(source_row)
            incoming_candidates = [
                dict(row)
                for row in list(incoming.get("candidates") or [])
                if isinstance(row, dict)
            ]
            source_name = (
                "sampled_graph_frontier"
                if bool(incoming.get("frontier_seed_sampled"))
                else "selected_provider_size_scan"
            )
            existing = merged_by_amount.get(amount)
            if existing is None:
                merged_by_amount[amount] = incoming
                existing_candidates = incoming_candidates
                merged_by_amount[amount]["candidates"] = existing_candidates
                sources_by_amount[amount] = [source_name]
            else:
                sources = sources_by_amount.setdefault(amount, [])
                if source_name not in sources:
                    sources.append(source_name)
                existing_candidates = [
                    dict(row)
                    for row in list(existing.get("candidates") or [])
                    if isinstance(row, dict)
                ]
                by_candidate = {
                    candidate_key(row): row
                    for row in existing_candidates
                    if candidate_key(row)[0]
                }
                for candidate in incoming_candidates:
                    key = candidate_key(candidate)
                    if not key[0]:
                        existing_candidates.append(candidate)
                        continue
                    prior = by_candidate.get(key)
                    if prior is None:
                        existing_candidates.append(candidate)
                        by_candidate[key] = candidate
                    elif candidate_rank(candidate) > candidate_rank(prior):
                        prior_index = existing_candidates.index(prior)
                        existing_candidates[prior_index] = candidate
                        by_candidate[key] = candidate

                for metric in ("quote_requests", "quote_successes", "failed_quote_edge_count"):
                    existing[metric] = int(existing.get(metric, 0) or 0) + int(
                        incoming.get(metric, 0) or 0
                    )
                existing["quote_failures"] = max(
                    0,
                    int(existing.get("quote_requests", 0) or 0)
                    - int(existing.get("quote_successes", 0) or 0),
                )
                failure_reasons = dict(existing.get("quote_failure_reasons") or {})
                for reason, count in dict(incoming.get("quote_failure_reasons") or {}).items():
                    failure_reasons[str(reason)] = int(failure_reasons.get(str(reason), 0) or 0) + int(count or 0)
                existing["quote_failure_reasons"] = failure_reasons
                samples = [
                    *list(existing.get("failed_quote_edge_samples") or []),
                    *list(incoming.get("failed_quote_edge_samples") or []),
                ]
                unique_samples = []
                seen_samples = set()
                for sample in samples:
                    identity = str(sample)
                    if identity in seen_samples:
                        continue
                    seen_samples.add(identity)
                    unique_samples.append(sample)
                existing["failed_quote_edge_samples"] = unique_samples[:256]
                existing["candidates"] = existing_candidates
                existing["frontier_seed_sampled"] = bool(
                    existing.get("frontier_seed_sampled")
                    or incoming.get("frontier_seed_sampled")
                )

            target = merged_by_amount[amount]
            if source_name not in sources_by_amount.setdefault(amount, []):
                sources_by_amount[amount].append(source_name)
            if bool(incoming.get("frontier_seed_sampled")):
                sample = {
                    "edge_offset": incoming.get("frontier_seed_edge_offset"),
                    "edge_cap": incoming.get("frontier_seed_edge_cap"),
                    "graph_edge_count": incoming.get("frontier_seed_graph_edge_count"),
                    "rotation_index": incoming.get("frontier_seed_rotation_index"),
                }
                sample_key = tuple(str(sample.get(k)) for k in (
                    "edge_offset", "edge_cap", "graph_edge_count", "rotation_index"
                ))
                known = {
                    tuple(str(item.get(k)) for k in (
                        "edge_offset", "edge_cap", "graph_edge_count", "rotation_index"
                    ))
                    for item in samples_by_amount.setdefault(amount, [])
                }
                if sample_key not in known:
                    samples_by_amount[amount].append(sample)

    merged: List[Dict[str, Any]] = []
    for amount, row in merged_by_amount.items():
        candidates = [
            dict(item)
            for item in list(row.get("candidates") or [])
            if isinstance(item, dict)
        ]
        selected, economic = _size_matrix_selection(candidates)
        row["route_ids"] = list(dict.fromkeys(
            str(item.get("route_id") or "") for item in candidates
            if str(item.get("route_id") or "")
        ))
        row["selection_basis"] = (
            "verified_after_cost_profit"
            if selected
            else (
                "economic_optimum_diagnostic"
                if economic
                else "no_economic_evidence"
            )
        )
        if economic and not selected and str(economic.get("reason") or "") == "non_positive_gross_profit":
            row["selection_basis"] = "gross_profit_diagnostic_only"
        row["selected_route_id"] = str(selected.get("route_id") or "") if selected else ""
        row["selected_after_cost_profit_wei"] = str(selected.get("after_cost_profit_wei") or "0") if selected else "0"
        row["economic_optimum_route_id"] = str(economic.get("route_id") or "") if economic else ""
        row["economic_optimum_after_cost_profit_wei"] = (
            str(_economic_after_cost_profit(economic))
            if economic and _economic_after_cost_profit(economic) is not None
            else "0"
        )
        row["economic_optimum_authoritative"] = bool(economic and economic.get("authoritative"))
        row["economic_optimum_executable"] = bool(selected)
        row["evidence_sources"] = list(sources_by_amount.get(amount) or [])
        row["frontier_seed_samples"] = list(samples_by_amount.get(amount) or [])
        row["evidence_only"] = True
        row["execution_authority_granted"] = False
        merged.append(row)

    return sorted(merged, key=lambda row: int(row.get("amount_in") or 0))


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
        observed_gas_price_wei: int | None = None,
        gas_price_integrity: Dict[str, Any] | None = None,
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
        if observed_gas_price_wei is None and gas_price_integrity is None:
            rpc_manager = getattr(self, "rpc_manager", None)
            if rpc_manager is not None and callable(getattr(rpc_manager, "gas_price_consensus", None)):
                try:
                    consensus = await rpc_manager.gas_price_consensus()
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    consensus = {"gas_price_wei": None, "status": "insufficient_agreement", "observations": [], "anomalies": []}
                observed_gas_price_wei = (
                    int(consensus.get("gas_price_wei"))
                    if consensus.get("gas_price_wei") not in (None, "")
                    else None
                )
                gas_price_integrity = dict(consensus)
            else:
                # Direct facade callers without the runtime bundle retain their
                # explicit RPC observation. Production runtime has rpc_manager.
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

            l1_fee_wei = 0
            l1_fee_status = "not_applicable"
            if int(getattr(getattr(self.cfg, "chain", None), "chain_id", 0) or 0) == BASE_CHAIN_ID:
                l1_fee_status = "execution_envelope_unconfigured"
                try:
                    execution_cfg = getattr(self.cfg, "execution", None)
                    profit_to = str(getattr(execution_cfg, "profit_to", "") or "")
                    provider = str(getattr(execution_cfg, "flash_provider", "aave") or "aave")
                    executor = str(getattr(execution_cfg, "executor_address", "") or "")
                    legs = list(getattr(getattr(opportunity, "route", None), "legs", []) or [])
                    if not profit_to or not executor:
                        missing = []
                        if not executor:
                            missing.append("executor_address")
                        if not profit_to:
                            missing.append("profit_to")
                        meta["base_execution_envelope"] = {
                            "configured": False,
                            "missing_fields": missing,
                        }
                    elif not legs:
                        l1_fee_status = "calldata_unavailable"
                    else:
                        min_abs = int(getattr(getattr(self.cfg, "safety", None), "minProfitAbs", 0) or 0)
                        min_bps = int(getattr(getattr(self.cfg, "safety", None), "minProfitBps", 0) or 0)
                        amount_borrow = int(getattr(legs[0], "amount_in", 0) or 0)
                        if amount_borrow <= 0:
                            amount_borrow = int(meta.get("amount_in") or 0)
                        min_profit_onchain = max(min_abs, amount_borrow * min_bps // 10_000)
                        deadline = int(time.time()) + int(getattr(execution_cfg, "deadline_seconds", 30) or 30)
                        calldata_legs = [
                            {
                                "dex": str(leg.dex),
                                "venue": str(leg.venue),
                                "token_in": str(leg.token_in),
                                "token_out": str(leg.token_out),
                                "min_out": int(str(leg.min_out)),
                                "aux": str(leg.data or "0x"),
                            }
                            for leg in legs
                        ]
                        calldata, _ = build_execute_calldata(
                            provider=provider,
                            borrow_token=str(legs[0].token_in),
                            amount_borrow=amount_borrow,
                            min_profit=min_profit_onchain,
                            profit_to=profit_to,
                            deadline=deadline,
                            legs=calldata_legs,
                        )
                        cache_key = f"base:l1fee:{calldata}"
                        cached_l1 = scan_cache.get(cache_key)
                        if cached_l1 is not None:
                            l1_fee_wei = int(cached_l1)
                            l1_fee_status = "exact_calldata_cached"
                        else:
                            queried_l1 = await estimate_base_l1_fee_wei(
                                rpc,
                                calldata,
                                block=f"0x{int(current_block):x}",
                            )
                            if queried_l1 is not None:
                                l1_fee_wei = int(queried_l1)
                                scan_cache.set(cache_key, l1_fee_wei)
                                l1_fee_status = "exact_calldata"
                            else:
                                l1_fee_status = "oracle_unavailable"
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
                    l1_fee_status = "calldata_build_failed"

                if l1_fee_status in {
                    "oracle_unavailable",
                    "calldata_build_failed",
                    "calldata_unavailable",
                    "execution_envelope_unconfigured",
                }:
                    # Base economics must not be authorized without the L1 data
                    # component when the exact executor envelope cannot be priced.
                    l1_fee_wei = 0

            gas_cost_wei += int(l1_fee_wei)
            if isinstance(meta, dict):
                meta["base_l1_fee_wei"] = str(int(l1_fee_wei))
                meta["base_l1_fee_status"] = l1_fee_status

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

            base_l1_pricing_required = int(getattr(getattr(self.cfg, "chain", None), "chain_id", 0) or 0) == BASE_CHAIN_ID
            if has_route_gas_inputs and (observed_gas_price_wei is None or (base_l1_pricing_required and l1_fee_status not in {"exact_calldata", "exact_calldata_cached"})):
                state = {
                    "stage": "scan_after_fee_revalidation",
                    "source": "runtime_primary_scan",
                    "reason": (
                        "gas_price_consensus_unavailable"
                        if observed_gas_price_wei is None
                        else (
                            "base_execution_envelope_unconfigured"
                            if l1_fee_status == "execution_envelope_unconfigured"
                            else "base_l1_fee_unavailable"
                        )
                    ),
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
                meta["profitability_diagnostic"] = dict(state)
                continue
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
            if profit_after_wei == 0 or not usd_enabled:
                continue
            try:
                profit_token = str(opportunity.route.legs[0].token_in)
            except (AttributeError, IndexError, TypeError, ValueError):
                continue
            usd_after = await token_to_usd_micro(
                rpc,
                chain=self.cfg.chain,
                token=profit_token,
                amount_wei=abs(profit_after_wei),
                block_number=int(current_block),
                cache=scan_cache,
                preference=preference,
            )
            if usd_after is None or int(usd_after) <= 0:
                continue
            signed_usd_after = int(usd_after) if profit_after_wei > 0 else -int(usd_after)
            state["profit_after_costs_usd_micro"] = int(signed_usd_after)
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
                "profit_after_costs_usd_micro": str(int(signed_usd_after)),
                "block_number": int(current_block),
            }

    def _adaptive_scan_amounts(self, amount_in: int, *, force_adaptive_size_scan: bool = False) -> List[int]:
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
        if bool(getattr(self, "_rpc_provider_comparison", False)) and not bool(
            force_adaptive_size_scan
        ):
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
        """Translate the reference borrow notional into bounded raw units per input token.

        The configured token universe remains the only execution-authority boundary.
        A small deterministic research frontier may participate in read-only market
        pricing so discovered pools can reach the quote/economic funnel without
        mutating execution configuration.
        """
        chain = getattr(self.cfg, "chain", None)
        configured_tokens: List[str] = []
        configured_seen: set[str] = set()
        for raw_token in list(getattr(chain, "token_universe", []) or []):
            token = str(raw_token or "").strip()
            key = token.lower()
            if token and key not in configured_seen:
                configured_seen.add(key)
                configured_tokens.append(token)

        weth = str(getattr(chain, "weth", "") or "").strip()
        research_tokens: List[str] = []
        research_cap = 8
        try:
            research_cap = max(
                0,
                min(
                    16,
                    int(os.environ.get("VICTOR_RESEARCH_TOKEN_SCAN_CAP", "8") or 8),
                ),
            )
        except (TypeError, ValueError):
            research_cap = 8

        discovery = getattr(self, "_discovery", None)
        frontier_getter = getattr(discovery, "research_frontier_tokens", None)
        if callable(frontier_getter) and research_cap:
            try:
                raw_frontier = frontier_getter(self.cfg, cap=research_cap)
            except (AttributeError, TypeError, ValueError):
                raw_frontier = []
            for raw_token in list(raw_frontier or []):
                token = str(raw_token or "").strip()
                key = token.lower()
                if (
                    token
                    and key not in configured_seen
                    and key not in {item.lower() for item in research_tokens}
                ):
                    research_tokens.append(token)
                if len(research_tokens) >= research_cap:
                    break

        tokens = [*configured_tokens, *research_tokens]
        telemetry: Dict[str, Any] = {
            "enabled": False,
            "source": "",
            "reference_token": weth,
            "base_amount_in": str(int(base_amount_in)),
            "amounts_by_token": {},
            "unpriced_tokens": [],
            "configured_tokens": int(len(configured_tokens)),
            "research_tokens_considered": int(len(research_tokens)),
            "research_tokens_priced": 0,
            "research_tokens_unpriced": [],
            "research_token_scan_notional_source": (
                "bounded_research_frontier_quote_derived_usd"
                if research_tokens
                else "configured_execution_universe_quote_derived_usd"
            ),
            "research_token_scan_cap": int(research_cap),
            "research_token_execution_universe_mutated": False,
        }
        if not tokens or not weth:
            return {}, telemetry

        try:
            evidence = await produce_market_price_evidence(
                rpc,
                cfg=self.cfg,
                tokens=[(token, "scan_input") for token in tokens],
                block_number=int(current_block),
                strict=False,
            )
        except (FinalQuoteError, OSError, RuntimeError, TypeError, ValueError):
            telemetry["source"] = "reference_token_fallback"
            fallback = max(1, int(base_amount_in))
            telemetry["amounts_by_token"] = {weth.lower(): str(fallback)}
            telemetry["unpriced_tokens"] = [
                token for token in tokens if token.lower() != weth.lower()
            ]
            research_unpriced = list(research_tokens)
            telemetry["research_tokens_unpriced"] = research_unpriced
            telemetry["research_tokens_priced"] = 0
            return {weth.lower(): fallback}, telemetry

        ref = evidence.get(weth.lower())
        if not isinstance(ref, dict):
            telemetry["source"] = "reference_token_unpriced"
            telemetry["unpriced_tokens"] = list(tokens)
            telemetry["research_tokens_unpriced"] = list(research_tokens)
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
            telemetry["research_tokens_unpriced"] = list(research_tokens)
            return {}, telemetry

        amounts: Dict[str, int] = {}
        unpriced: List[str] = []
        for token in tokens:
            row = evidence.get(token.lower())
            if not isinstance(row, dict):
                unpriced.append(token)
                continue
            try:
                decimals = int(row["decimals"])
                price_usd = float(row["price_usd"])
                if price_usd <= 0:
                    raise ValueError("token_price_non_positive")
                raw = int(
                    max(
                        1.0,
                        round(
                            reference_usd
                            / price_usd
                            * float(10 ** decimals)
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
                unpriced.append(token)
                continue
            amounts[token.lower()] = raw

        research_unpriced = [
            token for token in research_tokens if token.lower() in {item.lower() for item in unpriced}
        ]
        telemetry["enabled"] = bool(amounts)
        telemetry["source"] = (
            "bounded_research_frontier_quote_derived_usd_notional"
            if research_tokens
            else "quote_derived_usd_notional"
        )
        telemetry["reference_notional_usd"] = float(reference_usd)
        telemetry["amounts_by_token"] = {
            token: str(amount) for token, amount in amounts.items()
        }
        telemetry["unpriced_tokens"] = list(unpriced)
        telemetry["research_tokens_unpriced"] = list(research_unpriced)
        telemetry["research_tokens_priced"] = int(
            len(research_tokens) - len(research_unpriced)
        )
        telemetry["configured_tokens_priced"] = int(
            len(configured_tokens)
            - sum(1 for token in configured_tokens if token.lower() in {item.lower() for item in unpriced})
        )
        return amounts, telemetry

    async def _scan_primary_opportunities(
        self,
        rpc: Any,
        *,
        current_block: int,
        amount_in: int,
        cache: PerBlockCache | None = None,
        discovery_context: Dict[str, Any] | None = None,
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
        provider_comparison_active = bool(getattr(self, "_rpc_provider_comparison", False))
        max_scan_edges = (
            self._provider_comparison_edge_cap()
            if provider_comparison_active
            else None
        )
        provider_scan_pool_event_cache = discovery_context.get(
            "_provider_scan_pool_event_cache"
        )
        scan_pool_event_cache = (
            provider_scan_pool_event_cache
            if provider_scan_pool_event_cache is not None
            else getattr(self, "_pool_event_cache", None)
        )
        extra_curve_pools = list(discovery_context.get("curve_pools") or [])
        extra_balancer_pools = list(discovery_context.get("balancer_pools") or [])
        extra_aerodrome_pools = list(discovery_context.get("aerodrome_pools") or [])
        extra_slipstream_pools = list(discovery_context.get("slipstream_pools") or [])
        extra_camelot_algebra_pools = list(discovery_context.get("camelot_algebra_pools") or [])
        extra_camelot_v2_pools = list(discovery_context.get("camelot_v2_pools") or [])
        extra_constant_product_pools = list(discovery_context.get("constant_product_pools") or [])

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
                "aerodrome_pools": len(extra_aerodrome_pools),
                "slipstream_pools": len(extra_slipstream_pools),
                "camelot_algebra_pools": len(extra_camelot_algebra_pools),
            "constant_product_pools": len(extra_constant_product_pools),
            },
            "candidate_token_discovery": candidate_token_telemetry,
        }
        two_leg_telemetry: Dict[str, Any] = {}
        three_leg_telemetry: Dict[str, Any] = {}
        opps2: List[Opportunity] = []
        opps3: List[Opportunity] = []
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
            shared_telemetry = dict(discovery_context.get("_shared_token_scan_telemetry") or {})
            token_scan_telemetry = {
                **shared_telemetry,
                "enabled": bool(token_scan_amounts),
                "source": "shared_provider_comparison",
                "reference_token": str(
                    shared_telemetry.get("reference_token")
                    or getattr(getattr(self.cfg, "chain", None), "weth", "")
                    or ""
                ),
                "base_amount_in": str(int(amount_in)),
                "amounts_by_token": {
                    token: str(raw) for token, raw in token_scan_amounts.items()
                },
                "unpriced_tokens": list(shared_telemetry.get("unpriced_tokens") or []),
                "research_tokens_unpriced": list(shared_telemetry.get("research_tokens_unpriced") or []),
            }
        telemetry["scan_sizing"] = dict(token_scan_telemetry)
        try:
            gas_price_consensus = await self.rpc_manager.gas_price_consensus()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            gas_price_consensus = {
                "gas_price_wei": None,
                "status": "insufficient_agreement",
                "observations": [],
                "anomalies": [],
            }
        observed_gas_price_wei = (
            int(gas_price_consensus.get("gas_price_wei"))
            if gas_price_consensus.get("gas_price_wei") not in (None, "")
            else None
        )
        telemetry["gas_price_integrity"] = dict(gas_price_consensus)
        try:
            size_amounts = [int(amount_in)]
            selected_full_graph_base_only = bool(
                discovery_context.get("_selected_provider_full_graph_base_only")
            )
            adaptive_amounts = (
                []
                if selected_full_graph_base_only
                else self._adaptive_scan_amounts(
                    int(amount_in),
                    force_adaptive_size_scan=bool(force_adaptive_size_scan),
                )
            )
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
                        pool_event_cache=scan_pool_event_cache,
                        max_scan_edges=max_scan_edges,
                        max_reverse_candidates=(
                            3 if selected_full_graph_base_only else None
                        ),
                        extra_v3_pairs=extra_v3_pairs,
                        extra_curve_pools=extra_curve_pools,
                        extra_balancer_pools=extra_balancer_pools,
                        extra_aerodrome_pools=extra_aerodrome_pools,
                        extra_slipstream_pools=extra_slipstream_pools,
                        extra_camelot_algebra_pools=extra_camelot_algebra_pools,
                        extra_camelot_v2_pools=extra_camelot_v2_pools,
                        extra_constant_product_pools=extra_constant_product_pools,
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
                        pool_event_cache=scan_pool_event_cache,
                        max_scan_edges=max_scan_edges,
                        max_reverse_candidates=(
                            3 if selected_full_graph_base_only else None
                        ),
                        extra_v3_pairs=extra_v3_pairs,
                        extra_curve_pools=extra_curve_pools,
                        extra_balancer_pools=extra_balancer_pools,
                        extra_aerodrome_pools=extra_aerodrome_pools,
                        extra_slipstream_pools=extra_slipstream_pools,
                        extra_camelot_algebra_pools=extra_camelot_algebra_pools,
                        extra_camelot_v2_pools=extra_camelot_v2_pools,
                        extra_constant_product_pools=extra_constant_product_pools,
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
                    observed_gas_price_wei=observed_gas_price_wei,
                    gas_price_integrity=gas_price_consensus,
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
                            "successful_quote_edge_count",
                            "successful_quote_pool_count",
                            "successful_quote_pair_count",
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
                return _candidate_economic_after_cost_for_sizing(candidate)

            # Revalidate every scanned candidate before route-size
            # deduplication. Otherwise the sizing selector cannot see the
            # authoritative after-cost economics it is supposed to optimize.
            await self._annotate_canonical_after_fee_usd(
                opps=[*opps2, *opps3],
                rpc=rpc,
                current_block=int(current_block),
                cache=scan_cache,
                observed_gas_price_wei=observed_gas_price_wei,
                gas_price_integrity=gas_price_consensus,
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
            _attach_quote_economic_size_curves([*opps2, *opps3], size_matrix)

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
            telemetry["reverse_leg_prefilter"] = dict(
                two_leg_telemetry.get("reverse_leg_prefilter") or {}
            )
            telemetry["pool_event_state"] = dict(
                two_leg_telemetry.get("pool_event_state")
                or three_leg_telemetry.get("pool_event_state")
                or {}
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

    def _selected_provider_frontier_seed_amounts(self, amount_in: int) -> List[int]:
        """Return a tiny alternate-notional frontier for size-emergent discovery.

        Provider comparison stays symmetric at the base notional. When that
        base scan has too few candidates, nearby sizes must still be allowed
        to introduce routes that do not exist at 1x. This helper derives its
        candidates from the existing cap-aware adaptive ladder and remains
        explicitly bounded.
        """
        base = max(1, int(amount_in))
        ladder = [
            int(value)
            for value in self._adaptive_scan_amounts(
                base,
                force_adaptive_size_scan=True,
            )
            if int(value) > 0 and int(value) != base
        ]
        if not ladder:
            return []

        try:
            max_probes = max(
                1,
                min(
                    3,
                    int(
                        os.environ.get(
                            "VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_MAX_PROBES",
                            "3",
                        )
                        or 3
                    ),
                ),
            )
        except (TypeError, ValueError):
            max_probes = 3

        preferred: List[int] = []
        # Sample a low, middle, and upper authorized notional. Larger sizes
        # matter disproportionately when fixed gas/flash-loan costs create a
        # break-even threshold; do not spend every frontier probe near 1x.
        raw = os.environ.get(
            "VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_MULTIPLIERS",
            "0.5,2.0,8.0",
        )
        ladder_set = set(ladder)
        for item in str(raw).split(","):
            try:
                multiplier = float(item.strip())
                if multiplier <= 0.0:
                    continue
                candidate = max(1, int(round(float(base) * multiplier)))
            except (TypeError, ValueError):
                continue
            if candidate in ladder_set and candidate not in preferred:
                preferred.append(candidate)
            if len(preferred) >= max_probes:
                break

        if len(preferred) < max_probes:
            for candidate in ladder:
                if candidate not in preferred:
                    preferred.append(candidate)
                if len(preferred) >= max_probes:
                    break
        return preferred[:max_probes]

    async def _run_bounded_selected_provider_size_probe(
        self,
        rpc: Any,
        *,
        current_block: int,
        base_amount_in: int,
        base_opps: List[Opportunity],
        cache: PerBlockCache,
    ) -> tuple[List[Opportunity], Dict[str, Any]]:
        """Probe promising base routes at alternate notionals without rescanning the graph."""
        telemetry: Dict[str, Any] = {}
        adaptive_amounts = self._adaptive_scan_amounts(
            int(base_amount_in),
            force_adaptive_size_scan=True,
        )
        try:
            min_opportunities = max(
                1,
                int(os.environ.get("VICTOR_ADAPTIVE_SIZE_MIN_OPPORTUNITIES", "2") or 2),
            )
        except (TypeError, ValueError):
            min_opportunities = 2

        def _authoritative_positive(candidate: Any) -> bool:
            meta = getattr(candidate, "meta", {}) or {}
            state = meta.get("profitability") if isinstance(meta, dict) else {}
            if not isinstance(state, dict):
                return False
            try:
                return bool(
                    state.get("revalidated")
                    and state.get("authoritative")
                    and state.get("valid")
                    and int(state.get("profit_after_costs_wei") or 0) > 0
                )
            except (TypeError, ValueError, OverflowError):
                return False

        def _route_key(candidate: Any) -> str:
            return str(
                getattr(candidate, "route_id", "")
                or getattr(candidate, "id", "")
                or ""
            )

        direct = [
            candidate
            for candidate in list(base_opps or [])
            if str(getattr(candidate, "strategy", "") or "").startswith("two-leg:")
        ]
        triangles = [
            candidate
            for candidate in list(base_opps or [])
            if str(getattr(candidate, "strategy", "") or "").startswith("tri:")
        ]
        direct.sort(key=_candidate_sizing_sort_key, reverse=True)
        triangles.sort(key=_candidate_sizing_sort_key, reverse=True)

        try:
            route_cap = max(
                4,
                min(24, int(os.environ.get("VICTOR_ADAPTIVE_SIZE_ROUTE_CAP", "12") or 12)),
            )
        except (TypeError, ValueError):
            route_cap = 12
        try:
            triangle_cap = max(
                0,
                min(route_cap, int(os.environ.get("VICTOR_ADAPTIVE_SIZE_TRIANGLE_CAP", "4") or 4)),
            )
        except (TypeError, ValueError):
            triangle_cap = 4

        selected: List[Opportunity] = []
        seen_routes: set[str] = set()
        for candidate in [*direct[:route_cap], *triangles[:triangle_cap]]:
            key = _route_key(candidate)
            if key and key in seen_routes:
                continue
            if key:
                seen_routes.add(key)
            selected.append(candidate)
            if len(selected) >= route_cap:
                break

        # Profitability at the current notional does not prove that the notional
        # is optimal. Whenever routes are available and the authorized ladder has
        # alternatives, evaluate their size curve before handing candidates on.
        # The canonical-positive count remains diagnostic and never grants
        # execution authority; when no routes exist, graph-frontier discovery is
        # responsible for introducing size-emergent routes.
        positive_base = sum(
            1 for candidate in base_opps if _authoritative_positive(candidate)
        )
        should_probe = bool(len(adaptive_amounts) > 1 and selected)
        telemetry["adaptive_size_discovery"] = {
            "enabled": bool(len(adaptive_amounts) > 1),
            "base_amount_in": str(int(base_amount_in)),
            "amounts_scanned": [str(int(base_amount_in))],
            "probe_triggered": False,
            "minimum_opportunities": int(min_opportunities),
            "candidates_before_probe": int(len(base_opps)),
            "authoritative_positive_candidates_before_probe": int(positive_base),
            "probe_basis": "bounded_selected_route_requote",
            "selected_route_count": int(len(selected)),
            "route_cap": int(route_cap),
            "triangle_cap": int(triangle_cap),
            "probe_candidate_delta": 0,
            "probe_quote_failures": 0,
        }
        if not should_probe:
            return list(base_opps), telemetry

        probe_amounts: List[int] = []
        for amount in list(adaptive_amounts[1:5]):
            if int(amount) not in probe_amounts:
                probe_amounts.append(int(amount))
        if len(adaptive_amounts) > 1:
            terminal = int(adaptive_amounts[-1])
            if terminal not in probe_amounts:
                probe_amounts.append(terminal)

        # Frontier-discovered candidates can originate at an alternate size.
        # Keep the economic row aligned to the notional actually quoted rather
        # than relabeling every seed route as the base-size result.
        candidates_by_source_size: Dict[int, Dict[str, List[Opportunity]]] = {}
        for candidate in [*direct, *triangles]:
            meta = getattr(candidate, "meta", {}) or {}
            try:
                source_amount = max(
                    1, int(meta.get("adaptive_seed_amount_in") or base_amount_in)
                )
            except (TypeError, ValueError):
                source_amount = int(base_amount_in)
            group = candidates_by_source_size.setdefault(
                source_amount, {"two": [], "three": []}
            )
            strategy = str(getattr(candidate, "strategy", "") or "")
            group["two" if strategy.startswith("two-leg:") else "three"].append(candidate)

        size_scan_records: List[Dict[str, Any]] = [
            {
                "amount_in": int(source_amount),
                "two": list(group["two"]),
                "three": list(group["three"]),
                "two_metrics": {},
                "three_metrics": {},
            }
            for source_amount, group in sorted(candidates_by_source_size.items())
        ]
        if not size_scan_records:
            size_scan_records.append({
                "amount_in": int(base_amount_in),
                "two": [],
                "three": [],
                "two_metrics": {},
                "three_metrics": {},
            })
        sized: List[Opportunity] = []

        for probe_amount in probe_amounts:
            tasks = []
            for candidate in selected:
                try:
                    base_raw = int(
                        getattr(getattr(candidate, "route", None).legs[0], "amount_in", 0)
                    )
                except (AttributeError, IndexError, TypeError, ValueError):
                    base_raw = 0
                if base_raw <= 0 or int(base_amount_in) <= 0:
                    continue
                meta = getattr(candidate, "meta", {}) or {}
                try:
                    reference_amount_in = int(
                        meta.get("adaptive_seed_amount_in") or base_amount_in
                    )
                except (TypeError, ValueError):
                    reference_amount_in = int(base_amount_in)
                if reference_amount_in <= 0:
                    reference_amount_in = int(base_amount_in)
                # Do not spend quote budget requoting a frontier candidate at the
                # exact notional where it was already discovered.
                if int(probe_amount) == int(reference_amount_in):
                    continue
                raw_probe = max(
                    1,
                    int(
                        round(
                            float(base_raw)
                            * float(probe_amount)
                            / float(max(1, reference_amount_in))
                        )
                    ),
                )
                try:
                    clone = candidate.model_copy(deep=True)
                except AttributeError:
                    continue
                tasks.append(
                    requote_opportunity(
                        rpc,
                        self.cfg,
                        cache,
                        clone,
                        new_amount_in=raw_probe,
                        slippage_bps=int(self.cfg.safety.slippage_bps),
                    )
                )
            if not tasks:
                continue
            results = await asyncio.gather(*tasks, return_exceptions=True)
            probe_rows: List[Opportunity] = []
            for result in results:
                if isinstance(result, Exception) or result is None:
                    telemetry["adaptive_size_discovery"]["probe_quote_failures"] = int(
                        telemetry["adaptive_size_discovery"].get("probe_quote_failures", 0)
                    ) + 1
                    continue
                probe_rows.append(result)
                sized.append(result)
            size_scan_records.append({
                "amount_in": int(probe_amount),
                "two": [
                    row for row in probe_rows
                    if str(getattr(row, "strategy", "") or "").startswith("two-leg:")
                ],
                "three": [
                    row for row in probe_rows
                    if str(getattr(row, "strategy", "") or "").startswith("tri:")
                ],
                "two_metrics": {},
                "three_metrics": {},
            })

        try:
            gas_price_consensus = await self.rpc_manager.gas_price_consensus()
        except (AttributeError, RuntimeError, TypeError, ValueError):
            gas_price_consensus = {
                "gas_price_wei": None,
                "status": "insufficient_agreement",
                "observations": [],
                "anomalies": [],
            }
        observed_gas_price_wei = (
            int(gas_price_consensus.get("gas_price_wei"))
            if gas_price_consensus.get("gas_price_wei") not in (None, "")
            else None
        )
        if sized:
            await self._annotate_canonical_after_fee_usd(
                opps=list(sized),
                rpc=rpc,
                current_block=int(current_block),
                cache=cache,
                observed_gas_price_wei=observed_gas_price_wei,
                gas_price_integrity=gas_price_consensus,
            )

        matrix = _build_size_economic_matrix(size_scan_records)
        _attach_quote_economic_size_curves([*selected, *sized], matrix)
        telemetry["size_economic_matrix"] = matrix
        telemetry["size_economic_evidence"] = [
            _size_economic_candidate_row(candidate)
            for candidate in sized
        ]
        telemetry["adaptive_size_discovery"].update({
            "amounts_scanned": [
                str(int(amount))
                for amount in sorted({
                    int(record.get("amount_in") or 0)
                    for record in size_scan_records
                    if int(record.get("amount_in") or 0) > 0
                } | {int(amount) for amount in probe_amounts if int(amount) > 0})
            ],
            "probe_triggered": bool(sized),
            "probe_candidate_delta": int(len(sized)),
            "economic_matrix_complete": bool(
                {str(row.get("amount_in")) for row in matrix}.issuperset(
                    {
                        str(int(amount))
                        for amount in sorted({
                            int(record.get("amount_in") or 0)
                            for record in size_scan_records
                            if int(record.get("amount_in") or 0) > 0
                        } | {int(amount) for amount in probe_amounts if int(amount) > 0})
                    }
                )
            ),
            "best_sizing_variants": [
                {
                    "route_id": _route_key(candidate),
                    "amount_in": str(getattr(getattr(candidate.route, "legs", [])[0], "amount_in", "")),
                    "expected_profit_raw": str(getattr(candidate, "expected_profit_raw", "0") or "0"),
                    "after_cost_profit_wei": str(
                        (
                            (getattr(candidate, "meta", {}) or {}).get("profitability")
                            or {}
                        ).get("profit_after_costs_wei", "")
                    ),
                    "economic_after_cost_profit_wei": (
                        str(_candidate_economic_after_cost_for_sizing(candidate))
                        if _candidate_economic_after_cost_for_sizing(candidate) is not None
                        else ""
                    ),
                    "sizing_selection_basis": (
                        "signed_economic_after_cost"
                        if _candidate_economic_after_cost_for_sizing(candidate) is not None
                        else "gross_diagnostic_fallback"
                    ),
                    "revalidated": bool(
                        (
                            (getattr(candidate, "meta", {}) or {}).get("profitability")
                            or {}
                        ).get("revalidated")
                    ),
                }
                for candidate in sorted(
                    sized,
                    key=_candidate_sizing_sort_key,
                    reverse=True,
                )[:32]
            ],
        })
        return [*base_opps, *sized], telemetry

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
            snapshot_fn = getattr(manager, "snapshot", None)
            snapshot = snapshot_fn() if callable(snapshot_fn) else {}
            bootstrap_quarantined = False
            if isinstance(snapshot, dict):
                for row in list(snapshot.get("read") or []):
                    if not isinstance(row, dict) or str(row.get("url") or "") != bootstrap_url:
                        continue
                    bootstrap_quarantined = float(row.get("quote_unhealthy_until") or 0.0) > time.time()
                    break
            if not bootstrap_quarantined:
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

        selection_started_ms = int(time.time() * 1000)
        selection_timeout_s = self._provider_scan_timeout_s()
        provider_progress_by_url: Dict[str, Dict[str, Any]] = {}
        for url in candidates:
            try:
                provider_name = str(urlsplit(url).hostname or "unknown")
            except ValueError:
                provider_name = "unknown"
            provider_progress_by_url[url] = {
                "provider": provider_name[:128],
                "status": "pending",
                "quote_requests": 0,
                "quote_successes": 0,
                "candidate_count": 0,
            }

        def publish_rpc_selection_progress(
            phase: str,
            *,
            provider_url: str | None = None,
            status: str | None = None,
            candidate_count: int | None = None,
            provider_telemetry: Dict[str, Any] | None = None,
            details: Dict[str, Any] | None = None,
        ) -> None:
            """Publish bounded, credential-free live progress for the read-only scan."""
            now_ms = int(time.time() * 1000)
            provider_row = provider_progress_by_url.get(provider_url or "")
            if provider_row is not None:
                if status:
                    provider_row["status"] = str(status)
                    if status == "running":
                        provider_row["started_ms"] = now_ms
                        provider_row.pop("completed_ms", None)
                        provider_row.pop("elapsed_ms", None)
                    elif status in {"completed", "failed", "timed_out"}:
                        provider_row["completed_ms"] = now_ms
                        provider_row["elapsed_ms"] = max(
                            0, now_ms - int(provider_row.get("started_ms") or now_ms)
                        )
                if candidate_count is not None:
                    provider_row["candidate_count"] = max(0, int(candidate_count))
                if isinstance(provider_telemetry, dict):
                    quotes = dict(provider_telemetry.get("quotes") or {})
                    provider_row["quote_requests"] = max(
                        0, int(quotes.get("requests") or 0)
                    )
                    provider_row["quote_successes"] = max(
                        0, int(quotes.get("successes") or 0)
                    )
                    try:
                        provider_row["scan_latency_ms"] = round(
                            float(provider_telemetry.get("scan_latency_ms") or 0.0), 1
                        )
                    except (TypeError, ValueError, OverflowError):
                        provider_row["scan_latency_ms"] = 0.0
                    error = str(provider_telemetry.get("scan_error") or "").lower()
                    if error:
                        provider_row["error_kind"] = (
                            "provider_scan_timeout"
                            if "timeout" in error or "timed out" in error
                            else "provider_scan_failed"
                        )
                    else:
                        provider_row.pop("error_kind", None)

            providers = [dict(row) for row in provider_progress_by_url.values()]
            terminal = {"completed", "failed", "timed_out"}
            prior = dict(getattr(self, "_market_pipeline_telemetry", {}) or {})
            previous_progress = dict(prior.get("rpc_selection_progress") or {})
            same_selection = (
                int(previous_progress.get("started_ms") or 0) == selection_started_ms
            )
            phase_started_ms = (
                now_ms
                if (
                    not same_selection
                    or str(previous_progress.get("phase") or "") != str(phase)
                )
                else int(previous_progress.get("phase_started_ms") or now_ms)
            )
            previous_details = (
                dict(previous_progress.get("details") or {})
                if same_selection
                else {}
            )
            progress = {
                "phase": str(phase),
                "started_ms": selection_started_ms,
                "phase_started_ms": phase_started_ms,
                "phase_elapsed_ms": max(0, now_ms - phase_started_ms),
                "updated_ms": now_ms,
                "elapsed_ms": max(0, now_ms - selection_started_ms),
                "provider_count": len(providers),
                "providers_started": sum(row.get("status") != "pending" for row in providers),
                "providers_running": sum(row.get("status") == "running" for row in providers),
                "providers_completed": sum(row.get("status") in terminal for row in providers),
                "providers_failed": sum(row.get("status") in {"failed", "timed_out"} for row in providers),
                "providers": providers,
            }
            if details:
                previous_details.update(dict(details))
            if previous_details:
                progress["details"] = previous_details
            prior.update({
                "rpc_selection_phase": str(phase),
                "rpc_selection_started_ms": selection_started_ms,
                "rpc_provider_scan_timeout_s": float(selection_timeout_s),
                "rpc_selection_progress": progress,
            })
            self._market_pipeline_telemetry = prior

            loop_telemetry = dict(getattr(self, "_runtime_loop_telemetry", {}) or {})
            if str(loop_telemetry.get("phase") or "") != str(phase):
                loop_telemetry["phase_started_ms"] = now_ms
            loop_telemetry["phase"] = str(phase)
            self._runtime_loop_telemetry = loop_telemetry

        publish_rpc_selection_progress("discovery_preparation")

        discovery_context = await self._build_discovery_context(
            bootstrap_rpc,
            current_block=int(current_block),
        )
        provider_scan_pool_event_cache = self._build_provider_comparison_pool_event_cache(
            discovery_context,
            current_block=int(current_block),
        )
        discovery_context = dict(discovery_context)
        discovery_context["_provider_scan_pool_event_cache"] = provider_scan_pool_event_cache
        shared_token_scan_amounts, shared_token_scan_telemetry = await self._build_token_scan_amounts(
            bootstrap_rpc,
            current_block=int(current_block),
            base_amount_in=int(amount_in),
            cache=PerBlockCache(),
        )
        discovery_context["_shared_token_scan_telemetry"] = dict(shared_token_scan_telemetry)

        async def scan_one(url: str) -> tuple[str, List[Opportunity], PerBlockCache, Dict[str, Any], RpcEconomicEvidence]:
            scan_cache = PerBlockCache()
            telemetry: Dict[str, Any] = {}
            telemetry["provider_comparison_edge_cap"] = self._provider_comparison_edge_cap()
            publish_rpc_selection_progress(
                "provider_comparison",
                provider_url=url,
                status="running",
            )
            started = time.perf_counter()
            try:
                if url == bootstrap_url:
                    opps = await asyncio.wait_for(
                        self._scan_primary_opportunities(
                            bootstrap_rpc,
                            current_block=int(current_block),
                            amount_in=int(amount_in),
                            cache=scan_cache,
                            discovery_context=discovery_context,
                            telemetry_sink=telemetry,
                            shared_token_scan_amounts=shared_token_scan_amounts,
                            force_adaptive_size_scan=False,
                        ),
                        timeout=self._provider_scan_timeout_s(),
                    )
                else:
                    async with JsonRpcClient(
                        url, timeout_s=10.0, max_concurrency=30, max_batch=80
                    ) as provider_rpc:
                        opps = await asyncio.wait_for(
                            self._scan_primary_opportunities(
                                provider_rpc,
                                current_block=int(current_block),
                                amount_in=int(amount_in),
                                cache=scan_cache,
                                discovery_context=discovery_context,
                                telemetry_sink=telemetry,
                                shared_token_scan_amounts=shared_token_scan_amounts,
                                force_adaptive_size_scan=False,
                            ),
                            timeout=self._provider_scan_timeout_s(),
                        )
            except asyncio.TimeoutError:
                telemetry.setdefault("scan_error", "provider_scan_timeout")
                telemetry["provider_scan_timeout_s"] = self._provider_scan_timeout_s()
                telemetry["scan_latency_ms"] = float((time.perf_counter() - started) * 1000.0)
                opps = []
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
            economic_rows = [
                item
                for item in list(telemetry.get("size_economic_evidence") or [])
                if isinstance(item, dict) and bool(item.get("revalidated"))
            ]
            best_return_bps = -1e18
            for item in economic_rows:
                try:
                    amount = int(item.get("amount_in") or 0)
                    economic = int(item.get("economic_after_cost_profit_wei") or 0)
                    if amount > 0:
                        best_return_bps = max(best_return_bps, (float(economic) / float(amount)) * 10_000.0)
                except (TypeError, ValueError, OverflowError):
                    continue
            best_return_bps = float(best_return_bps)
            evidence = RpcEconomicEvidence(
                endpoint=url,
                provider=str(urlsplit(url).hostname or ""),
                profit_after_costs_usd_micro=int(profit_micro),
                profitable_opportunity_count=int(profitable_count),
                quote_requests=quote_requests,
                quote_successes=quote_successes,
                observed_after_cost_return_bps=best_return_bps,
                successful_quote_edge_count=int(
                    telemetry.get("successful_quote_edge_count", 0) or 0
                ),
                successful_quote_pool_count=int(
                    telemetry.get("successful_quote_pool_count", 0) or 0
                ),
                successful_quote_pair_count=int(
                    telemetry.get("successful_quote_pair_count", 0) or 0
                ),
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
                    "observed_after_cost_return_bps": best_return_bps,
                    "provider": str(urlsplit(url).hostname or ""),
                    "score": row.get("score"),
                    "ok": row.get("ok"),
                    "quote_failures": row.get("quote_failures", 0),
                    "quote_successes": row.get("quote_successes", 0),
                    "quote_last_error": row.get("quote_last_error"),
                    "quote_unhealthy_until": row.get("quote_unhealthy_until", 0.0),
                }
            )
            scan_error = str(telemetry.get("scan_error") or "").lower()
            scan_status = (
                "timed_out"
                if "timeout" in scan_error or "timed out" in scan_error
                else "failed" if scan_error else "completed"
            )
            publish_rpc_selection_progress(
                "provider_comparison",
                provider_url=url,
                status=scan_status,
                candidate_count=len(opps or []),
                provider_telemetry=telemetry,
            )
            return url, list(opps or []), scan_cache, telemetry, evidence

        publish_rpc_selection_progress("provider_comparison")
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

        # Provider comparison is intentionally symmetric at the base notional.
        # If the selected provider has too few base candidates, rescue only a
        # tiny nearby size frontier on that provider before route-only requotes.
        # This closes the "profitable only at another size" discovery hole
        # without replaying the institutional ladder across every provider.
        adaptive_telemetry: Dict[str, Any] = {}
        frontier_seed_telemetry: Dict[str, Any] = {}
        publish_rpc_selection_progress("selected_provider_adaptive")
        adaptive_opps: List[Opportunity] = []
        selected_provider_url = str(selected_url)
        adaptive_cache = PerBlockCache()

        try:
            min_opportunities = max(
                1,
                int(
                    os.environ.get(
                        "VICTOR_ADAPTIVE_SIZE_MIN_OPPORTUNITIES",
                        "2",
                    )
                    or 2
                ),
            )
        except (TypeError, ValueError):
            min_opportunities = 2

        authoritative_positive_selected = 0
        for candidate in list(selected_opps or []):
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
                    authoritative_positive_selected += 1
            except (TypeError, ValueError):
                continue

        full_graph_rescue_required = bool(
            len(selected_opps or []) < min_opportunities
            or authoritative_positive_selected < min_opportunities
        )
        if full_graph_rescue_required:
            publish_rpc_selection_progress("selected_provider_full_scan")
            # Provider comparison is intentionally capped. The selected provider
            # now receives the same immutable graph, but in bounded chunks so the
            # full graph is covered without one monolithic wall-clock timeout.
            full_scan_telemetry: Dict[str, Any] = {
                "attempted": True,
                "rescue_reason": (
                    "insufficient_base_candidates"
                    if len(selected_opps or []) < min_opportunities
                    else "insufficient_authoritative_after_cost_positive_candidates"
                ),
                "base_candidate_count": int(len(selected_opps or [])),
                "authoritative_positive_candidate_count": int(
                    authoritative_positive_selected
                ),
                "chunk_size": int(self._selected_provider_full_scan_chunk_size()),
                "chunk_timeout_s": float(self._selected_provider_full_scan_chunk_timeout_s()),
                "budget_s": float(self._selected_provider_full_scan_budget_s()),
                "frontier_reserved_budget_s": float(self._selected_provider_frontier_seed_budget_s()),
                "parallelism": int(self._selected_provider_full_scan_parallelism()),
                "chunks_total": 0,
                "chunks_completed": 0,
                "edges_total": 0,
                "edges_covered": 0,
                "returned": 0,
                "scan_errors": [],
                "chunks": [],
            }
            full_scan_started = time.perf_counter()
            full_scan_opps: List[Opportunity] = []
            full_scan_records: List[Dict[str, Any]] = []
            provider_graph = discovery_context.get("_provider_scan_pool_event_cache")

            edge_count_fn = getattr(provider_graph, "edge_count", None)
            slice_fn = getattr(provider_graph, "slice", None)
            graph_edge_count = (
                int(edge_count_fn())
                if callable(edge_count_fn)
                else 0
            )
            if graph_edge_count <= 0:
                graph_edge_count = 1
            chunk_size = int(full_scan_telemetry["chunk_size"])
            chunk_total = max(1, (graph_edge_count + chunk_size - 1) // chunk_size)
            full_scan_telemetry["chunks_total"] = int(chunk_total)
            full_scan_telemetry["edges_total"] = int(graph_edge_count)
            total_budget_s = float(self._selected_provider_full_scan_budget_s(graph_edge_count))
            full_scan_telemetry["budget_s"] = total_budget_s
            chunk_order = _selected_provider_full_scan_chunk_order(
                graph_edge_count=graph_edge_count,
                chunk_size=chunk_size,
                rotation_index=int(current_block),
            )
            full_scan_telemetry["rotation_start_chunk"] = int(chunk_order[0])
            full_scan_telemetry["chunk_order_preview"] = [
                int(index) for index in chunk_order[: min(12, len(chunk_order))]
            ]
            full_scan_telemetry["budget_basis"] = {
                "graph_edge_count": int(graph_edge_count),
                "chunks_required": int(chunk_total),
                "parallel_waves_required": int(
                    (chunk_total + int(full_scan_telemetry["parallelism"]) - 1)
                    // int(full_scan_telemetry["parallelism"])
                ),
                "adaptive": bool(total_budget_s > 8.0),
                "per_tick_hard_cap_s": 12.0,
                "rotation_start_chunk": int(chunk_order[0]),
                "frontier_reserved_budget_s": float(
                    full_scan_telemetry["frontier_reserved_budget_s"]
                ),
            }
            publish_rpc_selection_progress(
                "selected_provider_full_scan",
                details={
                    "scan_kind": "rotating_full_graph_slice",
                    "chunks_total": int(chunk_total),
                    "chunks_completed": 0,
                    "chunks_started": 0,
                    "edges_total": int(graph_edge_count),
                    "edges_covered": 0,
                    "budget_s": float(total_budget_s),
                    "rotation_start_chunk": int(chunk_order[0]),
                    "chunk_order_preview": [
                        int(index) for index in chunk_order[: min(12, len(chunk_order))]
                    ],
                },
            )
            chunk_statuses: Dict[int, str] = {
                index: "pending" for index in range(chunk_total)
            }
            chunk_status_reasons: Dict[int, str] = {}

            async def _run_selected_full_scan_chunk(
                scan_rpc: Any,
                *,
                chunk_index: int,
                chunk_cache: Any,
                timeout_s: float,
            ) -> None:
                context = dict(discovery_context)
                context["_provider_scan_pool_event_cache"] = chunk_cache
                context["_selected_provider_full_graph_base_only"] = True
                sink: Dict[str, Any] = {}
                started = time.perf_counter()
                try:
                    chunk_opps = await asyncio.wait_for(
                        self._scan_primary_opportunities(
                            scan_rpc,
                            current_block=int(current_block),
                            amount_in=int(amount_in),
                            cache=selected_cache,
                            discovery_context=context,
                            telemetry_sink=sink,
                            shared_token_scan_amounts=shared_token_scan_amounts,
                            force_adaptive_size_scan=False,
                        ),
                        timeout=float(timeout_s),
                    )
                    chunk_opps = list(chunk_opps or [])
                    full_scan_opps.extend(chunk_opps)
                    full_scan_records.append({
                        "amount_in": int(amount_in),
                        "two": [
                            item for item in chunk_opps
                            if str(getattr(item, "strategy", "") or "").startswith("two-leg:")
                        ],
                        "three": [
                            item for item in chunk_opps
                            if str(getattr(item, "strategy", "") or "").startswith("tri:")
                        ],
                        "two_metrics": {
                            "size_economic_diagnostics": list(
                                sink.get("size_economic_diagnostics") or []
                            ),
                        },
                        "three_metrics": {},
                    })
                    selected_edges = int(
                        (sink.get("scan_edges_selected") or 0)
                        or min(chunk_size, max(0, graph_edge_count - chunk_index * chunk_size))
                    )
                    full_scan_telemetry["edges_covered"] = int(
                        full_scan_telemetry["edges_covered"] + selected_edges
                    )
                    full_scan_telemetry["chunks_completed"] = int(
                        full_scan_telemetry["chunks_completed"] + 1
                    )
                    chunk_statuses[int(chunk_index)] = "completed"
                    full_scan_telemetry["chunks"].append({
                        "index": int(chunk_index),
                        "offset": int(chunk_index * chunk_size),
                        "edges_selected": int(selected_edges),
                        "returned": int(len(chunk_opps)),
                        "latency_ms": float(
                            sink.get("scan_latency_ms")
                            or (time.perf_counter() - started) * 1000.0
                        ),
                    })
                    publish_rpc_selection_progress(
                        "selected_provider_full_scan",
                        details={
                            "chunks_completed": int(full_scan_telemetry["chunks_completed"]),
                            "edges_covered": int(full_scan_telemetry["edges_covered"]),
                        },
                    )
                except asyncio.TimeoutError:
                    chunk_statuses[int(chunk_index)] = "timed_out"
                    chunk_status_reasons[int(chunk_index)] = "chunk_timeout"
                    full_scan_telemetry["scan_errors"].append({
                        "chunk": int(chunk_index),
                        "offset": int(chunk_index * chunk_size),
                        "reason": "selected_provider_full_scan_chunk_timeout",
                        "timeout_s": float(timeout_s),
                    })
                    publish_rpc_selection_progress(
                        "selected_provider_full_scan",
                        details={
                            "chunks_timed_out": sum(
                                value == "timed_out" for value in chunk_statuses.values()
                            ),
                        },
                    )
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                    chunk_statuses[int(chunk_index)] = "failed"
                    chunk_status_reasons[int(chunk_index)] = f"{type(exc).__name__}: {exc}"
                    full_scan_telemetry["scan_errors"].append({
                        "chunk": int(chunk_index),
                        "offset": int(chunk_index * chunk_size),
                        "reason": f"{type(exc).__name__}: {exc}",
                    })
                    publish_rpc_selection_progress(
                        "selected_provider_full_scan",
                        details={
                            "chunks_failed": sum(
                                value == "failed" for value in chunk_statuses.values()
                            ),
                        },
                    )

            chunk_timeout_s = float(full_scan_telemetry["chunk_timeout_s"])
            chunk_parallelism = int(full_scan_telemetry["parallelism"])

            async def _run_selected_full_scan_chunks(scan_rpc: Any) -> None:
                for batch_start in range(0, chunk_total, chunk_parallelism):
                    tasks = []
                    task_chunk_indices: List[int] = []
                    batch_chunk_indices = chunk_order[
                        batch_start : min(chunk_total, batch_start + chunk_parallelism)
                    ]
                    for chunk_index in batch_chunk_indices:
                        remaining = total_budget_s - (
                            time.perf_counter() - full_scan_started
                        )
                        # Observed rescue chunks take several seconds. Avoid launching
                        # a slice with too little time to finish: wait_for cancellation
                        # cleanup can otherwise consume the frontier's separate budget.
                        if remaining < min(4.0, chunk_timeout_s):
                            break
                        timeout_s = min(chunk_timeout_s, remaining)
                        chunk_statuses[int(chunk_index)] = "running"
                        chunk_cache = slice_fn(
                            int(chunk_index * chunk_size),
                            int(chunk_size),
                        )
                        tasks.append(
                            asyncio.create_task(
                                _run_selected_full_scan_chunk(
                                    scan_rpc,
                                    chunk_index=int(chunk_index),
                                    chunk_cache=chunk_cache,
                                    timeout_s=float(timeout_s),
                                )
                            )
                        )
                        task_chunk_indices.append(int(chunk_index))
                    if not tasks:
                        break
                    publish_rpc_selection_progress(
                        "selected_provider_full_scan",
                        details={
                            "chunks_started": sum(
                                value == "running" for value in chunk_statuses.values()
                            ),
                            "chunks_completed": sum(
                                value == "completed" for value in chunk_statuses.values()
                            ),
                            "chunks_timed_out": sum(
                                value == "timed_out" for value in chunk_statuses.values()
                            ),
                            "chunks_failed": sum(
                                value == "failed" for value in chunk_statuses.values()
                            ),
                            "active_chunks": list(task_chunk_indices),
                            "rotation_start_chunk": int(chunk_order[0]),
                        },
                    )
                    await _gather_selected_provider_scan_batch(
                        tasks,
                        task_chunk_indices,
                        full_scan_telemetry["scan_errors"],
                    )

            if callable(slice_fn):
                if selected_provider_url == bootstrap_url:
                    await _run_selected_full_scan_chunks(bootstrap_rpc)
                else:
                    async with JsonRpcClient(
                        selected_provider_url,
                        timeout_s=10.0,
                        max_concurrency=30,
                        max_batch=80,
                    ) as selected_provider_rpc:
                        await _run_selected_full_scan_chunks(selected_provider_rpc)
            else:
                # Test/legacy fallback: preserve the previous single-pass behavior
                # when an injected cache does not expose the frozen-graph slicing API.
                context = dict(discovery_context)
                context["_selected_provider_full_graph_base_only"] = True
                sink: Dict[str, Any] = {}
                try:
                    if selected_provider_url == bootstrap_url:
                        chunk_opps = await asyncio.wait_for(
                            self._scan_primary_opportunities(
                                bootstrap_rpc,
                                current_block=int(current_block),
                                amount_in=int(amount_in),
                                cache=selected_cache,
                                discovery_context=context,
                                telemetry_sink=sink,
                                shared_token_scan_amounts=shared_token_scan_amounts,
                                force_adaptive_size_scan=False,
                            ),
                            timeout=selection_timeout_s,
                        )
                    else:
                        async with JsonRpcClient(
                            selected_provider_url,
                            timeout_s=10.0,
                            max_concurrency=30,
                            max_batch=80,
                        ) as selected_provider_rpc:
                            chunk_opps = await asyncio.wait_for(
                                self._scan_primary_opportunities(
                                    selected_provider_rpc,
                                    current_block=int(current_block),
                                    amount_in=int(amount_in),
                                    cache=selected_cache,
                                    discovery_context=context,
                                    telemetry_sink=sink,
                                    shared_token_scan_amounts=shared_token_scan_amounts,
                                    force_adaptive_size_scan=False,
                                ),
                                timeout=selection_timeout_s,
                            )
                    chunk_opps = list(chunk_opps or [])
                    full_scan_opps.extend(chunk_opps)
                    full_scan_records.append({
                        "amount_in": int(amount_in),
                        "two": [
                            item for item in chunk_opps
                            if str(getattr(item, "strategy", "") or "").startswith("two-leg:")
                        ],
                        "three": [
                            item for item in chunk_opps
                            if str(getattr(item, "strategy", "") or "").startswith("tri:")
                        ],
                        "two_metrics": {
                            "size_economic_diagnostics": list(
                                sink.get("size_economic_diagnostics") or []
                            ),
                        },
                        "three_metrics": {},
                    })
                    full_scan_telemetry["chunks_completed"] = 1
                    full_scan_telemetry["edges_covered"] = int(
                        sink.get("scan_edges_selected") or graph_edge_count
                    )
                    chunk_statuses[0] = "completed"
                except asyncio.TimeoutError:
                    chunk_statuses[0] = "timed_out"
                    chunk_status_reasons[0] = "fallback_scan_timeout"
                    full_scan_telemetry["scan_errors"].append({
                        "reason": "selected_provider_full_scan_timeout",
                        "timeout_s": float(selection_timeout_s),
                    })
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                    chunk_statuses[0] = "failed"
                    chunk_status_reasons[0] = f"{type(exc).__name__}: {exc}"
                    full_scan_telemetry["scan_errors"].append({
                        "reason": f"{type(exc).__name__}: {exc}",
                    })

            if full_scan_opps:
                selected_opps = [*list(selected_result[1] or []), *full_scan_opps]

            full_scan_telemetry.update(
                _selected_provider_chunk_accounting(
                    graph_edge_count=graph_edge_count,
                    chunk_size=chunk_size,
                    chunk_statuses=chunk_statuses,
                    chunk_status_reasons=chunk_status_reasons,
                )
            )
            full_scan_telemetry["returned"] = int(len(full_scan_opps))
            full_scan_telemetry["elapsed_ms"] = float(
                (time.perf_counter() - full_scan_started) * 1000.0
            )
            if full_scan_records:
                combined_record = {
                    "amount_in": int(amount_in),
                    "two": [
                        item
                        for record in full_scan_records
                        for item in list(record.get("two") or [])
                    ],
                    "three": [
                        item
                        for record in full_scan_records
                        for item in list(record.get("three") or [])
                    ],
                    "two_metrics": {
                        "size_economic_diagnostics": [
                            diagnostic
                            for record in full_scan_records
                            for diagnostic in list(
                                (record.get("two_metrics") or {}).get(
                                    "size_economic_diagnostics"
                                )
                                or []
                            )
                        ]
                    },
                    "three_metrics": {
                        "size_economic_diagnostics": [
                            diagnostic
                            for record in full_scan_records
                            for diagnostic in list(
                                (record.get("three_metrics") or {}).get(
                                    "size_economic_diagnostics"
                                )
                                or []
                            )
                        ]
                    },
                }
                full_scan_telemetry["size_economic_matrix"] = _build_size_economic_matrix(
                    [combined_record]
                )
                full_scan_telemetry["size_economic_evidence"] = _size_route_rows(
                    combined_record
                )[0]
            selected_telemetry["selected_provider_full_scan"] = dict(full_scan_telemetry)

            adaptive_cache = selected_cache
            seed_amounts = self._selected_provider_frontier_seed_amounts(int(amount_in))
            try:
                seed_timeout_s = max(
                    1.0,
                    min(
                        selection_timeout_s,
                        float(
                            os.environ.get(
                                "VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_TIMEOUT_S",
                                "3.0",
                            )
                            or 3.0
                        ),
                    ),
                )
            except (TypeError, ValueError):
                seed_timeout_s = min(selection_timeout_s, 3.0)
            seed_budget_s = min(
                selection_timeout_s,
                float(self._selected_provider_frontier_seed_budget_s()),
            )

            frontier_edge_cap = int(self._selected_provider_frontier_edge_cap())
            rotation_slots = max(
                1, (graph_edge_count + frontier_edge_cap - 1) // frontier_edge_cap
            )
            rotation_index = int(current_block) % rotation_slots
            frontier_seed_telemetry = {
                "enabled": bool(seed_amounts),
                "amounts_scanned": [str(int(value)) for value in seed_amounts],
                "timeout_s": float(seed_timeout_s),
                "budget_s": float(seed_budget_s),
                "candidate_counts": [],
                "scan_errors": [],
                "scan_latency_ms": [],
                "size_economic_matrix": [],
                "size_economic_evidence": [],
                "rotation_index": int(rotation_index),
                "graph_edge_count": int(graph_edge_count),
                "edge_cap": int(frontier_edge_cap),
                "unique_edges_attempted": 0,
                "unique_edges_completed": 0,
                "sampled_graph_coverage_ratio": 0.0,
                "candidates_added": 0,
                "single_notional_provider_guard": True,
                "provider_comparison_cap_applied": False,
                "full_graph_pass": {
                    "attempted": True,
                    "returned": int(len(selected_opps or [])),
                    "chunks_completed": int(full_scan_telemetry.get("chunks_completed", 0)),
                    "chunks_total": int(full_scan_telemetry.get("chunks_total", 0)),
                    "edges_covered": int(full_scan_telemetry.get("edges_covered", 0)),
                    "edges_total": int(full_scan_telemetry.get("edges_total", 0)),
                    "timeout_s": float(full_scan_telemetry.get("budget_s") or selection_timeout_s),
                },
            }

            merged_seed_candidates: List[Opportunity] = list(selected_opps or [])
            seen_seed_keys: set[tuple[str, str]] = set()
            for candidate in merged_seed_candidates:
                route_id = str(
                    getattr(candidate, "route_id", "")
                    or getattr(candidate, "id", "")
                    or ""
                )
                try:
                    candidate_amount = str(
                        int(
                            getattr(
                                getattr(candidate, "route", None).legs[0],
                                "amount_in",
                                0,
                            )
                            or 0
                        )
                    )
                except (AttributeError, IndexError, TypeError, ValueError):
                    candidate_amount = ""
                seen_seed_keys.add((route_id, candidate_amount))

            publish_rpc_selection_progress(
                "selected_provider_frontier_seed",
                details={
                    "scan_kind": "frontier_seed",
                    "seed_count": len(seed_amounts),
                    "seeds_completed": 0,
                    "rotation_index": int(rotation_index),
                    "edge_cap": int(frontier_edge_cap),
                },
            )
            seed_started = time.perf_counter()
            previous_provider_comparison = bool(
                getattr(self, "_rpc_provider_comparison", False)
            )
            try:
                for seed_index, seed_amount in enumerate(seed_amounts):
                    remaining = float(seed_budget_s) - (
                        time.perf_counter() - seed_started
                    )
                    if remaining <= 0:
                        break
                    timeout = min(float(seed_timeout_s), remaining)
                    seed_cache = PerBlockCache()
                    seed_sink: Dict[str, Any] = {}
                    seed_context = dict(discovery_context)
                    if callable(slice_fn):
                        edge_offset = _selected_provider_frontier_slice_offset(
                            graph_edge_count=graph_edge_count,
                            edge_cap=frontier_edge_cap,
                            seed_index=seed_index,
                            seed_count=len(seed_amounts),
                            rotation_index=rotation_index,
                        )
                        seed_context["_provider_scan_pool_event_cache"] = slice_fn(
                            edge_offset,
                            frontier_edge_cap,
                        )
                    else:
                        frontier_edge_cap = 0
                        edge_offset = 0
                    # Critical guard: a frontier seed represents exactly one
                    # alternate notional. It must never recurse into the adaptive
                    # ladder inside _scan_primary_opportunities.
                    seed_context["_selected_provider_full_graph_base_only"] = True
                    scan_started = time.perf_counter()
                    try:
                        if selected_provider_url == bootstrap_url:
                            frontier = await asyncio.wait_for(
                                self._scan_primary_opportunities(
                                    bootstrap_rpc,
                                    current_block=int(current_block),
                                    amount_in=int(seed_amount),
                                    cache=seed_cache,
                                    discovery_context=seed_context,
                                    telemetry_sink=seed_sink,
                                    shared_token_scan_amounts=shared_token_scan_amounts,
                                    force_adaptive_size_scan=False,
                                ),
                                timeout=timeout,
                            )
                        else:
                            async with JsonRpcClient(
                                selected_provider_url,
                                timeout_s=10.0,
                                max_concurrency=30,
                                max_batch=80,
                            ) as seed_rpc:
                                frontier = await asyncio.wait_for(
                                    self._scan_primary_opportunities(
                                        seed_rpc,
                                        current_block=int(current_block),
                                        amount_in=int(seed_amount),
                                        cache=seed_cache,
                                        discovery_context=seed_context,
                                        telemetry_sink=seed_sink,
                                        shared_token_scan_amounts=shared_token_scan_amounts,
                                        force_adaptive_size_scan=False,
                                    ),
                                    timeout=timeout,
                                )

                        additions = 0
                        for candidate in list(frontier or []):
                            route_id = str(
                                getattr(candidate, "route_id", "")
                                or getattr(candidate, "id", "")
                                or ""
                            )
                            try:
                                candidate_amount = str(
                                    int(
                                        getattr(
                                            getattr(candidate, "route", None).legs[0],
                                            "amount_in",
                                            0,
                                        )
                                        or 0
                                    )
                                )
                            except (AttributeError, IndexError, TypeError, ValueError):
                                candidate_amount = ""
                            key = (route_id, candidate_amount)
                            if key in seen_seed_keys:
                                continue
                            seen_seed_keys.add(key)
                            meta = getattr(candidate, "meta", None)
                            if isinstance(meta, dict):
                                meta["adaptive_seed_amount_in"] = str(int(seed_amount))
                            else:
                                candidate.meta = {
                                    "adaptive_seed_amount_in": str(int(seed_amount))
                                }
                            merged_seed_candidates.append(candidate)
                            additions += 1

                        frontier_seed_telemetry["candidate_counts"].append(
                            {
                                "amount_in": str(int(seed_amount)),
                                "edge_offset": int(edge_offset),
                                "edge_cap": int(frontier_edge_cap),
                                "graph_edge_count": int(graph_edge_count),
                                "rotation_index": int(rotation_index),
                                "status": "completed",
                                "returned": int(len(frontier or [])),
                                "added": int(additions),
                            }
                        )
                        publish_rpc_selection_progress(
                            "selected_provider_frontier_seed",
                            details={
                                "seeds_completed": len(frontier_seed_telemetry["candidate_counts"]),
                                "seed_candidates_returned": sum(
                                    int(row.get("returned") or 0)
                                    for row in frontier_seed_telemetry["candidate_counts"]
                                ),
                                "seed_candidates_added": sum(
                                    int(row.get("added") or 0)
                                    for row in frontier_seed_telemetry["candidate_counts"]
                                ),
                            },
                        )
                        for matrix_row in list(seed_sink.get("size_economic_matrix") or []):
                            if not isinstance(matrix_row, dict):
                                continue
                            row = dict(matrix_row)
                            row.update({
                                "frontier_seed_sampled": True,
                                "frontier_seed_edge_offset": int(edge_offset),
                                "frontier_seed_edge_cap": int(frontier_edge_cap),
                                "frontier_seed_graph_edge_count": int(graph_edge_count),
                                "frontier_seed_rotation_index": int(rotation_index),
                                "execution_authority_granted": False,
                            })
                            frontier_seed_telemetry["size_economic_matrix"].append(row)
                        for evidence_row in list(seed_sink.get("size_economic_evidence") or []):
                            if not isinstance(evidence_row, dict):
                                continue
                            row = dict(evidence_row)
                            row.update({
                                "frontier_seed_sampled": True,
                                "frontier_seed_edge_offset": int(edge_offset),
                                "frontier_seed_edge_cap": int(frontier_edge_cap),
                                "frontier_seed_graph_edge_count": int(graph_edge_count),
                                "frontier_seed_rotation_index": int(rotation_index),
                                "execution_authority_granted": False,
                            })
                            frontier_seed_telemetry["size_economic_evidence"].append(row)
                        frontier_seed_telemetry["scan_latency_ms"].append(
                            float(
                                seed_sink.get("scan_latency_ms")
                                or ((time.perf_counter() - scan_started) * 1000.0)
                            )
                        )
                    except asyncio.TimeoutError:
                        frontier_seed_telemetry["candidate_counts"].append({
                            "amount_in": str(int(seed_amount)),
                            "edge_offset": int(edge_offset),
                            "edge_cap": int(frontier_edge_cap),
                            "graph_edge_count": int(graph_edge_count),
                            "rotation_index": int(rotation_index),
                            "status": "timed_out",
                            "returned": 0,
                            "added": 0,
                        })
                        frontier_seed_telemetry["scan_errors"].append(
                            {
                                "amount_in": str(int(seed_amount)),
                                "edge_offset": int(edge_offset),
                                "reason": "frontier_seed_timeout",
                                "timeout_s": float(timeout),
                            }
                        )
                        publish_rpc_selection_progress(
                            "selected_provider_frontier_seed",
                            details={
                                "seeds_completed": len(frontier_seed_telemetry["candidate_counts"]),
                                "seed_timeouts": sum(
                                    row.get("status") == "timed_out"
                                    for row in frontier_seed_telemetry["candidate_counts"]
                                ),
                            },
                        )
                    except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
                        frontier_seed_telemetry["candidate_counts"].append({
                            "amount_in": str(int(seed_amount)),
                            "edge_offset": int(edge_offset),
                            "edge_cap": int(frontier_edge_cap),
                            "graph_edge_count": int(graph_edge_count),
                            "rotation_index": int(rotation_index),
                            "status": "failed",
                            "returned": 0,
                            "added": 0,
                        })
                        frontier_seed_telemetry["scan_errors"].append(
                            {
                                "amount_in": str(int(seed_amount)),
                                "edge_offset": int(edge_offset),
                                "reason": f"{type(exc).__name__}: {exc}",
                            }
                        )
                        publish_rpc_selection_progress(
                            "selected_provider_frontier_seed",
                            details={
                                "seeds_completed": len(frontier_seed_telemetry["candidate_counts"]),
                                "seed_failures": sum(
                                    row.get("status") == "failed"
                                    for row in frontier_seed_telemetry["candidate_counts"]
                                ),
                            },
                        )
            finally:
                self._rpc_provider_comparison = previous_provider_comparison

            attempted_edges = set()
            completed_edges = set()
            for sample in list(frontier_seed_telemetry.get("candidate_counts") or []):
                try:
                    offset = max(0, int(sample.get("edge_offset") or 0))
                    cap = max(0, int(sample.get("edge_cap") or 0))
                    end = min(int(graph_edge_count), offset + cap)
                    attempted_edges.update(range(offset, max(offset, end)))
                    if str(sample.get("status") or "") == "completed":
                        completed_edges.update(range(offset, max(offset, end)))
                except (TypeError, ValueError):
                    continue
            frontier_seed_telemetry["unique_edges_attempted"] = len(attempted_edges)
            frontier_seed_telemetry["unique_edges_completed"] = len(completed_edges)
            frontier_seed_telemetry["sampled_graph_coverage_ratio"] = round(
                float(len(completed_edges)) / float(max(1, int(graph_edge_count))),
                6,
            )
            selected_opps = merged_seed_candidates
            frontier_seed_telemetry["candidates_added"] = max(
                0,
                int(len(selected_opps)) - int(len(selected_result[1] or [])),
            )

        adaptive_telemetry["frontier_seed"] = frontier_seed_telemetry
        publish_rpc_selection_progress(
            "selected_provider_size_curve",
            details={
                "scan_kind": "selected_provider_size_curve",
                "frontier_seed_attempted": bool(frontier_seed_telemetry.get("enabled")),
                "frontier_seed_candidates_added": int(frontier_seed_telemetry.get("candidates_added", 0) or 0),
            },
        )
        try:
            if selected_provider_url == bootstrap_url:
                selected_provider_rpc = bootstrap_rpc
                adaptive_opps, adaptive_telemetry = await asyncio.wait_for(

                    self._run_bounded_selected_provider_size_probe(

                        selected_provider_rpc,

                        current_block=int(current_block),

                        base_amount_in=int(amount_in),

                        base_opps=list(selected_opps or []),

                        cache=adaptive_cache,

                    ),

                    timeout=selection_timeout_s,

                )
            else:
                async with JsonRpcClient(
                    selected_provider_url,
                    timeout_s=10.0,
                    max_concurrency=30,
                    max_batch=80,
                ) as selected_provider_rpc:
                    adaptive_opps, adaptive_telemetry = await asyncio.wait_for(

                        self._run_bounded_selected_provider_size_probe(

                            selected_provider_rpc,

                            current_block=int(current_block),

                            base_amount_in=int(amount_in),

                            base_opps=list(selected_opps or []),

                            cache=adaptive_cache,

                        ),

                        timeout=selection_timeout_s,

                    )
        except asyncio.TimeoutError:
            adaptive_telemetry.setdefault("scan_error", "selected_provider_adaptive_timeout")
            adaptive_telemetry["provider_scan_timeout_s"] = selection_timeout_s
            adaptive_opps = list(selected_opps or [])
        except _SAFE_SCAN_TELEMETRY_EXCEPTIONS as exc:
            adaptive_telemetry.setdefault("scan_error", f"{type(exc).__name__}: {exc}")
            adaptive_opps = list(selected_opps or [])

        # Preserve frontier-rescue telemetry inside the public adaptive-size
        # payload so market-pipeline consumers can see exactly why alternate
        # notionals were scanned and whether they introduced new routes.
        if frontier_seed_telemetry:
            adaptive_state = dict(adaptive_telemetry.get("adaptive_size_discovery") or {})
            adaptive_state["frontier_seed"] = dict(frontier_seed_telemetry)
            adaptive_telemetry["adaptive_size_discovery"] = adaptive_state

        # Keep provider-comparison telemetry as the symmetric baseline, but
        # always preserve the selected provider's adaptive pass separately.
        # An adaptive scan can legitimately produce zero executable candidates
        # while still producing the size/economic matrix needed to prove that
        # the full frontier was modeled. Never let an empty opportunity list
        # erase that evidence.
        if adaptive_telemetry:
            selected_telemetry = dict(selected_telemetry)
            selected_adaptive = dict(adaptive_telemetry)
            selected_adaptive["rpc"] = dict(selected_adaptive.get("rpc") or {})
            selected_adaptive["rpc"].update({
                "endpoint": selected_url,
                "provider": str(urlsplit(selected_url).hostname or ""),
            })
            selected_telemetry["selected_provider_adaptive"] = selected_adaptive
            if selected_adaptive.get("adaptive_size_discovery"):
                selected_telemetry["adaptive_size_discovery"] = dict(
                    selected_adaptive["adaptive_size_discovery"]
                )
            adaptive_matrix = list(selected_adaptive.get("size_economic_matrix") or [])
            frontier_matrix = list(frontier_seed_telemetry.get("size_economic_matrix") or [])
            if adaptive_matrix or frontier_matrix:
                selected_telemetry["size_economic_matrix"] = _merge_size_economic_matrices(
                    list(selected_telemetry.get("size_economic_matrix") or []),
                    adaptive_matrix,
                    frontier_matrix,
                )
            adaptive_evidence = list(selected_adaptive.get("size_economic_evidence") or [])
            frontier_evidence = list(frontier_seed_telemetry.get("size_economic_evidence") or [])
            if adaptive_evidence or frontier_evidence:
                selected_telemetry["size_economic_evidence"] = [
                    *list(selected_telemetry.get("size_economic_evidence") or []),
                    *adaptive_evidence,
                    *frontier_evidence,
                ]
        if adaptive_opps:
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

        # Add the selected provider's full adaptive-size pass to the same
        # provider union. Other providers remain base-size comparison passes;
        # the selected provider is the only one allowed to expand the economic
        # sizing curve in this tick.
        for opportunity in list(adaptive_opps or []):
            route_id = str(getattr(opportunity, "route_id", "") or "")
            meta = getattr(opportunity, "meta", None)
            meta = meta if isinstance(meta, dict) else {}
            amount_key = ""
            try:
                amount_key = str(
                    getattr(getattr(opportunity, "route", None).legs[0], "amount_in", "")
                )
            except (AttributeError, IndexError, TypeError):
                pass
            key = (route_id, amount_key)
            if not route_id:
                key = (str(getattr(opportunity, "id", "") or ""), amount_key)
            meta["quote_provider_endpoint"] = selected_url
            meta["quote_provider"] = str(urlsplit(selected_url).hostname or "")
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
            "selected_provider_full_scan": dict(
                selected_telemetry.get("selected_provider_full_scan") or {}
            ),
            "selected_provider_adaptive": dict(
                selected_telemetry.get("selected_provider_adaptive") or {}
            ),
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
        completed_ms = int(time.time() * 1000)
        publish_rpc_selection_progress("complete")
        progress_snapshot = dict(
            (getattr(self, "_market_pipeline_telemetry", {}) or {}).get(
                "rpc_selection_progress"
            ) or {}
        )
        selected_telemetry["rpc_selection_phase"] = "complete"
        selected_telemetry["rpc_selection_started_ms"] = selection_started_ms
        selected_telemetry["rpc_selection_completed_ms"] = completed_ms
        selected_telemetry["rpc_provider_scan_timeout_s"] = float(selection_timeout_s)
        selected_telemetry["rpc_selection_progress"] = progress_snapshot
        self._market_pipeline_telemetry = {
            **dict(getattr(self, "_market_pipeline_telemetry", {}) or {}),
            "rpc_selection_phase": "complete",
            "rpc_selection_completed_ms": completed_ms,
            "rpc_selection_progress": progress_snapshot,
        }
        return {
            "selected_endpoint": selected_url,
            "opps": selected_opps,
            "cache": selected_cache,
            "telemetry": selected_telemetry,
            "evidence": evidence,
        }

    @staticmethod
    def _provider_scan_timeout_s() -> float:
        """Bound each provider's initial read-only comparison scan."""
        try:
            configured = float(
                os.environ.get("VICTOR_RPC_PROVIDER_SCAN_TIMEOUT_S", "35.0") or 35.0
            )
        except (TypeError, ValueError):
            configured = 35.0
        return max(5.0, min(configured, 120.0))

    @staticmethod
    def _provider_comparison_edge_cap() -> int:
        """Bound provider benchmarking without limiting the selected provider scan."""
        try:
            configured = int(
                os.environ.get("VICTOR_RPC_PROVIDER_COMPARISON_EDGE_CAP", "96") or 96
            )
        except (TypeError, ValueError):
            configured = 96
        return max(32, min(configured, 256))

    def _selected_provider_full_scan_chunk_size(self) -> int:
        """Use smaller default rescue chunks on Arbitrum, where provider scans time out."""
        chain = getattr(getattr(self, "cfg", None), "chain", None)
        try:
            chain_id = int(getattr(chain, "chain_id", 0) or 0)
        except (TypeError, ValueError):
            chain_id = 0
        default_size = 8 if chain_id == 42161 else 16
        try:
            configured = int(
                os.environ.get(
                    "VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_SIZE",
                    str(default_size),
                )
                or default_size
            )
        except (TypeError, ValueError):
            configured = default_size
        return max(8, min(configured, 256))

    @staticmethod
    def _selected_provider_full_scan_parallelism() -> int:
        try:
            configured = int(
                os.environ.get(
                    "VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM",
                    "3",
                )
                or 3
            )
        except (TypeError, ValueError):
            configured = 3
        return max(1, min(configured, 3))

    @staticmethod
    def _selected_provider_full_scan_chunk_timeout_s() -> float:
        try:
            configured = float(
                os.environ.get(
                    "VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_TIMEOUT_S",
                    "8.0",
                )
                or 8.0
            )
        except (TypeError, ValueError):
            configured = 8.0
        return max(3.0, min(configured, 15.0))

    def _selected_provider_full_scan_budget_s(self, graph_edge_count: int = 0) -> float:
        """Return a short per-tick budget; rotating slices continue coverage on later blocks."""
        try:
            configured = float(
                os.environ.get(
                    "VICTOR_SELECTED_PROVIDER_FULL_SCAN_BUDGET_S",
                    "8.0",
                )
                or 8.0
            )
        except (TypeError, ValueError):
            configured = 8.0
        # Never let an operator override turn the rescue scan into a 60-second
        # per-chain monopolist. Large graphs get more priority within this hard
        # cap, while rotating chunk order advances coverage on subsequent blocks.
        configured = max(5.0, min(configured, 12.0))
        chunk_size = self._selected_provider_full_scan_chunk_size()
        parallelism = self._selected_provider_full_scan_parallelism()
        chunks = max(1, (max(1, int(graph_edge_count)) + chunk_size - 1) // chunk_size)
        waves = max(1, (chunks + parallelism - 1) // parallelism)
        adaptive = configured * float(waves) / 4.0
        return min(12.0, max(configured, adaptive))

    @staticmethod
    def _selected_provider_frontier_seed_budget_s() -> float:
        """Reserve a bounded wall-clock window for alternate-size discovery."""
        try:
            configured = float(
                os.environ.get("VICTOR_ADAPTIVE_SIZE_FRONTIER_SEED_BUDGET_S", "10.0")
                or 10.0
            )
        except (TypeError, ValueError):
            configured = 10.0
        return max(3.0, min(configured, 12.0))

    @staticmethod
    def _selected_provider_frontier_edge_cap() -> int:
        try:
            configured = int(
                os.environ.get(
                    "VICTOR_SELECTED_PROVIDER_FRONTIER_EDGE_CAP",
                    "32",
                )
                or 96
            )
        except (TypeError, ValueError):
            configured = 96
        return max(32, min(configured, 192))

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

    def _build_provider_comparison_pool_event_cache(
        self,
        discovery_context: Dict[str, Any],
        *,
        current_block: int,
    ) -> _FrozenProviderScanPoolEventCache:
        """Freeze one event-prioritized graph so every provider sees identical routes."""
        extra_kwargs = {
            "extra_v3_pairs": list(discovery_context.get("v3_pairs") or []),
            "extra_curve_pools": list(discovery_context.get("curve_pools") or []),
            "extra_balancer_pools": list(discovery_context.get("balancer_pools") or []),
            "extra_aerodrome_pools": list(discovery_context.get("aerodrome_pools") or []),
            "extra_slipstream_pools": list(discovery_context.get("slipstream_pools") or []),
            "extra_camelot_algebra_pools": list(discovery_context.get("camelot_algebra_pools") or []),
            "extra_camelot_v2_pools": list(discovery_context.get("camelot_v2_pools") or []),
            "extra_constant_product_pools": list(discovery_context.get("constant_product_pools") or []),
        }
        edges = build_edges(self.cfg, **extra_kwargs)
        source = getattr(self, "_pool_event_cache", None)
        telemetry: Dict[str, Any] = {
            "enabled": False,
            "candidate_generation_mode": "full_graph",
            "candidate_edge_count": int(len(edges)),
            "candidate_edges_full": int(len(edges)),
            "candidate_edges_pruned": 0,
            "provider_comparison_frozen": True,
        }
        selected_edges = list(edges)
        if source is not None:
            try:
                source.refresh_edges(
                    edges,
                    balancer_vault=str(getattr(self.cfg.chain, "balancer_vault", "") or ""),
                )
                selected_edges, source_metrics = source.candidate_edges(
                    edges,
                    current_block=int(current_block),
                    max_candidates=int(
                        os.environ.get("VICTOR_EVENT_CANDIDATE_MAX", "768") or 768
                    ),
                    exploration_ratio=float(
                        os.environ.get("VICTOR_EVENT_EXPLORATION_RATIO", "0.10") or 0.10
                    ),
                )
                telemetry.update(dict(source_metrics or {}))
            except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
                selected_edges = list(edges)
        priorities: Dict[int, int] = {}
        if source is not None:
            for edge in selected_edges:
                try:
                    priorities[id(edge)] = int(
                        source.edge_priority(edge, current_block=int(current_block))
                    )
                except _SAFE_SCAN_TELEMETRY_EXCEPTIONS:
                    priorities[id(edge)] = 1
        telemetry["provider_comparison_frozen"] = True
        telemetry["candidate_edge_count"] = int(len(selected_edges))
        telemetry["candidate_edges_full"] = int(telemetry.get("candidate_edges_full") or len(edges))
        telemetry["candidate_edges_pruned"] = int(
            max(0, int(telemetry["candidate_edges_full"]) - len(selected_edges))
        )
        return _FrozenProviderScanPoolEventCache(
            selected_edges,
            telemetry,
            priorities,
            route_universe_edges=selected_edges,
        )

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
            "aerodrome": (
                list(discovery.aerodrome_pools())
                if discovery is not None
                and callable(getattr(discovery, "aerodrome_pools", None))
                else []
            ),
            "slipstream": (
                list(discovery.slipstream_pools())
                if discovery is not None
                and callable(getattr(discovery, "slipstream_pools", None))
                else []
            ),
            "camelot_algebra": (
                list(discovery.camelot_algebra_pools())
                if discovery is not None
                and callable(getattr(discovery, "camelot_algebra_pools", None))
                else []
            ),
            "camelot_v2": (
                list(discovery.camelot_v2_pools())
                if discovery is not None
                and callable(getattr(discovery, "camelot_v2_pools", None))
                else []
            ),
            "constant_product": [v.to_pool() for v in getattr(discovery, "_constant_product", {}).values()] if discovery is not None else [],
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
            "aerodrome_pools": list(venue_pools.get("aerodrome") or []),
            "slipstream_pools": list(venue_pools.get("slipstream") or []),
            "camelot_algebra_pools": list(venue_pools.get("camelot_algebra") or []),
            "camelot_v2_pools": list(venue_pools.get("camelot_v2") or []),
            "constant_product_pools": list(venue_pools.get("constant_product") or []),
            "runtime": {
                "budget_timeout_s": float(timeout_s),
                "stages": stages,
                "used_persisted_fallback": any(
                    stage.get("status") != "completed" for stage in stages
                ),
            },
        }