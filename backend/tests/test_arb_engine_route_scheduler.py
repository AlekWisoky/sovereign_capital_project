from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import victor_ai_bot.arb_engine as arb


def test_route_group_scheduler_round_robins_source_token_and_protocol():
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    router = "0x" + "aa" * 20
    first = arb.Edge("univ3", router, token_a, "0x" + "31" * 20, {"fee": 3000})
    second = arb.Edge("univ3", router, token_a, "0x" + "32" * 20, {"fee": 3000})
    other_protocol = arb.Edge("aerodrome", router, token_a, "0x" + "33" * 20, {"stable": True})
    other_token = arb.Edge("univ3", router, token_b, "0x" + "34" * 20, {"fee": 3000})

    scheduled = arb._round_robin_route_group_edges(
        [first, second, other_protocol, other_token]
    )

    # Keep prior order within each family, but ensure less frequent families
    # get a bounded route-evaluation slot before the dominant family repeats.
    assert scheduled == [first, other_protocol, other_token, second]


def test_route_group_parallelism_is_bounded(monkeypatch):
    monkeypatch.setenv("VICTOR_ROUTE_GROUP_PARALLELISM", "99")
    assert arb._route_group_parallelism() == 4
    monkeypatch.setenv("VICTOR_ROUTE_GROUP_PARALLELISM", "0")
    assert arb._route_group_parallelism() == 1


@pytest.mark.asyncio
async def test_two_leg_route_group_wave_coalesces_identical_quote_batches(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    edge = arb.Edge("univ3", "0x" + "aa" * 20, token_a, token_b, {"fee": 3000})
    calls = []

    async def fake_quote_batch(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        calls.append((tuple(arb.edge_key(item) for item in requested_edges), amount_in))
        return {arb.edge_key(item): (123, {"fee": 3000}) for item in requested_edges}

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quote_batch)
    group_a = {"out1": 100, "revs": [edge]}
    group_b = {"out1": 100, "revs": [edge]}
    quote_maps, physical_batches, coalesced = await arb._quote_two_leg_route_group_wave(
        object(), object(), object(), [group_a, group_b], metrics={}
    )

    assert len(calls) == 1
    assert physical_batches == 1
    assert coalesced == 1
    assert quote_maps[0] is quote_maps[1]


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


@pytest.mark.asyncio
async def test_first_leg_quote_wave_stops_at_deadline_and_retains_completed_results(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    router = "0x" + "aa" * 20
    edges = [
        arb.Edge("univ3", router, token_a, token_b, {"fee": 500}),
        arb.Edge("univ3", router, token_a, token_b, {"fee": 3000}),
        arb.Edge("aerodrome", router, token_b, token_a, {"stable": True}),
    ]
    calls = []

    async def fake_quote_batch(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        calls.append((int(amount_in), tuple(arb.edge_key(edge) for edge in requested_edges)))
        await asyncio.sleep(0.01)
        return {
            arb.edge_key(edge): (123 + int(amount_in), {"fee": 3000})
            for edge in requested_edges
        }

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quote_batch)
    deadline = __import__("time").perf_counter() + 0.001
    quotes, schedule = await arb._quote_edge_groups_in_bounded_waves(
        object(),
        object(),
        object(),
        [(100, [edges[0]]), (200, [edges[1]]), (300, [edges[2]])],
        deadline=deadline,
        block_number=0,
        parallelism=1,
        metrics={},
    )

    assert len(calls) == 1
    assert schedule["batches_total"] == 3
    assert schedule["batches_completed"] == 1
    assert schedule["batches_skipped_budget"] == 2
    assert schedule["waves_started"] == 1
    assert schedule["deadline_exceeded"] is True
    # A successful result from the already-started wave survives the deadline.
    first_edge = edges[0]
    assert arb.edge_key(first_edge) in quotes
    assert quotes[arb.edge_key(first_edge)][0] == 223
