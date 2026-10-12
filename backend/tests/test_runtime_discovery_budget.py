from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.discovery import (
    DiscoveredAerodrome,
    DiscoveredConstantProduct,
    DiscoveryManager,
)
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    RuntimePrimaryScanFacade,
    _discovered_pool_count,
)


@pytest.mark.asyncio
async def test_discovery_timeout_falls_back_to_persisted_universe(monkeypatch):
    monkeypatch.setenv("VICTOR_DISCOVERY_TIMEOUT_S", "0.25")

    class Discovery:
        def v3_pairs(self):
            return [{"pool": "cached-v3"}]

        def curve_pools(self):
            return [{"pool": "cached-curve"}]

        def balancer_pools(self):
            return [{"pool": "cached-balancer"}]

        async def maybe_discover_univ3(self, rpc, cfg, block_number):
            await asyncio.sleep(1.0)
            return [{"pool": "fresh-v3"}]

        async def maybe_discover_venues(self, rpc, cfg, block_number):
            return {
                "curve": [{"pool": "fresh-curve"}],
                "balancer": [{"pool": "fresh-balancer"}],
            }

    runtime = RuntimePrimaryScanFacade()
    runtime._discovery = Discovery()
    runtime.cfg = SimpleNamespace()

    result = await runtime._build_discovery_context(
        object(),
        current_block=123,
    )

    assert result["v3_pairs"] == [{"pool": "cached-v3"}]
    assert result["curve_pools"] == [{"pool": "fresh-curve"}]
    assert result["balancer_pools"] == [{"pool": "fresh-balancer"}]

    runtime_meta = result["runtime"]
    assert runtime_meta["budget_timeout_s"] == 0.25
    assert runtime_meta["used_persisted_fallback"] is True
    assert runtime_meta["stages"][0]["stage"] == "univ3"
    assert runtime_meta["stages"][0]["status"] == "timed_out"
    assert runtime_meta["stages"][1]["status"] == "completed"


@pytest.mark.asyncio
async def test_discovery_fast_path_keeps_fresh_universe(monkeypatch):
    monkeypatch.setenv("VICTOR_DISCOVERY_TIMEOUT_S", "0.5")

    class Discovery:
        def v3_pairs(self):
            return [{"pool": "cached-v3"}]

        def curve_pools(self):
            return [{"pool": "cached-curve"}]

        def balancer_pools(self):
            return [{"pool": "cached-balancer"}]

        async def maybe_discover_univ3(self, rpc, cfg, block_number):
            return [{"pool": "fresh-v3"}]

        async def maybe_discover_venues(self, rpc, cfg, block_number):
            return {
                "curve": [{"pool": "fresh-curve"}],
                "balancer": [{"pool": "fresh-balancer"}],
            }

    runtime = RuntimePrimaryScanFacade()
    runtime._discovery = Discovery()
    runtime.cfg = SimpleNamespace()

    result = await runtime._build_discovery_context(
        object(),
        current_block=123,
    )

    assert result["v3_pairs"] == [{"pool": "fresh-v3"}]
    assert result["curve_pools"] == [{"pool": "fresh-curve"}]
    assert result["balancer_pools"] == [{"pool": "fresh-balancer"}]
    assert result["runtime"]["used_persisted_fallback"] is False
    assert all(
        stage["status"] == "completed"
        for stage in result["runtime"]["stages"]
    )


@pytest.mark.asyncio
async def test_venue_discovery_isolates_slow_and_failed_adapters(monkeypatch, tmp_path):
    monkeypatch.setenv("VICTOR_DISCOVERY_TIMEOUT_S", "0.25")
    manager = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            enable_venue_discovery=True,
            discovery_interval_blocks=40,
        ),
        flags=SimpleNamespace(enable_discovery=True),
    )
    calls = {"curve": 0}

    async def slow_curve(rpc, config, block_number):
        calls["curve"] += 1
        await asyncio.sleep(1.0)
        return False

    async def failed_balancer(rpc, config, block_number):
        raise RuntimeError("provider unavailable")

    async def add_aerodrome(rpc, config, block_number):
        manager._aerodrome["verified-pool"] = DiscoveredAerodrome(
            "0xpool", "0xtoken-a", "0xtoken-b", False, "0xfactory",
            int(block_number), int(block_number),
        )
        return True

    async def no_change(rpc, config, block_number):
        return False

    async def no_constant_product(rpc, config, block_number):
        return manager.constant_product_pools()

    monkeypatch.setattr(manager, "_discover_curve", slow_curve)
    monkeypatch.setattr(manager, "_discover_balancer", failed_balancer)
    monkeypatch.setattr(manager, "_discover_aerodrome", add_aerodrome)
    monkeypatch.setattr(manager, "_discover_slipstream", no_change)
    monkeypatch.setattr(manager, "_discover_camelot_algebra", no_change)
    monkeypatch.setattr(manager, "_discover_camelot_v2", no_change)
    monkeypatch.setattr(manager, "maybe_discover_constant_product", no_constant_product)

    result = await asyncio.wait_for(
        manager.maybe_discover_venues(object(), cfg, block_number=100),
        timeout=1.0,
    )
    by_name = {
        row["stage"]: row
        for row in manager._last_venue_discovery_telemetry["stages"]
    }

    assert by_name["curve"]["status"] == "timed_out"
    assert by_name["balancer"]["status"] == "failed"
    assert by_name["aerodrome"]["status"] == "completed"
    assert len(result["aerodrome"]) == 1
    assert "constant_product" in result
    assert manager._last_curve_run_block == 100

    # A timed-out historical scan is cooled down, not repeated every block.
    second = await asyncio.wait_for(
        manager.maybe_discover_venues(object(), cfg, block_number=101),
        timeout=1.0,
    )
    second_stages = {
        row["stage"]: row
        for row in manager._last_venue_discovery_telemetry["stages"]
    }
    assert second_stages["curve"]["status"] == "skipped_interval"
    assert calls["curve"] == 1
    assert len(second["aerodrome"]) == 1


@pytest.mark.asyncio
async def test_disabled_venue_discovery_preserves_constant_product_pools(tmp_path):
    manager = DiscoveryManager(chain_name="ethereum", data_dir=str(tmp_path))
    pool = DiscoveredConstantProduct(
        pool="0xpool",
        token_in="0xtoken-a",
        token_out="0xtoken-b",
        factory="0xfactory",
        router="0xrouter",
        venue_name="sushiswap_v2",
        first_seen_block=10,
        last_seen_block=20,
    )
    manager._constant_product["persisted-pool"] = pool
    cfg = SimpleNamespace(
        chain=SimpleNamespace(enable_venue_discovery=False),
        flags=SimpleNamespace(enable_discovery=False),
    )

    result = await manager.maybe_discover_venues(object(), cfg, block_number=21)

    assert result["constant_product"] == [pool.to_pool()]
    assert manager._last_venue_discovery_telemetry["enabled"] is False


def test_discovered_pool_count_includes_all_venue_families():
    assert _discovered_pool_count({
        "v3_pairs": [{"pool": "v3"}],
        "curve_pools": [{"pool": "curve"}],
        "balancer_pools": [{"pool": "balancer"}],
        "aerodrome_pools": [{"pool": "aerodrome"}],
        "slipstream_pools": [{"pool": "slipstream"}],
        "camelot_algebra_pools": [{"pool": "camelot-algebra"}],
        "camelot_v2_pools": [{"pool": "camelot-v2"}],
        "constant_product_pools": [{"pool": "cp-1"}, {"pool": "cp-2"}],
    }) == 9


