from __future__ import annotations

import json

import pytest

from victor_ai_bot.execution_capture.calibration import EmpiricalCalibrationStore, _safe_float


def test_calibration_load_invalid_json_degrades_to_empty_state(tmp_path):
    store_dir = tmp_path
    p = store_dir / 'execution_capture' / 'calibration_eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{not valid json', encoding='utf-8')

    store = EmpiricalCalibrationStore(data_dir=str(store_dir), chain='eth')

    assert store.snapshot() == {'items': []}


def test_calibration_load_non_mapping_json_degrades_to_empty_state(tmp_path):
    store_dir = tmp_path
    p = store_dir / 'execution_capture' / 'calibration_eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([1, 2, 3]), encoding='utf-8')

    store = EmpiricalCalibrationStore(data_dir=str(store_dir), chain='eth')

    assert store.snapshot() == {'items': []}


def test_calibration_load_does_not_swallow_unexpected_json_bug(tmp_path, monkeypatch):
    store_dir = tmp_path
    p = store_dir / 'execution_capture' / 'calibration_eth.json'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{}', encoding='utf-8')

    def _boom(*args, **kwargs):
        raise RuntimeError('unexpected_json_bug')

    monkeypatch.setattr(json, 'load', _boom)

    with pytest.raises(RuntimeError, match='unexpected_json_bug'):
        EmpiricalCalibrationStore(data_dir=str(store_dir), chain='eth')


def test_safe_float_keeps_expected_coercion_behavior():
    assert _safe_float('1.25') == 1.25
    assert _safe_float('bad', default=3.5) == 3.5


def test_safe_float_does_not_swallow_unexpected_bug():
    class BadFloat:
        def __float__(self):
            raise RuntimeError('unexpected_float_bug')

    with pytest.raises(RuntimeError, match='unexpected_float_bug'):
        _safe_float(BadFloat())
