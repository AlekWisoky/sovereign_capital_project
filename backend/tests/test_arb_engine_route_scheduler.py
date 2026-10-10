from __future__ import annotations

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
