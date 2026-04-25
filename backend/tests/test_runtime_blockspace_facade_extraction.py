from __future__ import annotations

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_blockspace_facade import RuntimeBlockspaceFacade

EXTRACTED_METHODS = {
    '_observe_blockspace',
}


class _Blockspace:
    def __init__(self):
        self.calls = []

    def observe_block(self, **kwargs):
        self.calls.append(kwargs)


class _LegacyBlockspace:
    def __init__(self):
        self.calls = []

    def observe_block(self, *, block_number: int, basefee_gwei: float, priority_gwei: float, pending_txs: int, mev_risk: float = 0.0):
        self.calls.append(
            {
                'block_number': block_number,
                'basefee_gwei': basefee_gwei,
                'priority_gwei': priority_gwei,
                'pending_txs': pending_txs,
                'mev_risk': mev_risk,
            }
        )


class _BlockspaceValueError(_Blockspace):
    def observe_block(self, **kwargs):
        raise ValueError('bad blockspace state')


class _BlockspaceKeyError(_Blockspace):
    def observe_block(self, **kwargs):
        raise KeyError('unexpected blockspace bug')


class _Runtime(RuntimeBlockspaceFacade):
    def __init__(self, blockspace=None):
        self._blockspace = blockspace


def test_runtime_bundle_inherits_blockspace_facade():
    assert issubclass(RuntimeBundle, RuntimeBlockspaceFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_observe_blockspace_uses_canonical_block_kwarg():
    runtime = _Runtime(blockspace=_Blockspace())

    ok = runtime._observe_blockspace(
        block_number=123,
        basefee_gwei=42.5,
        priority_gwei=1.5,
        pending_txs=7,
        mev_risk=0.2,
    )

    assert ok is True
    assert runtime._blockspace.calls == [
        {
            'block': 123,
            'basefee_gwei': 42.5,
            'priority_gwei': 1.5,
            'pending_txs': 7,
            'mev_risk': 0.2,
        }
    ]


def test_observe_blockspace_preserves_legacy_block_number_compatibility():
    runtime = _Runtime(blockspace=_LegacyBlockspace())

    ok = runtime._observe_blockspace(
        block_number=456,
        basefee_gwei=50.0,
        priority_gwei=2.0,
        pending_txs=11,
        mev_risk=0.4,
    )

    assert ok is True
    assert runtime._blockspace.calls == [
        {
            'block_number': 456,
            'basefee_gwei': 50.0,
            'priority_gwei': 2.0,
            'pending_txs': 11,
            'mev_risk': 0.4,
        }
    ]


def test_observe_blockspace_noops_when_blockspace_missing():
    runtime = _Runtime(blockspace=None)

    ok = runtime._observe_blockspace(
        block_number=1,
        basefee_gwei=1.0,
        priority_gwei=1.0,
        pending_txs=1,
        mev_risk=0.0,
    )

    assert ok is False


def test_observe_blockspace_swallows_expected_local_failure():
    runtime = _Runtime(blockspace=_BlockspaceValueError())

    ok = runtime._observe_blockspace(
        block_number=1,
        basefee_gwei=1.0,
        priority_gwei=1.0,
        pending_txs=1,
        mev_risk=0.0,
    )

    assert ok is False


def test_observe_blockspace_does_not_swallow_unexpected_bug():
    runtime = _Runtime(blockspace=_BlockspaceKeyError())

    with pytest.raises(KeyError, match='unexpected blockspace bug'):
        runtime._observe_blockspace(
            block_number=1,
            basefee_gwei=1.0,
            priority_gwei=1.0,
            pending_txs=1,
            mev_risk=0.0,
        )
