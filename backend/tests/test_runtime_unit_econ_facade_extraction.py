from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_unit_econ_facade as unit_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_unit_econ_facade import RuntimeUnitEconFacade

EXTRACTED_METHODS = {
    '_unit_econ_topn',
    '_annotate_single_unit_econ',
    '_annotate_unit_economics',
}


class _Runtime(RuntimeUnitEconFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name='ethereum'),
            execution=SimpleNamespace(
                usd_accounting_enabled=True,
                usd_stable_preference='usdc',
            ),
        )
        self.cache = object()


def _opp(*, token='WETH', profit=5000, gas='200', meta=None):
    return SimpleNamespace(
        route=SimpleNamespace(legs=[SimpleNamespace(token_in=token)]),
        expected_profit_raw=profit,
        meta=(meta if meta is not None else {'gas_cost_estimate_wei': gas}),
    )


def test_runtime_bundle_inherits_unit_econ_facade():
    assert issubclass(RuntimeBundle, RuntimeUnitEconFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_annotate_unit_economics_enriches_topn(monkeypatch):
    runtime = _Runtime()
    opps = [
        _opp(meta={'gas_cost_estimate_wei': '50', 'unit_econ': {'preexisting': '1'}}),
        _opp(token='WBTC', profit=7000, gas='80'),
        _opp(token='UNI', profit=9000, gas='100'),
    ]

    async def _gas_token(*args, **kwargs):
        return 100

    async def _token_usd(*args, token, amount_wei, **kwargs):
        return int(amount_wei) * (2 if token == 'WBTC' else 1)

    async def _gas_usd(*args, gas_cost_wei, **kwargs):
        return int(gas_cost_wei) * 3

    monkeypatch.setenv('VICTOR_USD_ACCOUNTING_TOPN', '2')
    monkeypatch.setattr(unit_mod, 'gas_wei_to_token_wei', _gas_token)
    monkeypatch.setattr(unit_mod, 'token_to_usd_micro', _token_usd)
    monkeypatch.setattr(unit_mod, 'gas_wei_to_usd_micro', _gas_usd)
    monkeypatch.setattr(unit_mod, 'format_usd_micro', lambda value: f'USD:{value}')

    ok = asyncio.run(runtime._annotate_unit_economics(opps=opps, rpc=object(), current_block=123))

    assert ok is True
    assert opps[0].expected_profit_usd == 'USD:5000'
    assert opps[0].meta['unit_econ'] == {
        'preexisting': '1',
        'gas_cost_in_profit_token_wei': '100',
        'profit_after_gas_in_profit_token_wei': '4900',
        'expected_profit_usd_micro': '5000',
        'gas_cost_usd_micro': '150',
        'profit_after_gas_usd_micro': '4850',
    }
    assert opps[1].expected_profit_usd == 'USD:14000'
    assert opps[1].meta['unit_econ']['gas_cost_usd_micro'] == '240'
    assert not hasattr(opps[2], 'expected_profit_usd')
    assert 'unit_econ' not in opps[2].meta


def test_annotate_single_unit_econ_swallows_expected_local_failure(monkeypatch):
    runtime = _Runtime()
    bad = _opp()

    async def _gas_token(*args, **kwargs):
        raise ValueError('bad pricing input')

    monkeypatch.setattr(unit_mod, 'gas_wei_to_token_wei', _gas_token)

    ok = asyncio.run(
        runtime._annotate_single_unit_econ(
            rpc=object(),
            opportunity=bad,
            current_block=10,
            preference='usdc',
        )
    )

    assert ok is False


def test_annotate_unit_economics_does_not_swallow_unexpected_bug(monkeypatch):
    runtime = _Runtime()
    opps = [_opp()]

    async def _gas_token(*args, **kwargs):
        return 10

    async def _token_usd(*args, **kwargs):
        raise AssertionError('unexpected pricing bug')

    monkeypatch.setattr(unit_mod, 'gas_wei_to_token_wei', _gas_token)
    monkeypatch.setattr(unit_mod, 'token_to_usd_micro', _token_usd)
    monkeypatch.setattr(unit_mod, 'gas_wei_to_usd_micro', _gas_token)

    with pytest.raises(AssertionError, match='unexpected pricing bug'):
        asyncio.run(runtime._annotate_unit_economics(opps=opps, rpc=object(), current_block=1))
