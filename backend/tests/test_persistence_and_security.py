import os
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from victor_ai_bot.agents.attribution import AgentAttributionStore
from victor_ai_bot.execution_capture.calibration import EmpiricalCalibrationStore
from victor_ai_bot.security.audit import SecurityAuditStore
from victor_ai_bot.security.auth import require_capability
from victor_ai_bot.security.permissions import Capability
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.strategies.family_scorecards import FamilyScorecardStore
from victor_ai_bot.telemetry.events import TelemetryEvent
from victor_ai_bot.telemetry.store import TelemetryStore


def test_sqlite_backed_persistence_roundtrip(tmp_path):
    tstore = TelemetryStore(data_dir=str(tmp_path), chain='eth')
    tstore.append(TelemetryEvent(event_type='decision', chain='eth', ts_ms=1, payload={'route_family': 'rf', 'strategy_family': 'sf', 'lane': 'PRIVATE'}))
    assert tstore.tail(limit=5)[0]['payload']['route_family'] == 'rf'

    attrib = AgentAttributionStore(path=str(tmp_path / 'agents' / 'attrib.json'), chain='eth')
    attrib.append({'ts_ms': 2, 'opportunity_id': 'o1', 'route_id': 'r1', 'strategy_family': 'sf', 'contributors': [{'agent': 'A1', 'followed': True, 'realized_pnl_impact_usd': 2.5, 'precision_hit': True}]})
    assert attrib.summary()['agents'][0]['agent'] == 'A1'

    fam = FamilyScorecardStore(path=str(tmp_path / 'strategies' / 'score.json'), chain='eth')
    fam.observe(family='flashloan_atomic', realized_pnl_usd=4.0, gas_cost_usd=1.0, ok=True, regime='balanced')
    assert fam.snapshot()['families'][0]['family'] == 'flashloan_atomic'

    cal = EmpiricalCalibrationStore(data_dir=str(tmp_path), chain='eth')
    cal.observe(route_family='rf', lane='PRIVATE', regime='balanced', projected_realized_edge_usd=10.0, actual_realized_edge_usd=8.0, predicted_success_probability=0.8, actual_success=True, predicted_slippage_usd=1.0, actual_slippage_usd=1.2, predicted_interference_probability=0.2, actual_stale=False)
    snap = cal.snapshot()['items'][0]
    assert snap['route_family'] == 'rf'
    assert snap['regime'] == 'balanced'


def test_security_capability_denied_and_audited(tmp_path, monkeypatch):
    monkeypatch.setenv('VICTOR_ADMIN_KEY', 'secret')
    app = FastAPI()
    db = PersistenceDB(str(tmp_path / 'state' / 'db.sqlite3'))
    app.state.runtime = type('RT', (), {'_security_audit': SecurityAuditStore(db), 'cfg': type('Cfg', (), {'chain': type('C', (), {'name': 'eth'})()})()})()

    @app.get('/admin-check')
    def admin_check(request: Request):
        require_capability(Capability.ADMIN_READ, request=request)
        return {'ok': True}

    client = TestClient(app)
    r = client.get('/admin-check')
    assert r.status_code == 401
    with db.connect() as conn:
        rows = conn.execute('SELECT allowed, capability FROM security_audit').fetchall()
    assert len(rows) >= 1
    assert int(rows[-1]['allowed']) == 0
