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
            "selected_provider_adaptive": {
                "scan_sizing": {
                    "configured_tokens": 5,
                    "research_tokens_considered": 2,
                    "research_tokens_priced": 1,
                    "research_tokens_unpriced": ["0xResearchUnpriced"],
                    "research_token_scan_notional_source": "bounded_research_frontier_quote_derived_usd_notional",
                    "research_token_scan_cap": 8,
                    "research_token_execution_universe_mutated": False,
                }
            },
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
            "size_economic_matrix": [{
                "amount_in": "100",
                "quote_requests": 10,
                "quote_successes": 8,
                "quote_failures": 2,
                "candidates": [],
                "selection_basis": "gross_profit_diagnostic_only",
            }],
            "size_economic_evidence": [{
                "route_id": "route-1",
                "amount_in": "100",
                "after_cost_profit_wei": "0",
            }],
            "size_economic_diagnostics": [],
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
    assert out["scan_sizing"] == {
        "configured_tokens": 5,
        "research_tokens_considered": 2,
        "research_tokens_priced": "1",
        "research_tokens_unpriced": ["0xResearchUnpriced"],
        "research_token_scan_notional_source": "bounded_research_frontier_quote_derived_usd_notional",
        "research_token_scan_cap": "8",
        "research_token_execution_universe_mutated": False,
    }
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
    assert out["size_economic_matrix"][0]["amount_in"] == "100"
    assert out["size_economic_matrix"][0]["quote_failures"] == 2
    assert out["size_economic_evidence"][0]["route_id"] == "route-1"


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

def test_market_pipeline_exposes_gas_consensus_without_rpc_credentials():
    runtime = _Runtime()
    runtime._market_pipeline_telemetry["gas_price_integrity"] = {
        "status": "insufficient_agreement",
        "gas_price_wei": None,
        "provider_count": 2,
        "observed_at": 123.0,
        "observations": [
            {
                "url": "https://user:password@rpc-a.example/v1?apikey=secret-a",
                "provider": "rpc-a.example",
                "block_number": 100,
                "gas_price_wei": 1_000_000_000,
            },
            {
                "url": "https://rpc-b.example/key-secret",
                "provider": "rpc-b.example",
                "block_number": 200,
                "gas_price_wei": 2_000_000_000,
                "error": "provider failure containing secret-b",
            },
        ],
        "anomalies": [
            {"reason": "stale_block", "url": "https://rpc-a.example?apikey=secret-a"},
            {"reason": "stale_block"},
            {"reason": "gas_price_outlier"},
        ],
    }

    summary = runtime.market_pipeline_telemetry_state()["gas_price_integrity"]
    assert summary["status"] == "insufficient_agreement"
    assert summary["provider_count"] == 2
    assert summary["usable_observation_count"] == 1
    assert summary["observations"] == [
        {
            "provider": "rpc-a.example",
            "block_number": 100,
            "gas_price_wei": "1000000000",
            "ok": True,
            "error_present": False,
        },
        {
            "provider": "rpc-b.example",
            "block_number": 200,
            "gas_price_wei": "2000000000",
            "ok": False,
            "error_present": True,
        },
    ]
    assert summary["anomaly_reason_counts"] == {
        "stale_block": 2,
        "gas_price_outlier": 1,
    }
    serialized = str(summary)
    for secret in ("password", "secret-a", "secret-b", "/v1", "/key-secret"):
        assert secret not in serialized

