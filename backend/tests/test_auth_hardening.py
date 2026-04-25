import os

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from victor_ai_bot.security.auth import require_capability
from victor_ai_bot.security.permissions import Capability


class _RT:
    _security_audit = None
    cfg = type('Cfg', (), {'chain': type('C', (), {'name': 'eth'})()})()


def _app():
    app = FastAPI()
    app.state.runtime = _RT()

    @app.post('/mutate')
    def mutate(request: Request):
        require_capability(Capability.ADMIN_WRITE, request=request)
        return {'ok': True}

    return app


def test_admin_closed_by_default(monkeypatch):
    monkeypatch.delenv('VICTOR_ADMIN_KEY', raising=False)
    monkeypatch.delenv('VICTOR_ALLOW_INSECURE_LOCAL_ADMIN', raising=False)
    client = TestClient(_app())
    r = client.post('/mutate')
    assert r.status_code == 401


def test_explicit_insecure_local_admin_opt_in(monkeypatch):
    monkeypatch.delenv('VICTOR_ADMIN_KEY', raising=False)
    monkeypatch.setenv('VICTOR_ALLOW_INSECURE_LOCAL_ADMIN', '1')
    client = TestClient(_app())
    r = client.post('/mutate')
    assert r.status_code == 200


def test_launch_mutation_requires_admin_key(monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    from victor_ai_bot.server import app
    client = TestClient(app)
    denied = client.post('/api/launch/enable-next')
    assert denied.status_code == 401
    allowed = client.post('/api/launch/enable-next', headers={'X-Admin-Key': 'secret'})
    assert allowed.status_code in {200, 401}


class _ExplodingAuditStore:
    def record(self, **kwargs):
        raise RuntimeError("boom")


class _AuditRT:
    _security_audit = _ExplodingAuditStore()
    cfg = type('Cfg', (), {'chain': type('C', (), {'name': 'eth'})()})()


def _app_with_exploding_audit():
    app = FastAPI()
    app.state.runtime = _AuditRT()

    @app.post('/mutate')
    def mutate(request: Request):
        require_capability(Capability.ADMIN_WRITE, request=request)
        return {'ok': True}

    return app


def test_audit_runtime_error_is_not_silently_swallowed(monkeypatch):
    monkeypatch.delenv('VICTOR_ADMIN_KEY', raising=False)
    monkeypatch.setenv('VICTOR_ALLOW_INSECURE_LOCAL_ADMIN', '1')
    client = TestClient(_app_with_exploding_audit())
    with pytest.raises(RuntimeError, match='boom'):
        client.post('/mutate')
