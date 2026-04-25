import ast
from pathlib import Path

import pytest

from victor_ai_bot.aqe.arbitrage.models import ArbitrageOpportunity, MarketQuote
from victor_ai_bot.aqe.arbitrage.runtime import ArbitrageRuntime
from victor_ai_bot.config import ArbitrageConfig

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'aqe' / 'arbitrage'


class DummyAdapter:
    name = 'demo'
    product = 'spot'

    def __init__(self, *, quote=None, orderbook=None):
        self._quote = quote
        self._orderbook = orderbook

    async def fetch_quote(self, *, symbol: str):
        if isinstance(self._quote, BaseException):
            raise self._quote
        return self._quote

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10):
        if isinstance(self._orderbook, BaseException):
            raise self._orderbook
        return self._orderbook

    async def close(self):
        return None


def _opp() -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        arb_type='spot_futures',
        symbol='BTCUSDT',
        buy_venue='buy',
        sell_venue='sell',
        buy_product='spot',
        sell_product='futures',
        entry_buy=100.0,
        entry_sell=101.0,
        spread_pct=1.0,
        est_net_profit_usd=12.0,
        liquidity_depth_usd=5000.0,
        pair_lifetime_sec=1.0,
        confidence=0.9,
        created_at_ms=1,
    )


@pytest.mark.asyncio
async def test_bus_update_value_error_is_safely_ignored(monkeypatch):
    runtime = ArbitrageRuntime(ArbitrageConfig(enabled=True, pairs=['BTCUSDT']))
    runtime._adapters = [DummyAdapter(quote=MarketQuote('demo', 'spot', 'BTCUSDT', 100.0, 101.0, 1))]
    monkeypatch.setattr(runtime._screener, 'screen', lambda **kwargs: [_opp()])
    monkeypatch.setattr('victor_ai_bot.aqe.arbitrage.runtime.BUS.update', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('ignore me')))

    await runtime._scan_once()

    assert runtime.state()['opp_count'] == 1


@pytest.mark.asyncio
async def test_bus_update_programmer_bug_is_not_swallowed(monkeypatch):
    runtime = ArbitrageRuntime(ArbitrageConfig(enabled=True, pairs=['BTCUSDT']))
    runtime._adapters = [DummyAdapter(quote=MarketQuote('demo', 'spot', 'BTCUSDT', 100.0, 101.0, 1))]
    monkeypatch.setattr(runtime._screener, 'screen', lambda **kwargs: [_opp()])
    monkeypatch.setattr('victor_ai_bot.aqe.arbitrage.runtime.BUS.update', lambda *args, **kwargs: (_ for _ in ()).throw(NameError('bus bug')))

    with pytest.raises(NameError):
        await runtime._scan_once()


@pytest.mark.asyncio
async def test_invalid_adapter_config_is_recorded_not_raised():
    runtime = ArbitrageRuntime(
        ArbitrageConfig(enabled=True, venues=[{'name': 'binance', 'product': 'spot', 'fee_bps': 'oops'}])
    )

    await runtime._init_adapters()

    assert runtime._adapters == []
    assert any(err.startswith('adapter_init_failed:ValueError:') for err in runtime._errors)


@pytest.mark.asyncio
async def test_quote_task_failures_are_recorded_and_scan_continues(monkeypatch):
    runtime = ArbitrageRuntime(ArbitrageConfig(enabled=True, pairs=['BTCUSDT']))
    runtime._adapters = [DummyAdapter(quote=ValueError('quote failed'))]
    monkeypatch.setattr(runtime._screener, 'screen', lambda **kwargs: [])

    await runtime._scan_once()

    assert any(err.startswith('quote_failed:BTCUSDT:ValueError:') for err in runtime._errors)
    assert runtime.state()['opp_count'] == 0


def test_arbitrage_runtime_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'runtime.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            broad.append('bare except')
            continue
        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
            broad.append('except Exception')
    assert broad == []
