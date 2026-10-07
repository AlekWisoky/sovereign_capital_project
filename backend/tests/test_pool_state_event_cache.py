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
        for i in range(4)
    ]
    cache.refresh_edges(edges)

    addresses = cache._subscription_addresses()

    assert len(addresses) == 16
    assert cache.snapshot()["subscription_truncated"] is True
