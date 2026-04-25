from __future__ import annotations

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_feature_bus_facade import RuntimeFeatureBusFacade

EXTRACTED_METHODS = {
    '_refresh_unified_feature_bus',
}


class _FeatureBus:
    def __init__(self):
        self.updated = 0
        self.snapshots = 0

    def update_from_bus(self):
        self.updated += 1

    def snapshot(self):
        self.snapshots += 1
        return {'feature_alpha': 1.25, 'feature_beta': 2.5}


class _FeatureBusValueError(_FeatureBus):
    def update_from_bus(self):
        raise ValueError('bad feature-bus state')


class _FeatureBusKeyError(_FeatureBus):
    def snapshot(self):
        raise KeyError('unexpected feature-bus bug')


class _Runtime(RuntimeFeatureBusFacade):
    def __init__(self, feature_bus=None):
        self._feature_bus = feature_bus


def test_runtime_bundle_inherits_feature_bus_facade():
    assert issubclass(RuntimeBundle, RuntimeFeatureBusFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_refresh_unified_feature_bus_updates_and_publishes():
    runtime = _Runtime(feature_bus=_FeatureBus())

    ok = runtime._refresh_unified_feature_bus()

    assert ok is True
    assert runtime._feature_bus.updated == 1
    assert runtime._feature_bus.snapshots == 1


def test_refresh_unified_feature_bus_noops_when_bus_missing():
    runtime = _Runtime(feature_bus=None)

    ok = runtime._refresh_unified_feature_bus()

    assert ok is False


def test_refresh_unified_feature_bus_swallows_expected_local_failure():
    runtime = _Runtime(feature_bus=_FeatureBusValueError())

    ok = runtime._refresh_unified_feature_bus()

    assert ok is False


def test_refresh_unified_feature_bus_does_not_swallow_unexpected_bug():
    runtime = _Runtime(feature_bus=_FeatureBusKeyError())

    with pytest.raises(KeyError, match='unexpected feature-bus bug'):
        runtime._refresh_unified_feature_bus()
