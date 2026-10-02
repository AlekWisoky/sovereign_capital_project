from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services.runtime_primary_scan_facade import (
    RuntimePrimaryScanFacade,
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
