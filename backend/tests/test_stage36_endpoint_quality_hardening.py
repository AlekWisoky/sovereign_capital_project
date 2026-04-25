import json

import pytest

from victor_ai_bot.execution_capture import endpoint_quality as mod
from victor_ai_bot.execution_capture.endpoint_quality import EndpointQualityStore, _safe_float, _safe_int


class ExplodingFloat:
    def __float__(self):
        raise RuntimeError('boom')


class ExplodingInt:
    def __int__(self):
        raise RuntimeError('boom')


def test_endpoint_quality_load_invalid_json_degrades_to_blank(tmp_path):
    path = tmp_path / 'execution_capture' / 'endpoint_quality_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{not-json', encoding='utf-8')
    store = EndpointQualityStore(data_dir=str(tmp_path), chain='eth')
    snap = store.snapshot()
    assert snap['lanes'] == {}
    assert snap['relays'] == {}
    assert isinstance(snap['updated_ts'], int)


def test_endpoint_quality_load_unexpected_json_bug_not_swallowed(tmp_path, monkeypatch):
    path = tmp_path / 'execution_capture' / 'endpoint_quality_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}', encoding='utf-8')

    def _boom(*args, **kwargs):
        raise RuntimeError('unexpected-json-bug')

    monkeypatch.setattr(mod.json, 'load', _boom)
    with pytest.raises(RuntimeError, match='unexpected-json-bug'):
        EndpointQualityStore(data_dir=str(tmp_path), chain='eth')


def test_endpoint_quality_safe_numeric_coercion_still_degrades_for_expected_values():
    assert _safe_float('bad', 1.5) == 1.5
    assert _safe_int('bad', 7) == 7


def test_endpoint_quality_safe_numeric_coercion_does_not_swallow_unexpected_bugs():
    with pytest.raises(RuntimeError, match='boom'):
        _safe_float(ExplodingFloat(), 1.0)
    with pytest.raises(RuntimeError, match='boom'):
        _safe_int(ExplodingInt(), 1)
