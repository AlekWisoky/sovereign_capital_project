from types import SimpleNamespace

import pytest

from victor_ai_bot.discovery import DiscoveryManager, _SLIPSTREAM_POOL_CREATED_TOPIC
from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.ethabi import enc_address, enc_uint, selector


def _word(value):
    return int(value).to_bytes(32, "big")


class FakeRpc:
    def __init__(self, factory, pool, token0, token1):
        self.factory = factory
        self.pool = pool
        self.token0 = token0
        self.token1 = token1

    async def eth_get_logs(self, **kwargs):
        return [{
            "topics": [
                _SLIPSTREAM_POOL_CREATED_TOPIC,
                "0x" + _word(int(self.token0, 16)).hex(),
                "0x" + _word(int(self.token1, 16)).hex(),
                "0x" + _word(100).hex(),
            ],
            "data": "0x" + _word(int(self.pool, 16)).hex(),
        }]

    async def eth_call(self, to, data, **kwargs):
        sig = data[2:10]
        if to == self.factory and sig == selector("isPool(address)").hex():
            return RpcResult(True, result="0x" + (1).to_bytes(32, "big").hex())
        if to == self.pool and sig == selector("liquidity()").hex():
            return RpcResult(True, result="0x" + (10**18).to_bytes(32, "big").hex())
        return RpcResult(False, error="unexpected")


@pytest.mark.asyncio
async def test_slipstream_discovery_requires_anchor_and_liquidity(tmp_path):
    factory = "0x" + "33" * 20
    pool = "0x" + "44" * 20
    token0 = "0x" + "11" * 20
    token1 = "0x" + "22" * 20
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            slipstream_factories=[factory],
            token_universe=[token0],
            discovery_interval_blocks=1,
            discovery_log_window_blocks=100,
            discovery_pool_max_candidates=8,
        ),
        flags=SimpleNamespace(enable_discovery=True),
    )
    dm = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    rows = await dm.maybe_discover_slipstream(FakeRpc(factory, pool, token0, token1), cfg, 100)
    assert len(rows) == 1
    assert rows[0]["tick_spacing"] == 100
    assert rows[0]["factory"].lower() == factory.lower()
