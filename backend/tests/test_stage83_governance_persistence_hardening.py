import json

import pytest

from victor_ai_bot.governance.kill_switch import KillSwitchStore
from victor_ai_bot.governance.pdr import PolicyDecisionRecordLog


class _BadLoad:
    def __call__(self, *args, **kwargs):
        raise KeyError('boom')


class _BadJsonable:
    def __iter__(self):
        raise ValueError('bad-entry')


class _BadEncode:
    def __repr__(self):
        return '<BadEncode>'


def test_kill_switch_invalid_json_degrades_to_default(tmp_path):
    path = tmp_path / 'governance' / 'kill_switch_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{bad json', encoding='utf-8')

    store = KillSwitchStore(data_dir=str(tmp_path), chain='eth')
    assert store.snapshot() == {'metrics': {}, 'suppressions': {}, 'history': []}


def test_kill_switch_non_mapping_json_degrades_to_default(tmp_path):
    path = tmp_path / 'governance' / 'kill_switch_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(['bad']), encoding='utf-8')

    store = KillSwitchStore(data_dir=str(tmp_path), chain='eth')
    assert store.snapshot() == {'metrics': {}, 'suppressions': {}, 'history': []}


def test_kill_switch_does_not_swallow_unexpected_json_load_bug(tmp_path, monkeypatch):
    path = tmp_path / 'governance' / 'kill_switch_eth.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{}', encoding='utf-8')

    monkeypatch.setattr('victor_ai_bot.governance.kill_switch.json.load', _BadLoad())
    with pytest.raises(KeyError):
        KillSwitchStore(data_dir=str(tmp_path), chain='eth')


def test_pdr_append_expected_bad_entry_is_ignored(tmp_path):
    log = PolicyDecisionRecordLog(path=str(tmp_path / 'gov' / 'pdr.jsonl'))
    log.append(_BadJsonable())
    assert log.tail() == []


def test_pdr_append_does_not_swallow_unexpected_json_bug(tmp_path, monkeypatch):
    log = PolicyDecisionRecordLog(path=str(tmp_path / 'gov' / 'pdr.jsonl'))

    def bad_dumps(*args, **kwargs):
        raise LookupError('boom')

    monkeypatch.setattr('victor_ai_bot.governance.pdr.json.dumps', bad_dumps)
    with pytest.raises(LookupError):
        log.append({'x': _BadEncode()})
