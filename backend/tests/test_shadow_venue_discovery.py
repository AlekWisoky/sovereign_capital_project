from types import SimpleNamespace

import pytest

from victor_ai_bot.discovery import DiscoveryManager
from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.ethabi import enc_address, enc_uint, selector


def _word(value: int) -> bytes:
    return int(value).to_bytes(32, "big")


def _addr_word(address: str) -> bytes:
    return enc_address(address)


def _fixed_addresses(*addresses: str) -> str:
    return "0x" + b"".join(_addr_word(a) for a in addresses).hex()


def _fixed_uints(*values: int) -> str:
    return "0x" + b"".join(_word(v) for v in values).hex()


def _dynamic_pool_tokens(tokens, balances) -> str:
    # (address[], uint256[], uint256) ABI encoding.
    head = _word(96) + _word(96 + 32 + 32 * len(tokens)) + _word(123)
    token_tail = _word(len(tokens)) + b"".join(_addr_word(t) for t in tokens)
    balance_tail = _word(len(balances)) + b"".join(_word(v) for v in balances)
    return "0x" + (head + token_tail + balance_tail).hex()


class _VenueRpc:
    def __init__(self, *, provider, registry, curve_pool, vault, balancer_pool_id, balancer_pool):
        self.provider = provider
        self.registry = registry
        self.curve_pool = curve_pool
        self.vault = vault
        self.balancer_pool_id = balancer_pool_id
        self.balancer_pool = balancer_pool
        self.calls = []
        self.logs_calls = 0

    async def eth_call(self, to, data, *, block="latest", from_addr=None):
        self.calls.append((to, data))
        sig = data[:10]
        if to == self.provider and sig == "0x" + selector("get_registry()").hex():
            return RpcResult(True, result="0x" + "00" * 12 + self.registry[2:])
        if to == self.registry and sig == "0x" + selector("pool_count()").hex():
            return RpcResult(True, result="0x" + _word(1).hex())
        if to == self.registry and sig == "0x" + selector("pool_list(uint256)").hex():
            return RpcResult(True, result="0x" + "00" * 12 + self.curve_pool[2:])
        if to == self.registry and sig == "0x" + selector("get_coins(address)").hex():
            return RpcResult(True, result=_fixed_addresses(
                "0x" + "00" * 20,
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
                "0x" + "00" * 20,
                "0x" + "00" * 20,
                "0x" + "00" * 20,
                "0x" + "00" * 20,
                "0x" + "00" * 20,
            ))
        if to == self.registry and sig == "0x" + selector("get_balances(address)").hex():
            return RpcResult(True, result=_fixed_uints(0, 10**18, 10**18, 0, 0, 0, 0, 0))
        if to == self.vault and sig == "0x" + selector("getPoolTokens(bytes32)").hex():
            return RpcResult(True, result=_dynamic_pool_tokens(
                [
                    "0x4200000000000000000000000000000000000006",
                    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                ],
                [10**18, 2 * 10**6],
            ))
        return RpcResult(False, error="unexpected_call")

    async def eth_get_logs(self, *, address, from_block, to_block, topics=None):
        self.logs_calls += 1
        return [{
            "topics": [
                "0x3c13bc30b8e878c53fd2a36b679409c073afd75950be43d8858768e956fbc20e",
                self.balancer_pool_id,
                "0x" + "00" * 12 + self.balancer_pool[2:],
            ],
            "data": "0x" + "00" * 32,
        }]


@pytest.mark.asyncio
async def test_bounded_curve_and_balancer_discovery_filters_to_supported_liquid_tokens(tmp_path):
    provider = "0x" + "11" * 20
    registry = "0x" + "22" * 20
    curve_pool = "0x" + "33" * 20
    vault = "0x" + "44" * 20
    balancer_pool = "0x" + "55" * 20
    pool_id = "0x" + "66" * 32
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            enable_venue_discovery=True,
            curve_address_provider=provider,
            balancer_vault=vault,
            token_universe=[
                "0x4200000000000000000000000000000000000006",
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
            ],
            discovery_pool_max_candidates=2,
            discovery_log_window_blocks=100,
        )
    )
    rpc = _VenueRpc(
        provider=provider,
        registry=registry,
        curve_pool=curve_pool,
        vault=vault,
        balancer_pool_id=pool_id,
        balancer_pool=balancer_pool,
    )
    dm = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))

    result = await dm.maybe_discover_venues(rpc, cfg, 1000)

    assert result["curve"]
    expected_curve_tokens = {
        "0x833589fcD6eDb6e08f4c7c32d4f71b54bda02913".lower(),
        "0xfde4c96c8593536e31f229ea8f37b2ad2699bb2".lower(),
    }
    assert any(
        {p["token_in"].lower(), p["token_out"].lower()} == expected_curve_tokens
        for p in result["curve"]
    ), result["curve"]
    assert result["balancer"]
    assert result["balancer"][0]["pool_id"] == pool_id
    assert rpc.logs_calls == 1
