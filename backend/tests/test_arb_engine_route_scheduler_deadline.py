from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import victor_ai_bot.arb_engine as arb


@pytest.mark.asyncio
async def test_completed_first_leg_quote_is_consumed_but_no_more_than_one_wave_after_deadline(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    token_c = "0x" + "33" * 20
    edges = [
        arb.Edge("univ3", "0x" + "aa" * 20, token_a, token_b, {"fee": 3000}),
        arb.Edge("univ3", "0x" + "bb" * 20, token_b, token_a, {"fee": 3000}),
        arb.Edge("aerodrome", "0x" + "cc" * 20, token_a, token_c, {"stable": True}),
        arb.Edge("aerodrome", "0x" + "dd" * 20, token_c, token_a, {"stable": True}),
    ]
    monkeypatch.setattr(arb, "build_edges", lambda *args, **kwargs: edges)
    batches = []

    async def fake_quotes(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        batches.append(tuple(arb.edge_key(edge) for edge in requested_edges))
        await asyncio.sleep(0.01)
        return {
            arb.edge_key(edge): (
                110 if edge.token_out == token_b else 105,
                {"fee": 3000, "gas_estimate": 1},
            )
            for edge in requested_edges
        }

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quotes)
    monkeypatch.setattr(arb, "scan_efficiency_snapshot", lambda **kwargs: {
        "elapsed_ms": 0.0,
        "candidate_count": int(kwargs["candidate_count"]),
        "quote_requests": int(kwargs["quote_requests"]),
        "quote_successes": int(kwargs["quote_successes"]),
        "quote_success_rate": 1.0,
        "cache_hits": 0,
        "network_batches": len(batches),
    })
    cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"), safety=SimpleNamespace(slippage_bps=50))
    telemetry = {}
    await arb.find_two_leg_opportunities(
        object(), cfg, object(), 123, amount_in=100, slippage_bps=50,
        time_budget_ms=1, telemetry=telemetry,
    )

    assert telemetry["route_budget_elapsed_ms"] >= 10.0
    assert telemetry["route_budget_exhausted"] is True
    assert telemetry["route_groups_evaluated"] <= arb._route_group_parallelism()
    assert telemetry["route_budget_stop_reason"] == "time_budget"
