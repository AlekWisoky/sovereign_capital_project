from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_caq_kds_facade as caq_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_caq_kds_facade import RuntimeCaqKdsFacade

EXTRACTED_METHODS = {
    '_dex_scan_margin_ratios',
    '_publish_dex_scan_summary',
}


class _Runtime(RuntimeCaqKdsFacade):
    def __init__(self):
        self.fail_rate = 0.15

    def _route_fail_rate(self):
        return float(self.fail_rate)


def test_runtime_bundle_inherits_caq_kds_facade():
    assert issubclass(RuntimeBundle, RuntimeCaqKdsFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_dex_scan_margin_ratios_preserve_legacy_fallbacks():
    runtime = _Runtime()
    opps = [
        SimpleNamespace(meta={'margin_ratio': 0.12}),
        SimpleNamespace(meta={'brain': {'margin_ratio': '0.34'}}),
        SimpleNamespace(meta={'brain': {'margin_ratio': object()}}),
        SimpleNamespace(meta=None),
    ]

    assert runtime._dex_scan_margin_ratios(opps=opps) == [0.12, 0.34]


def test_publish_dex_scan_summary_updates_bus(monkeypatch):
    runtime = _Runtime()
    calls = []
    monkeypatch.setattr(caq_mod, 'BUS', SimpleNamespace(update=lambda name, payload: calls.append((name, payload))))

    ok = runtime._publish_dex_scan_summary(
        opps=[
            SimpleNamespace(meta={'margin_ratio': 0.1}),
            SimpleNamespace(meta={'brain': {'margin_ratio': 0.3}}),
        ]
    )

    assert ok is True
    assert calls == [
        (
            'dex',
            {
                'opps_per_block': 2.0,
                'avg_margin_ratio': 0.2,
                'route_fail_rate': 0.15,
            },
        )
    ]


def test_publish_dex_scan_summary_swallows_expected_local_failure(monkeypatch):
    runtime = _Runtime()

    def _boom(_name, _payload):
        raise ValueError('bad dex summary state')

    monkeypatch.setattr(caq_mod, 'BUS', SimpleNamespace(update=_boom))

    ok = runtime._publish_dex_scan_summary(opps=[SimpleNamespace(meta={'margin_ratio': 0.2})])

    assert ok is False


def test_publish_dex_scan_summary_does_not_swallow_unexpected_bug(monkeypatch):
    runtime = _Runtime()

    def _boom(_name, _payload):
        raise ZeroDivisionError('unexpected dex summary bug')

    monkeypatch.setattr(caq_mod, 'BUS', SimpleNamespace(update=_boom))

    with pytest.raises(ZeroDivisionError, match='unexpected dex summary bug'):
        runtime._publish_dex_scan_summary(opps=[SimpleNamespace(meta={'margin_ratio': 0.2})])
