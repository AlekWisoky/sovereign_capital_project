"""Deterministic scan-density and quote-efficiency metrics.

These metrics are observational only. They do not admit capital, alter route
selection, or bypass the canonical execution/receipt/settlement path.
"""
from __future__ import annotations

from typing import Mapping


def scan_efficiency_snapshot(
    *,
    elapsed_ms: float,
    candidate_count: int,
    quote_requests: int,
    quote_successes: int,
    opportunity_count: int,
    cache_hits: int = 0,
    network_batches: int = 0,
) -> dict[str, float | int]:
    elapsed = max(0.0, float(elapsed_ms))
    seconds = elapsed / 1000.0
    requests = max(0, int(quote_requests))
    successes = max(0, int(quote_successes))
    candidates = max(0, int(candidate_count))
    opportunities = max(0, int(opportunity_count))
    hits = max(0, int(cache_hits))
    batches = max(0, int(network_batches))
    return {
        "elapsed_ms": elapsed,
        "candidate_count": candidates,
        "quote_requests": requests,
        "quote_successes": min(successes, requests) if requests else 0,
        "quote_success_rate": (float(successes) / float(requests)) if requests else 0.0,
        "cache_hits": hits,
        "network_batches": batches,
        "quotes_per_network_batch": (float(requests - hits) / float(batches)) if batches else 0.0,
        "opportunity_count": opportunities,
        "opportunity_density_per_sec": (float(opportunities) / seconds) if seconds > 0 else 0.0,
        "opportunity_rate_per_quote": (float(opportunities) / float(requests)) if requests else 0.0,
    }


def attach_scan_efficiency(meta: Mapping[str, object], snapshot: Mapping[str, object]) -> dict:
    out = dict(meta)
    out["scan_efficiency"] = dict(snapshot)
    return out
