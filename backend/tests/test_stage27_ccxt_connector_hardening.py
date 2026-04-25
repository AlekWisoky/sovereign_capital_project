from __future__ import annotations

import sys
import types

import pytest

from victor_ai_bot.aqe.connectors.exchange import CCXTConnector


class _FakeExchangeError(Exception):
    pass


class _BugError(ZeroDivisionError):
    pass


def _install_fake_ccxt(monkeypatch, exchange_cls):
    mod = types.ModuleType("ccxt")
    mod.fakeex = exchange_cls
    monkeypatch.setitem(sys.modules, "ccxt", mod)


class _SafeExchange:
    __module__ = "safe_ccxt_module"

    def __init__(self, kwargs):
        self.kwargs = kwargs

    def cancel_order(self, order_id):
        raise _FakeExchangeError("cancel failed")

    def fetch_balance(self):
        return {"free": {"USDT": "1.25", "BAD": object()}}

    def fetch_positions(self):
        raise _FakeExchangeError("positions unavailable")


class _BuggyExchange:
    __module__ = "buggy_ccxt_module"

    def __init__(self, kwargs):
        self.kwargs = kwargs

    def cancel_order(self, order_id):
        raise _BugError("unexpected bug")

    def fetch_balance(self):
        raise _BugError("unexpected bug")

    def fetch_positions(self):
        raise _BugError("unexpected bug")


@pytest.fixture(autouse=True)
def _install_aux_modules(monkeypatch):
    safe_mod = types.ModuleType("safe_ccxt_module")
    safe_mod.BaseError = _FakeExchangeError
    safe_mod.ExchangeError = _FakeExchangeError
    safe_mod.NetworkError = _FakeExchangeError
    safe_mod.NotSupported = _FakeExchangeError
    buggy_mod = types.ModuleType("buggy_ccxt_module")
    monkeypatch.setitem(sys.modules, "safe_ccxt_module", safe_mod)
    monkeypatch.setitem(sys.modules, "buggy_ccxt_module", buggy_mod)


def test_connect_import_error_becomes_runtime_error(monkeypatch):
    monkeypatch.delitem(sys.modules, "ccxt", raising=False)
    connector = CCXTConnector(exchange_id="fakeex")
    with pytest.raises(RuntimeError, match="ccxt not installed"):
        connector.connect()


def test_safe_ccxt_operation_errors_degrade_non_fatally(monkeypatch):
    _install_fake_ccxt(monkeypatch, _SafeExchange)
    connector = CCXTConnector(exchange_id="fakeex", enable_trading=True)
    connector.connect()
    assert connector.cancel_order("abc") is False
    assert connector.get_balance() == {"USDT": 1.25}
    assert connector.get_positions() == []


def test_unexpected_ccxt_bugs_are_not_swallowed(monkeypatch):
    _install_fake_ccxt(monkeypatch, _BuggyExchange)
    connector = CCXTConnector(exchange_id="fakeex", enable_trading=True)
    connector.connect()
    with pytest.raises(_BugError):
        connector.cancel_order("abc")
    with pytest.raises(_BugError):
        connector.get_balance()
    with pytest.raises(_BugError):
        connector.get_positions()


def test_connect_init_shape_errors_become_runtime_error(monkeypatch):
    class _BadInitExchange:
        def __init__(self, kwargs):
            raise TypeError("bad init")

    _install_fake_ccxt(monkeypatch, _BadInitExchange)
    connector = CCXTConnector(exchange_id="fakeex", enable_trading=True)
    with pytest.raises(RuntimeError, match="connector init failed"):
        connector.connect()
