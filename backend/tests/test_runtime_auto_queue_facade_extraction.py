from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_auto_queue_facade import RuntimeAutoQueueFacade

EXTRACTED_METHODS = {
    '_refresh_auto_queue_from_decision',
}


class _Runtime(RuntimeAutoQueueFacade):
    def __init__(self):
        self._auto_queue = []
        self._auto_queue_block = 0


def test_runtime_bundle_inherits_auto_queue_facade():
    assert issubclass(RuntimeBundle, RuntimeAutoQueueFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_refresh_auto_queue_from_decision_updates_queue_and_block():
    runtime = _Runtime()
    decision = SimpleNamespace(portfolio=['opp-2', 'opp-1'])

    refreshed = runtime._refresh_auto_queue_from_decision(decision, current_block=321)

    assert refreshed is True
    assert runtime._auto_queue == ['opp-2', 'opp-1']
    assert runtime._auto_queue_block == 321


def test_refresh_auto_queue_from_decision_skips_missing_portfolio():
    runtime = _Runtime()
    runtime._auto_queue = ['existing']
    runtime._auto_queue_block = 111

    refreshed = runtime._refresh_auto_queue_from_decision(SimpleNamespace(), current_block=222)

    assert refreshed is False
    assert runtime._auto_queue == ['existing']
    assert runtime._auto_queue_block == 111


def test_refresh_auto_queue_from_decision_is_operator_safe_on_bad_portfolio():
    runtime = _Runtime()
    runtime._auto_queue = ['existing']
    runtime._auto_queue_block = 111
    decision = SimpleNamespace(portfolio=object())

    refreshed = runtime._refresh_auto_queue_from_decision(decision, current_block=222)

    assert refreshed is False
    assert runtime._auto_queue == ['existing']
    assert runtime._auto_queue_block == 111
