from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.pool_state_event_cache import (
    PoolStateEventCache,
    _SYNC_TOPIC,
)
from victor_ai_bot.arb_engine import Edge


def _sync_data(reserve0: int, reserve1: int) -> str:
    return "0x" + f"{reserve0:064x}{reserve1:064x}"


def test_pool_event_cache_tracks_sync_and_prioritizes_affected_pool():
    pool = "0x" + "11" * 20
    other = "0x" + "22" * 20
    cache = PoolStateEventCache(
        chain_name="base",
        chain_id=8453,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
    )
    hot = Edge("univ3", "0x" + "33" * 20, "0x" + "44" * 20, "0x" + "55" * 20, {"pool": pool})
    cold = Edge("univ3", "0x" + "33" * 20, "0x" + "44" * 20, "0x" + "66" * 20, {"pool": other})
    cache.refresh_edges([hot, cold])

    cache._apply_log({
        "address": pool,
        "blockNumber": hex(100),
        "transactionHash": "0xabc",
        "topics": [_SYNC_TOPIC],
        "data": _sync_data(123, 456),
    })

    ordered, telemetry = cache.prioritize_edges([cold, hot], current_block=101)

    assert ordered[0] == hot
    state = cache.state_for_pool(pool)
    assert state is not None
    assert state.reserve0 == 123
    assert state.reserve1 == 456
    assert state.last_event_type == "sync"
    assert telemetry["dirty_edges"] == 1
    assert telemetry["event_count"] == 1


def test_pool_event_cache_bounds_websocket_subscription_addresses():
    cache = PoolStateEventCache(
        chain_name="ethereum",
        chain_id=1,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
        max_addresses=2,
    )
    edges = [
        Edge("univ3", "0x" + "33" * 20, "0x" + f"{i + 1:040x}", "0x" + f"{i + 100:040x}", {"pool": "0x" + f"{i + 200:040x}"})
        for i in range(20)
    ]
    cache.refresh_edges(edges)

    addresses = cache._subscription_addresses()

    assert len(addresses) == 16
    assert cache.snapshot()["subscription_truncated"] is True


def test_pool_event_cache_generates_dirty_subgraph_and_preserves_reverse_pair():
    cache = PoolStateEventCache(
        chain_name="base",
        chain_id=8453,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
    )
    token_a = "0x" + "aa" * 20
    token_b = "0x" + "bb" * 20
    hot_pool = "0x" + "10" * 20
    reverse_pool = "0x" + "11" * 20
    hot = Edge("univ3", "0x" + "30" * 20, token_a, token_b, {"pool": hot_pool})
    reverse = Edge("aerodrome", "0x" + "31" * 20, token_b, token_a, {"pool": reverse_pool})
    cold = [
        Edge(
            "univ3",
            "0x" + f"{i + 100:040x}",
            "0x" + f"{i + 200:040x}",
            "0x" + f"{i + 300:040x}",
            {"pool": "0x" + f"{i + 400:040x}"},
        )
        for i in range(20)
    ]
    all_edges = [hot, reverse, *cold]
    cache.refresh_edges(all_edges)
    cache._apply_log(
        {
            "address": hot_pool,
            "blockNumber": hex(100),
            "transactionHash": "0xdef",
            "topics": [_SYNC_TOPIC],
            "data": _sync_data(1000, 900),
        }
    )

    candidates, telemetry = cache.candidate_edges(
        all_edges,
        current_block=101,
        max_candidates=12,
        exploration_ratio=0.10,
    )

    assert hot in candidates
    assert reverse in candidates
    assert len(candidates) < len(all_edges)
    assert telemetry["candidate_generation_mode"] == "dirty_subgraph"
    assert telemetry["candidate_edges_pruned"] > 0
    assert telemetry["fresh_dirty_pool_count"] == 1
    assert telemetry["affected_token_count"] == 2
    snapshot = cache.snapshot()
    assert snapshot["candidate_generation_mode"] == "dirty_subgraph"
    assert snapshot["candidate_edges_pruned"] > 0


