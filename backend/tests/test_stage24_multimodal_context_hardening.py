from __future__ import annotations

from typing import Any, Dict

import pytest

from victor_ai_bot.caq_kds import multimodal as mm


class _BoomHash:
    def __call__(self, s: str) -> int:
        raise RuntimeError('boom-hash')


class _BoomGraphUpdate:
    def __call__(self, *args: Any, **kwargs: Any) -> None:
        raise ValueError('graph-update-bad-state')


class _BoomRagRetrieve:
    def __call__(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise KeyError('rag-runtime-bad-state')


class _BadContext:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return ['not-a-mapping']


def test_hash_embed_skips_expected_value_coercion_failures() -> None:
    vec = mm._hash_embed({'ok': 1.0, 'bad': object()}, dim=8)
    assert len(vec) == 8
    assert abs(sum(x * x for x in vec) - 1.0) < 1e-6


def test_hash_embed_does_not_swallow_unexpected_hash_bug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mm, '_stable_hash', _BoomHash())
    with pytest.raises(RuntimeError, match='boom-hash'):
        mm._hash_embed({'ok': 1.0}, dim=8)


def test_fuse_returns_deterministic_degraded_graph_context_on_safe_graph_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = mm.MarketFusionEngine(mm.FusionConfig(dim=8))
    monkeypatch.setattr(mm.GRAPH, 'update_from_snapshot', _BoomGraphUpdate())

    state = engine.fuse(local_state={'margin_ratio': 0.0012, 'gas_ratio': 0.0})

    assert state.context['degraded'] is True
    assert state.context['error_code'] == 'graph_context_unavailable'
    assert 'graph-update-bad-state' in state.context['error']
    assert state.context['edge_count'] == 0
    assert state.context['novelty'] == 0.0
    assert state.context['embedding'] == []


def test_fuse_marks_non_mapping_rag_context_as_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = mm.MarketFusionEngine(mm.FusionConfig(dim=8))
    monkeypatch.setattr(mm.RAG, 'retrieve', _BadContext())

    state = engine.fuse(local_state={'margin_ratio': 0.0009, 'gas_ratio': 0.0})

    assert state.context['degraded'] is True
    assert state.context['error_code'] == 'graph_context_invalid'
    assert state.context['error'] == 'non_mapping:list'
    assert state.context['anchors'] == []


def test_fuse_does_not_swallow_unexpected_rag_bug(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = mm.MarketFusionEngine(mm.FusionConfig(dim=8))
    monkeypatch.setattr(mm.RAG, 'retrieve', _BoomRagRetrieve())

    with pytest.raises(KeyError, match='rag-runtime-bad-state'):
        engine.fuse(local_state={'margin_ratio': 0.0011, 'gas_ratio': 0.0})
