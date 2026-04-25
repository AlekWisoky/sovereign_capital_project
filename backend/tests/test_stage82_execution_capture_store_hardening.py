import json
from pathlib import Path

import pytest

from victor_ai_bot.execution_capture.path_diversity import PathDiversityMemory
from victor_ai_bot.execution_capture.route_quality_store import RouteQualityStore
from victor_ai_bot.execution_capture.venue_profiles import VenueReliabilityStore


def test_route_quality_store_invalid_json_degrades_to_blank_state(tmp_path: Path):
    path = tmp_path / 'execution_capture' / 'route_quality_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{bad json', encoding='utf-8')

    store = RouteQualityStore(data_dir=str(tmp_path), chain='eth')
    assert store.snapshot() == {'items': []}
    assert store.summary(route_family='f', venue_subset=[], split_signature='default') == {
        'attempts': 0,
        'success_rate': 0.65,
        'mean_realized_edge_usd': 0.0,
        'quality': 0.627,
    }


def test_route_quality_store_unexpected_json_bug_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / 'execution_capture' / 'route_quality_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}', encoding='utf-8')

    def boom(*args, **kwargs):
        raise AssertionError('json bug')

    monkeypatch.setattr(json, 'load', boom)
    with pytest.raises(AssertionError, match='json bug'):
        RouteQualityStore(data_dir=str(tmp_path), chain='eth')


def test_path_diversity_invalid_json_degrades_to_blank_state(tmp_path: Path):
    path = tmp_path / 'execution_capture' / 'paths.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{bad json', encoding='utf-8')

    store = PathDiversityMemory(str(path))
    assert store.snapshot() == {'paths': []}
    assert store.penalty('x') == 0.0


def test_path_diversity_unexpected_json_bug_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / 'execution_capture' / 'paths.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}', encoding='utf-8')

    def boom(*args, **kwargs):
        raise AssertionError('json bug')

    monkeypatch.setattr(json, 'load', boom)
    with pytest.raises(AssertionError, match='json bug'):
        PathDiversityMemory(str(path))


def test_venue_profiles_invalid_json_degrades_to_blank_state(tmp_path: Path):
    path = tmp_path / 'execution_capture' / 'venue_profiles_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{bad json', encoding='utf-8')

    store = VenueReliabilityStore(data_dir=str(tmp_path), chain='eth')
    assert store.snapshot() == {'venues': []}
    assert store.profile(venue='') == {
        'venue_reliability_score': 0.35,
        'venue_slippage_bias': 0.0,
        'venue_failure_penalty': 0.0,
        'fill_reliability': 0.0,
        'latency_sensitivity': 0.0,
    }


def test_venue_profiles_unexpected_json_bug_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / 'execution_capture' / 'venue_profiles_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}', encoding='utf-8')

    def boom(*args, **kwargs):
        raise AssertionError('json bug')

    monkeypatch.setattr(json, 'load', boom)
    with pytest.raises(AssertionError, match='json bug'):
        VenueReliabilityStore(data_dir=str(tmp_path), chain='eth')
