from pathlib import Path

from victor_ai_bot.pathing import canonical_data_dir


def test_canonical_data_dir_maps_legacy_root_data(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    backend = repo / 'backend'
    package = backend / 'victor_ai_bot'
    package.mkdir(parents=True)
    monkeypatch.chdir(repo)
    out = canonical_data_dir('data')
    assert out.endswith('backend/data')