def test_dirty_hot_subgraph_reserves_family_balanced_exploration():
    cache = PoolStateEventCache(
        chain_name="base",
        chain_id=8453,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
    )
    token_a = "0x" + "aa" * 20
    token_b = "0x" + "bb" * 20
    token_c = "0x" + "cc" * 20
    token_d = "0x" + "dd" * 20
    hot_pool = "0x" + f"{1:040x}"
    hot_edges = [
        Edge(
            "univ3",
            "0x" + "30" * 20,
            token_a,
            token_b,
            {"pool": "0x" + f"{i + 1:040x}"},
        )
        for i in range(40)
    ]
    cold_specs = [
        ("curve", {"pool": "0x" + "41" * 20, "i": 0, "j": 1}),
        ("balancer", {"pool_id": "0x" + "42" * 32}),
        ("aerodrome", {"pool": "0x" + "43" * 20, "factory": "0x" + "44" * 20}),
        ("slipstream", {"pool": "0x" + "45" * 20, "factory": "0x" + "46" * 20, "tick_spacing": 60}),
        ("camelot_algebra", {"pool": "0x" + "47" * 20, "factory": "0x" + "48" * 20, "tick_spacing": 60}),
        ("camelot_v2", {"pool": "0x" + "49" * 20, "factory": "0x" + "4a" * 20}),
        ("constant_product", {"pool": "0x" + "4b" * 20, "factory": "0x" + "4c" * 20, "venue_name": "uniswap_v2"}),
        ("constant_product", {"pool": "0x" + "4d" * 20, "factory": "0x" + "4e" * 20, "venue_name": "sushiswap_v2"}),
    ]
    cold_edges = []
    for family_index, (dex, params) in enumerate(cold_specs):
        router = "0x" + f"{family_index + 80:040x}"
        for pool_index in range(4):
            local = dict(params)
            local["pool"] = "0x" + f"{1000 + family_index * 10 + pool_index:040x}"
            if dex == "balancer":
                local["pool_id"] = "0x" + f"{2000 + family_index * 10 + pool_index:064x}"
            edge = Edge(dex, router, token_c, token_d, local)
            reverse_params = dict(local)
            if dex == "curve":
                reverse_params["i"], reverse_params["j"] = local["j"], local["i"]
            cold_edges.extend([
                edge,
                Edge(dex, router, token_d, token_c, reverse_params),
            ])

    all_edges = [*hot_edges, *cold_edges]
    cache.refresh_edges(all_edges)
    cache._apply_log({
        "address": hot_pool,
        "blockNumber": hex(100),
        "transactionHash": "0xabc",
        "topics": [_SYNC_TOPIC],
        "data": _sync_data(1000, 900),
    })

    candidates, telemetry = cache.candidate_edges(
        all_edges,
        current_block=101,
        max_candidates=32,
        exploration_ratio=0.10,
    )

    families = {
        edge.params.get("venue_name") if edge.dex == "constant_product" else edge.dex
        for edge in candidates
    }
    assert telemetry["candidate_generation_mode"] == "dirty_subgraph"
    assert len(candidates) <= 32
    assert {
        "curve", "balancer", "aerodrome", "slipstream",
        "camelot_algebra", "camelot_v2", "uniswap_v2", "sushiswap_v2",
    }.issubset(families)


def test_pool_event_cache_keeps_full_graph_without_fresh_events():
    cache = PoolStateEventCache(
        chain_name="arbitrum",
        chain_id=42161,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
    )
    edges = [
        Edge(
            "univ3",
            "0x" + f"{i + 500:040x}",
            "0x" + f"{i + 600:040x}",
            "0x" + f"{i + 700:040x}",
            {"pool": "0x" + f"{i + 800:040x}"},
        )
        for i in range(10)
    ]
    cache.refresh_edges(edges)

    candidates, telemetry = cache.candidate_edges(
        edges,
        current_block=100,
        max_candidates=12,
    )

    assert candidates == edges
    assert telemetry["candidate_generation_mode"] == "full_graph"
    assert telemetry["candidate_edges_pruned"] == 0


