from types import SimpleNamespace

import victor_ai_bot.server as server


class _DummyAppState:
    pass


class _DummyRuntime:
    pass


def _minimal_runtime_attach(app, runtime):
    app.state.runtime = runtime  # type: ignore[attr-defined]


def test_create_app_exposes_boot_status_and_omar_disabled_by_default(monkeypatch):
    monkeypatch.setattr(server, 'configure_logging', lambda: None)
    monkeypatch.setattr(server, 'load_runtime_configs', lambda default_cfg: [])
    monkeypatch.setattr(server, 'build_runtime', lambda cfgs: _DummyRuntime())
    monkeypatch.setattr(server, 'attach_runtime', _minimal_runtime_attach)

    app = server.create_app()

    boot = app.state.boot_status  # type: ignore[attr-defined]
    assert set(boot.keys()) == {'public_defaults', 'config_validation', 'omar'}
    assert boot['public_defaults']['ok'] is True
    assert boot['config_validation']['ok'] is True
    assert boot['config_validation']['reason'] == 'validated'
    assert boot['omar']['enabled'] is False
    assert boot['omar']['reason'] == 'disabled'


def test_create_app_records_public_defaults_failure_without_crashing(monkeypatch):
    cfg = SimpleNamespace()

    monkeypatch.setattr(server, 'configure_logging', lambda: None)
    monkeypatch.setattr(server, 'load_runtime_configs', lambda default_cfg: [cfg])
    monkeypatch.setattr(server, 'enforce_public_defaults', lambda c: (_ for _ in ()).throw(AttributeError('boom')))
    monkeypatch.setattr(server, 'enforce_or_warn', lambda c: None)
    monkeypatch.setattr(server, 'build_runtime', lambda cfgs: _DummyRuntime())
    monkeypatch.setattr(server, 'attach_runtime', _minimal_runtime_attach)

    app = server.create_app()

    boot = app.state.boot_status  # type: ignore[attr-defined]
    assert boot['public_defaults']['ok'] is False
    assert boot['public_defaults']['reason'] == 'public_defaults_failed'
    assert 'boom' in boot['public_defaults']['error']
    assert boot['config_validation']['ok'] is True
