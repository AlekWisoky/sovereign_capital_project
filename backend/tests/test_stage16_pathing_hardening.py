from pathlib import Path

import victor_ai_bot.pathing as pathing


def test_canonical_data_dir_falls_back_when_resolve_raises(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root / 'backend')

    def boom(self, *args, **kwargs):
        raise RuntimeError('cwd resolution unavailable')

    monkeypatch.setattr(Path, 'resolve', boom)
    out = pathing.canonical_data_dir('relative/custom-data')
    assert out.endswith('relative/custom-data')



def test_migrate_legacy_data_roots_reports_oserror_skip(tmp_path, monkeypatch):
    legacy = tmp_path / 'data'
    canonical = tmp_path / 'backend' / 'data'
    failing = legacy / 'ledger.jsonl'
    failing.parent.mkdir(parents=True)
    failing.write_text('x', encoding='utf-8')

    monkeypatch.setattr(pathing, 'LEGACY_ROOT_DATA_DIR', legacy)
    monkeypatch.setattr(pathing, 'CANONICAL_BACKEND_DATA_DIR', canonical)

    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(self):
        if self == failing:
            raise OSError('simulated read failure')
        return original_read_bytes(self)

    monkeypatch.setattr(Path, 'read_bytes', guarded_read_bytes)

    results = pathing.migrate_legacy_data_roots()
    assert results['ledger.jsonl'] == 'skipped:OSError'
    assert not (canonical / 'ledger.jsonl').exists()



def test_cleanup_empty_nested_backend_residue_removes_only_empty_dirs(tmp_path, monkeypatch):
    backend_root = tmp_path / 'backend'
    empty_nested = backend_root / 'backend' / 'data' / 'caq_kds'
    empty_nested.mkdir(parents=True)
    monkeypatch.setattr(pathing, 'BACKEND_ROOT', backend_root)

    pathing._cleanup_empty_nested_backend_residue()

    assert not (backend_root / 'backend').exists()

    nonempty_root = tmp_path / 'backend_nonempty'
    kept_nested = nonempty_root / 'backend' / 'data'
    kept_nested.mkdir(parents=True)
    (kept_nested / 'marker.txt').write_text('keep', encoding='utf-8')
    monkeypatch.setattr(pathing, 'BACKEND_ROOT', nonempty_root)

    pathing._cleanup_empty_nested_backend_residue()

    assert (nonempty_root / 'backend').exists()
    assert (kept_nested / 'marker.txt').exists()
