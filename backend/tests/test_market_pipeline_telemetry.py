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
                "route_group_schedule": {
                    "block_number": 200,
                    "groups_prepared": 2,
                    "groups_completed": 2,
                    "quote_batches_completed_and_consumed": 2,
                    "duplicate_quote_batches_coalesced": 0,
                    "parallelism_limit": 3,
                    "waves_started": 1,
                    "ordering": "round_robin_source_token_protocol",
                    "completed_wave_results_consumed_before_budget_stop": True,
                },
                "route_group_schedule_by_block": {
                    "200": {
                        "block_number": 200,
                        "groups_prepared": 2,
                        "groups_completed": 2,
                        "quote_batches_completed_and_consumed": 2,
                        "duplicate_quote_batches_coalesced": 0,
                        "parallelism_limit": 3,
                        "waves_started": 1,
                        "ordering": "round_robin_source_token_protocol",
                        "completed_wave_results_consumed_before_budget_stop": True,
                    },
                },
                "quote_phase_ms": 125.0,
                "route_evaluation_ms": 17.5,
                "route_groups_evaluated": 3,
                "route_budget_exhausted": False,
                "route_budget_stop_reason": "completed",
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
        "endpoint": "rpc.example",
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
        "route_group_schedule": {
            "block_number": 200,
            "groups_prepared": 2,
            "groups_completed": 2,
            "quote_batches_completed_and_consumed": 2,
            "duplicate_quote_batches_coalesced": 0,
            "parallelism_limit": 3,
            "waves_started": 1,
            "ordering": "round_robin_source_token_protocol",
            "completed_wave_results_consumed_before_budget_stop": True,
        },
        "route_group_schedule_by_block": {
            "200": {
                "block_number": 200,
                "groups_prepared": 2,
                "groups_completed": 2,
                "quote_batches_completed_and_consumed": 2,
                "duplicate_quote_batches_coalesced": 0,
                "parallelism_limit": 3,
                "waves_started": 1,
                "ordering": "round_robin_source_token_protocol",
                "completed_wave_results_consumed_before_budget_stop": True,
            },
        },
        "quote_phase_ms": 125.0,
        "route_evaluation_ms": 17.5,
        "route_groups_evaluated": 3,
        "route_budget_exhausted": False,
        "route_budget_stop_reason": "completed",
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


def test_market_pipeline_exposes_live_rpc_selection_progress_without_endpoint_urls():
    runtime = _Runtime()
    runtime._market_pipeline_telemetry.update({
        "rpc_selection_phase": "provider_comparison",
        "rpc_selection_started_ms": 1_800_000_000_000,
        "rpc_provider_scan_timeout_s": 35.0,
        "rpc_selection_progress": {
            "phase": "provider_comparison",
            "started_ms": 1_800_000_000_000,
            "phase_started_ms": 1_800_000_001_000,
            "updated_ms": 1_800_000_012_000,
            "elapsed_ms": 12_000,
            "phase_elapsed_ms": 11_000,
            "provider_count": 2,
            "providers_started": 2,
            "providers_running": 1,
            "providers_completed": 1,
            "providers_failed": 0,
            "providers": [
                {
                    "provider": "rpc-a.example",
                    "status": "completed",
                    "quote_requests": 10,
                    "quote_successes": 10,
                    "candidate_count": 1,
                    "elapsed_ms": 1_200,
                },
                {
                    "provider": "rpc-b.example",
                    "status": "running",
                    "quote_requests": 4,
                    "quote_successes": 3,
                    "candidate_count": 0,
                },
            ],
        },
    })

    out = runtime.market_pipeline_telemetry_state()

    assert out["rpc_selection_phase"] == "provider_comparison"
    assert out["rpc_provider_scan_timeout_s"] == 35.0
    progress = out["rpc_selection_progress"]
    assert progress["phase"] == "provider_comparison"
    assert progress["providers_running"] == 1
    assert [row["status"] for row in progress["providers"]] == [
        "completed", "running"
    ]
    assert [row["provider"] for row in progress["providers"]] == [
        "rpc-a.example", "rpc-b.example"
    ]
    serialized = str(progress)
    assert "https://" not in serialized
    assert "apikey" not in serialized
    assert "password" not in serialized


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


def test_market_pipeline_sanitizes_rpc_urls_and_raw_errors():
    runtime = _Runtime()
    runtime._market_pipeline_telemetry["rpc"].update({
        "endpoint": "https://user:password@rpc.example/v1?apikey=rpc-secret",
        "last_error": "connection failed at https://rpc.example/secret-path?token=error-secret",
    })
    out = runtime.market_pipeline_telemetry_state()
    assert out["rpc"]["endpoint"] == "rpc.example"
    assert out["rpc"]["last_error"] == "rpc_transport_or_provider_error"
    serialized = str(out["rpc"])
    for secret in ("password", "rpc-secret", "secret-path", "error-secret", "/v1"):
        assert secret not in serialized

