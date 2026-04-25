from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_primary_scan_facade as scan_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade

EXTRACTED_METHODS = {
    '_discover_extra_v3_pairs',
    '_scan_primary_opportunities',
}


class _Discovery:
    def __init__(self, pairs=None):
        self.pairs = list(pairs or [])
        self.calls = []

    async def maybe_discover_univ3(self, rpc, cfg, block_number):
        self.calls.append({'rpc': rpc, 'cfg': cfg, 'block_number': block_number})
        return list(self.pairs)


class _Runtime(RuntimePrimaryScanFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            flags=SimpleNamespace(enable_two_leg_loops=True, enable_three_leg_loops=False, enable_v3_triangular=False),
            safety=SimpleNamespace(slippage_bps=75),
        )
        self.cache = object()
        self._discovery = _Discovery(['v3-a', 'v3-b'])


def _opp(profit: int, *, expected: int | None = None):
    return SimpleNamespace(
        meta={'profit_after_gas_estimate_wei': profit} if profit >= 0 else {},
        expected_profit_raw=expected if expected is not None else max(0, profit),
    )


def test_runtime_bundle_inherits_primary_scan_facade():
    assert issubclass(RuntimeBundle, RuntimePrimaryScanFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_scan_primary_opportunities_preserves_discovery_scan_sort_and_truncate(monkeypatch):
    runtime = _Runtime()
    calls = {'two': None, 'three': None}

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        calls['two'] = {'rpc': rpc, 'cfg': cfg, 'cache': cache, 'block_number': block_number, **kwargs}
        return [_opp(5), _opp(20), _opp(-1, expected=11)]

    async def fake_three(rpc, cfg, cache, block_number, **kwargs):
        calls['three'] = {'rpc': rpc, 'cfg': cfg, 'cache': cache, 'block_number': block_number, **kwargs}
        return [_opp(15)]

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', fake_two)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', fake_three)
    runtime.cfg.flags.enable_three_leg_loops = True

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=10)

    assert runtime._discovery.calls[0]['block_number'] == 321
    assert calls['two']['amount_in'] == 10
    assert calls['two']['extra_v3_pairs'] == ['v3-a', 'v3-b']
    assert calls['three']['extra_v3_pairs'] == ['v3-a', 'v3-b']
    assert [int((o.meta or {}).get('profit_after_gas_estimate_wei') or o.expected_profit_raw) for o in opps] == [20, 15, 11, 5]


@pytest.mark.asyncio
async def test_scan_primary_opportunities_returns_empty_when_amount_in_nonpositive(monkeypatch):
    runtime = _Runtime()

    async def unexpected(*args, **kwargs):
        raise AssertionError('scan should not run')

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', unexpected)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', unexpected)

    opps = await runtime._scan_primary_opportunities(object(), current_block=1, amount_in=0)

    assert opps == []
    assert runtime._discovery.calls == []


@pytest.mark.asyncio
async def test_scan_primary_opportunities_does_not_swallow_unexpected_scan_bug(monkeypatch):
    runtime = _Runtime()

    async def boom(*args, **kwargs):
        raise KeyError('unexpected scan bug')

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', boom)

    with pytest.raises(KeyError, match='unexpected scan bug'):
        await runtime._scan_primary_opportunities(object(), current_block=7, amount_in=10)



@pytest.mark.asyncio
async def test_scan_primary_opportunities_prefers_verified_after_cost_truth_over_gross_estimates(monkeypatch):
    runtime = _Runtime()

    async def fake_two(rpc, cfg, cache, block_number, **kwargs):
        return [
            SimpleNamespace(
                id='gross-only',
                route_id='route-gross',
                meta={'profit_after_gas_estimate_wei': '500'},
                expected_profit_raw='900',
            ),
            SimpleNamespace(
                id='net-verified',
                route_id='route-net',
                meta={
                    'profit_after_gas_estimate_wei': '10',
                    'profit_after_costs': '250',
                    'safety': {'profit_after_costs_wei': '250'},
                },
                expected_profit_raw='100',
            ),
        ]

    async def fake_three(rpc, cfg, cache, block_number, **kwargs):
        return []

    monkeypatch.setattr(scan_mod, 'find_two_leg_opportunities', fake_two)
    monkeypatch.setattr(scan_mod, 'find_three_leg_opportunities', fake_three)

    opps = await runtime._scan_primary_opportunities(object(), current_block=321, amount_in=10)

    assert [getattr(o, 'id', '') for o in opps] == ['net-verified', 'gross-only']
