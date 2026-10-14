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

    assert telemetry["route_budget_exhausted"] is True
    assert telemetry["route_groups_evaluated"] == 0
    assert telemetry["first_leg_quote_batches_cancelled"] == 1
    assert telemetry["route_budget_stop_reason"] == "time_budget"


@pytest.mark.asyncio
async def test_first_leg_quote_wave_cancels_late_batches_and_retains_completed_results(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    token_c = "0x" + "33" * 20
    router = "0x" + "aa" * 20
    edges = [
        arb.Edge("univ3", router, token_a, token_b, {"fee": 500}),
        arb.Edge("univ3", router, token_b, token_c, {"fee": 3000}),
        arb.Edge("aerodrome", router, token_c, token_a, {"stable": True}),
    ]
    calls = []

    async def fake_quote_batch(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        calls.append((int(amount_in), tuple(arb.edge_key(edge) for edge in requested_edges)))
        if int(amount_in) == 200:
            await asyncio.sleep(0.2)
        else:
            await asyncio.sleep(0.001)
        return {
            arb.edge_key(edge): (123 + int(amount_in), {"fee": 3000})
            for edge in requested_edges
        }

    monkeypatch.setattr(arb, "quote_edges_batch", fake_quote_batch)
    deadline = __import__("time").perf_counter() + 0.03
    quotes, schedule = await arb._quote_edge_groups_in_bounded_waves(
        object(),
        object(),
        object(),
        [(100, [edges[0]]), (200, [edges[1]]), (300, [edges[2]])],
        deadline=deadline,
        block_number=0,
        parallelism=2,
        metrics={},
    )

    assert sorted(amount for amount, _ in calls) == [100, 200]
    assert schedule["batches_total"] == 3
    assert schedule["batches_completed"] == 1
    assert schedule["batches_failed"] == 0
    assert schedule["batches_cancelled"] == 1
    assert schedule["batches_skipped_budget"] == 1
    assert schedule["waves_started"] == 1
    assert schedule["deadline_exceeded"] is True
    assert arb.edge_key(edges[0]) in quotes
    assert arb.edge_key(edges[1]) not in quotes



@pytest.mark.asyncio
async def test_first_leg_quote_wave_cleans_up_when_caller_is_cancelled(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    edge = arb.Edge(
        "univ3",
        "0x" + "aa" * 20,
        token_a,
        token_b,
        {"fee": 3000},
    )
    started = asyncio.Event()
    cleaned = []

    async def slow_quote_batch(rpc, cfg, cache, requested_edges, amount_in, metrics=None):
        started.set()
        try:
            await asyncio.sleep(10)
        finally:
            cleaned.append(int(amount_in))
        return {}

    monkeypatch.setattr(arb, "quote_edges_batch", slow_quote_batch)
    scan = asyncio.create_task(
        arb._quote_edge_groups_in_bounded_waves(
            object(),
            object(),
            object(),
            [(100, [edge]), (200, [edge])],
            deadline=__import__("time").perf_counter() + 10,
            block_number=0,
            parallelism=1,
            metrics={},
        )
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    scan.cancel()
    with pytest.raises(asyncio.CancelledError):
        await scan

    assert cleaned == [100]


@pytest.mark.asyncio
async def test_cancelled_first_leg_recovers_completed_quote_cache_entries(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    token_c = "0x" + "33" * 20
    router = "0x" + "aa" * 20
    completed_edge = arb.Edge("univ3", router, token_a, token_b, {"fee": 500})
    in_flight_edge = arb.Edge(
        "balancer", "0x" + "bb" * 20, token_b, token_c,
        {"pool_id": "0x" + "cc" * 32},
    )

    class Cache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

    cache = Cache()
    result_value = (123_456, {"fee": 500})
    started = asyncio.Event()

    async def partial_quote_batch(_rpc, _cfg, local_cache, requested_edges, amount_in, metrics=None):
        del metrics
        local_cache.set(
            arb._edge_quote_cache_key(completed_edge, amount_in),
            result_value,
        )
        started.set()
        # Simulate a later venue's quote still in flight when the shared deadline
        # expires. The already-cached UniV3 result is usable; the Balancer result
        # does not exist and must not be synthesized.
        await asyncio.Event().wait()
        return {
            arb.edge_key(completed_edge): result_value,
            arb.edge_key(in_flight_edge): (999_999, {}),
        }

    monkeypatch.setattr(arb, "quote_edges_batch", partial_quote_batch)
    quotes, schedule = await arb._quote_edge_groups_in_bounded_waves(
        object(),
        object(),
        cache,
        [(100_000, [completed_edge, in_flight_edge])],
        deadline=__import__("time").perf_counter() + 0.03,
        block_number=1,
        parallelism=1,
        metrics={},
    )

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert quotes[arb.edge_key(completed_edge)] == result_value
    assert arb.edge_key(in_flight_edge) not in quotes
    assert schedule["batches_completed"] == 0
    assert schedule["batches_cancelled"] == 1
    assert schedule["partial_quote_edges_recovered_after_cancellation"] == 1
    assert schedule["deadline_exceeded"] is True


@pytest.mark.asyncio
async def test_third_leg_quote_jobs_are_bounded_and_recover_cached_successes(monkeypatch):
    token_a = "0x" + "11" * 20
    token_b = "0x" + "22" * 20
    token_c = "0x" + "33" * 20
    router = "0x" + "aa" * 20
    completed_edge = arb.Edge("univ3", router, token_a, token_b, {"fee": 500})
    cancelled_edge = arb.Edge("balancer", router, token_b, token_c, {"pool_id": "0x" + "cc" * 32})
    skipped_edge = arb.Edge("curve", "0x" + "dd" * 20, token_c, token_a, {"i": 0, "j": 1})

    class Cache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

    cache = Cache()
    completed_value = (111_000, {"fee": 500})
    recovered_value = (222_000, {"pool_id": "0x" + "cc" * 32})
    started = asyncio.Event()
    calls = []

    async def fake_quote_batch(_rpc, _cfg, local_cache, requested_edges, amount_in, metrics=None):
        amount = int(amount_in)
        calls.append(amount)
        if amount == 200:
            local_cache.set(
                arb._edge_quote_cache_key(cancelled_edge, amount),
                recovered_value,
            )
            started.set()
            await asyncio.Event().wait()
        await asyncio.sleep(0.001)
        return {
            arb.edge_key(edge): (
                completed_value if amount == 100 else (333_000, {})
            )
            for edge in requested_edges
        }

    def signature(amount, edges):
        return (int(amount), tuple(sorted(arb.edge_key(edge) for edge in edges)))

    jobs = [
        (signature(100, [completed_edge]), 100, [completed_edge]),
        (signature(200, [cancelled_edge]), 200, [cancelled_edge]),
        (signature(300, [skipped_edge]), 300, [skipped_edge]),
    ]
    monkeypatch.setattr(arb, "quote_edges_batch", fake_quote_batch)

    results, schedule = await arb._quote_edge_jobs_in_bounded_waves(
        object(),
        object(),
        cache,
        jobs,
        deadline=__import__("time").perf_counter() + 0.04,
        parallelism=2,
        metrics={},
    )

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert sorted(calls) == [100, 200]
    assert results[signature(100, [completed_edge])][arb.edge_key(completed_edge)] == completed_value
    assert results[signature(200, [cancelled_edge])][arb.edge_key(cancelled_edge)] == recovered_value
    assert signature(300, [skipped_edge]) not in results
    assert schedule["batches_total"] == 3
    assert schedule["batches_completed"] == 1
    assert schedule["batches_failed"] == 0
    assert schedule["batches_cancelled"] == 1
    assert schedule["batches_skipped_budget"] == 1
    assert schedule["partial_quote_edges_recovered_after_cancellation"] == 1
    assert schedule["waves_started"] == 1
    assert schedule["parallelism_limit"] == 2
    assert schedule["deadline_exceeded"] is True


@pytest.mark.asyncio
async def test_two_leg_route_group_wave_cancels_at_deadline_and_recovers_exact_cache(monkeypatch):
    token_a = "0x" + "51" * 20
    token_b = "0x" + "52" * 20
    edge = arb.Edge("univ3", "0x" + "53" * 20, token_a, token_b, {"fee": 3000})

    class Cache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

    cache = Cache()
    quote = (909, {"fee": 3000})
    started = asyncio.Event()

    async def slow_quote(_rpc, _cfg, local_cache, edges, amount_in, metrics=None):
        del metrics
        local_cache.set(arb._edge_quote_cache_key(edge, amount_in), quote)
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(arb, "quote_edges_batch", slow_quote)
    metrics = {}
    maps, completed, coalesced = await arb._quote_two_leg_route_group_wave(
        object(),
        object(),
        cache,
        [{"out1": 100, "revs": [edge]}],
        metrics=metrics,
        deadline=__import__("time").perf_counter() + 0.03,
    )

    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert maps == [{arb.edge_key(edge): quote}]
    assert completed == 0
    assert coalesced == 0
    assert metrics["route_group_quote_batches_cancelled"] == 1
    assert metrics["route_group_quote_edges_recovered_after_cancellation"] == 1

