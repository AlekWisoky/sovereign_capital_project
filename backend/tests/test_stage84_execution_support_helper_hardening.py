from __future__ import annotations

import pytest

from victor_ai_bot.execution_capture.aging import aging_factor, half_life_ms
from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.usd_pricing import format_usd_micro
from victor_ai_bot.gas import suggest_gas


class _Presets:
    standard_max_fee_gwei = 10
    standard_priority_fee_gwei = 1
    fast_max_fee_gwei = 20
    fast_priority_fee_gwei = 2
    instant_max_fee_gwei = 30
    instant_priority_fee_gwei = 3


class _BadInt:
    def __int__(self):
        raise TypeError('bad-int')


class _ExplodingInt:
    def __int__(self):
        raise RuntimeError('boom-int')


class _ExplodingFloatPath:
    def __int__(self):
        raise RuntimeError('boom-int')


class _RpcBatchSafe:
    async def batch(self, reqs):
        return [RpcResult(ok=True, result={'reward': [['0xz']]}), RpcResult(ok=True, result='0xz')]

    async def fee_history_tip(self):
        return None

    async def gas_price(self):
        return None


class _RpcBatchBug:
    async def batch(self, reqs):
        raise RuntimeError('boom-batch')

    async def fee_history_tip(self):
        return None

    async def gas_price(self):
        return None


def test_half_life_ms_expected_bad_override_degrades_safely():
    assert half_life_ms('flashloan_atomic', overrides={'flashloan_atomic': _BadInt()}) == 1800


def test_half_life_ms_unexpected_override_bug_not_swallowed():
    with pytest.raises(RuntimeError):
        half_life_ms('flashloan_atomic', overrides={'flashloan_atomic': _ExplodingInt()})


def test_format_usd_micro_expected_bad_input_degrades_safely():
    assert format_usd_micro(_BadInt()) == '0'


def test_format_usd_micro_unexpected_bug_not_swallowed():
    with pytest.raises(RuntimeError):
        format_usd_micro(_ExplodingFloatPath())


@pytest.mark.asyncio
async def test_suggest_gas_expected_batch_parse_failures_degrade_safely():
    max_fee, prio = await suggest_gas(_RpcBatchSafe(), mode='standard', presets=_Presets())
    assert max_fee == 10 * 10**9
    assert prio == 1 * 10**9


@pytest.mark.asyncio
async def test_suggest_gas_unexpected_batch_bug_not_swallowed():
    with pytest.raises(RuntimeError):
        await suggest_gas(_RpcBatchBug(), mode='standard', presets=_Presets())


def test_aging_factor_still_orders_longer_half_life_above_shorter_one():
    assert aging_factor(route_family='funding_arb', age_ms=1000) > aging_factor(route_family='flashloan_atomic', age_ms=1000)
