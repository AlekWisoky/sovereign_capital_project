from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    _canonical_route_universe_telemetry,
)
from victor_ai_bot.runtime_services.runtime_state_facade import RuntimeStateFacade


class _Runtime(RuntimeStateFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
        self._market_pipeline_telemetry = {
            "last_scan": 1234567890,
            "last_block": 200,
            "scan_latency_ms": 42.5,
            "scan_error": "",
            "discovery": {
                "pools_seen": 7,
                "v3_pairs": 4,
                "curve_pools": 2,
                "balancer_pools": 1,
            },
            "quotes": {"requests": 10, "successes": 8},
            "rpc": {
                "endpoint": "https://rpc.example",
                "provider": "rpc.example",
                "score": 123.4,
                "ok": True,
                "quote_failures": 2,
                "quote_successes": 8,
                "quote_last_error": "rpc_rate_limited",
                "quote_unhealthy_until": 999.0,
            },
            "routes_considered": 12,
            "edges_generated": 20,
            "route_universe": {
                "configured_token_count": 3,
                "active_token_count": 3,
                "edges_by_dex": {"univ3": 20},
                "unique_directed_pairs": 6,
                "directed_pairs_with_reverse": 6,
                "reverse_pair_coverage_ratio": 1.0,
                "univ3_unique_pool_count": 10,
                "univ3_possible_configured_pair_fee_count": 12,
                "univ3_configured_pair_fee_coverage_ratio": 10.0 / 12.0,
            },
            "route_evaluation": {
                "quote_phase_ms": 125.0,
                "route_evaluation_ms": 17.5,
                "route_groups_evaluated": 3,
                "budget_exhausted_after_quote": False,
            },
        }
        self._opps = [
            SimpleNamespace(meta={
                "profitability": {
                    "revalidated": True,
                    "authoritative": True,
                    "profitAfterCostsUsdMicroInt": 5,
                },
                "execution_route_runtime": {"ready": True, "degraded": False},
            }),
            SimpleNamespace(meta={
                "profitability": {
                    "revalidated": True,
                    "authoritative": True,
                    "profitAfterCostsUsdMicroInt": -1,
                },
                "execution_route_runtime": {"ready": False, "degraded": True},
            }),
        ]


def test_market_pipeline_telemetry_preserves_zero_candidate_diagnostics():
    runtime = _Runtime()
    runtime._opps = []
    out = runtime.market_pipeline_telemetry_state()
    assert out["scanner"]["alive"] is True
    assert out["scanner"]["last_block"] == 200
    assert out["discovery"]["pools_seen"] == 7
    assert out["quotes"] == {
        "requests": 10,
        "successes": 8,
        "failures": 2,
        "success_rate": 0.8,
        "failure_reasons": {},
    }
    assert out["rpc"] == {
        "endpoint": "https://rpc.example",
        "provider": "rpc.example",
        "score": 123.4,
        "ok": True,
        "quote_failures": 2,
        "quote_successes": 8,
        "quote_last_error": "rpc_rate_limited",
        "quote_unhealthy_until": 999.0,
    }
    assert out["route_universe"]["configured_token_count"] == 3
    assert out["route_universe"]["univ3_unique_pool_count"] == 10
    assert out["route_universe"]["univ3_configured_pair_fee_coverage_ratio"] == 10.0 / 12.0
    assert out["route_evaluation"] == {
        "quote_phase_ms": 125.0,
        "route_evaluation_ms": 17.5,
        "route_groups_evaluated": 3,
        "budget_exhausted_after_quote": False,
    }
    assert out["economics"] == {
        "gross_candidates": 0,
        "after_fee_candidates": 0,
        "after_fee_positive_candidates": 0,
    }


def test_market_pipeline_telemetry_counts_canonical_profitability_when_candidates_exist():
    out = _Runtime().market_pipeline_telemetry_state()
    assert out["economics"]["gross_candidates"] == 2
    assert out["economics"]["after_fee_candidates"] == 2
    assert out["economics"]["after_fee_positive_candidates"] == 1
    assert all(
        isinstance(out["economics"][key], int)
        for key in (
            "gross_candidates",
            "after_fee_candidates",
            "after_fee_positive_candidates",
        )
    )
    assert out["quality"]["route_quality"] == {
        "ready_candidates": 1,
        "degraded_candidates": 1,
    }


def test_canonical_route_universe_prefers_three_leg_snapshot_without_double_counting():
    two_leg = {
        "route_universe": {
            "configured_token_count": 3,
            "univ3_unique_pool_count": 12,
        }
    }
    three_leg = {
        "route_universe": {
            "configured_token_count": 3,
            "univ3_unique_pool_count": 12,
            "three_leg_max_edges_per_token": 10,
            "three_leg_edges_pruned_by_token_cap": 4,
        }
    }

    out = _canonical_route_universe_telemetry(two_leg, three_leg)

    assert out == three_leg["route_universe"]


def test_market_pipeline_telemetry_exposes_candidate_tokens_separately_from_execution_universe():
    runtime = _Runtime()
    runtime._market_pipeline_telemetry["candidate_token_discovery"] = {
        "execution_universe": ["0x" + "11" * 20],
        "observed_tokens": ["0x" + "11" * 20, "0x" + "22" * 20],
        "observed_not_admitted": ["0x" + "22" * 20],
        "observed_count": 2,
        "observed_not_admitted_count": 1,
        "observation_cap": 64,
        "observation_truncated": False,
        "admission_mutated": False,
        "sources": {"0x" + "22" * 20: ["balancer_pool_candidate"]},
    }
    out = runtime.market_pipeline_telemetry_state()
    candidate = out["candidate_token_discovery"]
    assert candidate["execution_universe"] == ["0x" + "11" * 20]
    assert candidate["observed_not_admitted"] == ["0x" + "22" * 20]
    assert candidate["observed_not_admitted_count"] == 1
    assert candidate["admission_mutated"] is False
