import json
import os
from pathlib import Path

import pytest

from victor_ai_bot.rl_policy import RlPolicy


def test_rl_policy_load_invalid_json_degrades_to_empty(tmp_path):
    path = tmp_path / 'rl.json'
    path.write_text('{not-json', encoding='utf-8')
    policy = RlPolicy(path=str(path))
    assert policy.summary()['states'] == 0
    assert policy.summary()['total_updates'] == 0


def test_rl_policy_load_unexpected_json_bug_not_swallowed(tmp_path, monkeypatch):
    path = tmp_path / 'rl.json'
    path.write_text('{}', encoding='utf-8')

    def boom(*args, **kwargs):
        raise KeyboardInterrupt('unexpected')

    monkeypatch.setattr(json, 'load', boom)
    with pytest.raises(KeyboardInterrupt):
        RlPolicy(path=str(path))


def test_rl_policy_save_expected_json_error_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / 'rl.json'
    policy = RlPolicy(path=str(path))

    def boom(*args, **kwargs):
        raise TypeError('bad payload')

    monkeypatch.setattr(json, 'dump', boom)
    policy.save()
    assert not path.exists()


def test_rl_policy_save_unexpected_json_bug_not_swallowed(tmp_path, monkeypatch):
    path = tmp_path / 'rl.json'
    policy = RlPolicy(path=str(path))

    def boom(*args, **kwargs):
        raise RuntimeError('unexpected')

    monkeypatch.setattr(json, 'dump', boom)
    with pytest.raises(RuntimeError):
        policy.save()