def test_hot_subgraph_cap_round_robins_families_when_all_edges_are_hot():
    cache = PoolStateEventCache(
        chain_name="base",
        chain_id=8453,
        ws_urls=["wss://example"],
        rpc_urls=["https://example"],
    )
    anchor = "0x" + "11" * 20
    other = "0x" + "90" * 20
    hot_pool = "0x" + f"{1000:040x}"

    # Common-token V3 edges lead the builder output. Every later family touches
    # the dirty anchor too, so the entire graph is hot and the old implementation
    # truncated the list at the cap before the exploration reserve could help.
    hot_edges = [
        Edge(
            "univ3", "0x" + "aa" * 20, anchor, other,
            {"pool": "0x" + f"{1000 + i:040x}", "fee": 3000},
        )
        for i in range(80)
    ]
    hot_edges[0].params["pool"] = hot_pool

    other_families = [
        ("curve", "curve", {"i": 0, "j": 1}),
        ("balancer", "0x" + "bb" * 20, {"pool_id": "0x" + f"{3000:064x}"}),
        ("aerodrome", "0x" + "cc" * 20, {"factory": "0x" + "dd" * 20, "stable": False}),
        ("slipstream", "0x" + "ee" * 20, {"factory": "0x" + "ff" * 20, "tick_spacing": 60}),
        ("camelot_algebra", "0x" + "12" * 20, {"factory": "0x" + "13" * 20, "tick_spacing": 60}),
        ("camelot_v2", "0x" + "14" * 20, {"factory": "0x" + "15" * 20}),
        ("constant_product", "0x" + "16" * 20, {"venue_name": "uniswap_v2", "factory": "0x" + "17" * 20}),
        ("constant_product", "0x" + "18" * 20, {"venue_name": "sushiswap_v2", "factory": "0x" + "19" * 20}),
    ]
    diverse_edges = []
    for family_index, (dex, venue, extra) in enumerate(other_families):
        for pool_index in range(6):
            pool = "0x" + f"{4000 + family_index * 10 + pool_index:040x}"
            params = {**extra, "pool": pool}
            if dex == "balancer":
                params["pool_address"] = pool
                params["pool_id"] = "0x" + f"{5000 + family_index * 10 + pool_index:064x}"
            if dex == "curve":
                venue = pool
            token_out = "0x" + f"{6000 + family_index * 10 + pool_index:040x}"
            diverse_edges.append(Edge(dex, venue, anchor, token_out, params))
            reverse_params = dict(params)
            if dex == "curve":
                reverse_params["i"], reverse_params["j"] = 1, 0
            diverse_edges.append(Edge(dex, venue, token_out, anchor, reverse_params))

    edges = [*hot_edges, *diverse_edges]
    cache.refresh_edges(edges)
    cache._apply_log({
        "address": hot_pool,
        "blockNumber": hex(100),
        "transactionHash": "0xhot",
        "topics": [_SYNC_TOPIC],
        "data": _sync_data(1000, 900),
    })

    candidates, telemetry = cache.candidate_edges(
        edges,
        current_block=101,
        max_candidates=32,
        exploration_ratio=0.10,
    )

    families = {
        cache._edge_family_name(edge)
        for edge in candidates
    }
    expected_families = {
        "univ3", "curve", "balancer", "aerodrome", "slipstream",
        "camelot_algebra", "camelot_v2", "uniswap_v2", "sushiswap_v2",
    }
    assert len(candidates) == 32
    assert expected_families.issubset(families)
    assert telemetry["candidate_generation_mode"] == "dirty_subgraph"
    assert telemetry["hot_subgraph_edge_count"] == len(edges)
    assert telemetry["exploration_edge_count"] == 0
    assert telemetry["family_fair_selection"] is True
    assert expected_families.issubset(set(telemetry["candidate_edges_by_family"]))
    assert expected_families.issubset(set(telemetry["hot_selected_edges_by_family"]))

    # The public scanner payload reads snapshot(), not the transient return value.
    # Verify the family-selection evidence is wired through that boundary too.
    snapshot = cache.snapshot()
    assert snapshot["family_fair_selection"] is True
    assert snapshot["candidate_edges_by_family"] == telemetry["candidate_edges_by_family"]
    assert snapshot["hot_selected_edges_by_family"] == telemetry["hot_selected_edges_by_family"]
    assert snapshot["exploration_edges_by_family"] == telemetry["exploration_edges_by_family"]
