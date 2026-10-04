from types import SimpleNamespace

import pytest

from victor_ai_bot.discovery import DiscoveryManager, _CAMELOT_ALGEBRA_POOL_TOPIC
from victor_ai_bot.ethabi import selector


class FakeRpc:
    def __init__(self, factory, pool, token0, token1):
        self.factory = factory
        self.pool = pool
        self.token0 = token0
        self.token1 = token1

    async def eth_get_logs(self, **kwargs):
        assert kwargs["address"] == self.factory
        return [{
            "topics": [
                _CAMELOT_ALGEBRA_POOL_TOPIC,
                "0x" + "00" * 12 + self.token0[2:],
                "0x" + "00" * 12 + self.token1[2:],
            ],
            "data": "0x" + "00" * 12 + self.pool[2:],
        }]

    async def eth_call(self, address, data, block="latest"):
        selectors = {selector("tickSpacing()").hex(): 60, selector("liquidity()").hex(): 10**18}
        if address == self.pool and data[2:10] in selectors:
            return SimpleNamespace(ok=True, result=hex(selectors[data[2:10]]))
        return SimpleNamespace(ok=False, result="0x")


@pytest.mark.asyncio
async def test_camelot_algebra_discovery_requires_anchor_and_liquidity(tmp_path):
    factory = "0x00000000000000000000000000000000000000f1"
    pool = "0x00000000000000000000000000000000000000f2"
    token0 = "0x0000000000000000000000000000000000000001"
    token1 = "0x0000000000000000000000000000000000000002"
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            camelot_algebra_factory=factory,
            token_universe=[token0],
            discovery_interval_blocks=1,
            discovery_log_window_blocks=100,
            discovery_pool_max_candidates=10,
        ),
        flags=SimpleNamespace(enable_discovery=True),
    )
    dm = DiscoveryManager(chain_name="arbitrum", data_dir=str(tmp_path))
    rows = await dm.maybe_discover_camelot_algebra(FakeRpc(factory, pool, token0, token1), cfg, 100)
    assert len(rows) == 1
    assert rows[0]["tick_spacing"] == 60
    assert rows[0]["factory"].lower() == factory.lower()
