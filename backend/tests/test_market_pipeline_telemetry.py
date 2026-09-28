from __future__ import annotations

from types import SimpleNamespace

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
            "routes_considered": 12,
            "edges_generated": 20,
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
    }
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
