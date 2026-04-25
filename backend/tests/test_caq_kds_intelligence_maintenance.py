from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.server import app
import victor_ai_bot.api_routes.intelligence_routes as intelligence_routes
from victor_ai_bot.caq_kds import xai as xai_mod
from victor_ai_bot.caq_kds import reliability as rel_mod


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="base"))


class _AuditWithState:
    def latest(self, limit: int):
        return [{"decision_id": "d-1", "ts": 1.0}]

    def get(self, decision_id: str):
        return {"decision_id": str(decision_id)}

    def state(self):
        return {"append": {"ok": False, "last_error_code": "audit_append_failed"}, "degraded": True}


class _XaiEngineWithState:
    def __init__(self):
        self.audit = _AuditWithState()


class _ReliabilityTrackerWithState:
    def state(self):
        return {"reliability": 0.88, "storage": {"degraded": True, "bus_publish": {"ok": False, "last_error_code": "reliability_publish_failed"}}}


class _BusPublishFailure:
    def snapshot(self):
        return {"kds": {"data": {"last_conf": 0.7}}}

    def publish(self, bucket: str, data):
        raise RuntimeError("publish_down")


def test_decision_audit_log_marks_storage_degraded_on_append_failure(tmp_path, monkeypatch):
    log = xai_mod.DecisionAuditLog(data_dir=str(tmp_path), chain="base", max_cache=5)
    monkeypatch.setattr(xai_mod.os, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk_full")))

    expl = xai_mod.DecisionExplanation(
        decision_id="dec-1",
        ts=1.0,
        chain="base",
        kind="trade",
        mode="auto",
        ok=True,
    )

    logged_id = log.log(expl)

    assert logged_id == "dec-1"
    assert log.latest(1)[0]["decision_id"] == "dec-1"
    state = log.state()
    assert state["degraded"] is True
    assert state["append"]["ok"] is False
    assert state["append"]["last_error_code"] == "audit_append_failed"


def test_reliability_tracker_surfaces_load_and_publish_degradation(tmp_path, monkeypatch):
    state_path = Path(tmp_path) / "caq_kds" / "reliability_base.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{bad json", encoding="utf-8")

    monkeypatch.setattr(rel_mod, "BUS", _BusPublishFailure())
    tracker = rel_mod.PerformanceQuantifier(data_dir=str(tmp_path), chain="base", window=8)

    initial = tracker.state()
    assert initial["storage"]["degraded"] is True
    assert initial["storage"]["state_load"]["last_error_code"] == "reliability_state_load_failed"

    tracker.observe(
        row={
            "amount_in_wei": "100",
            "realized_after_gas_wei": "5",
            "ok": True,
            "extra": {"aqe_debug": {"joint_entropy": "0.2", "explore": False}},
        }
    )

    state = tracker.state()
    assert state["storage"]["bus_publish"]["ok"] is False
    assert state["storage"]["bus_publish"]["last_error_code"] == "reliability_publish_failed"
    assert state["storage"]["degraded"] is True


def test_intelligence_routes_expose_additive_storage_state(monkeypatch):
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: _Runtime()
    monkeypatch.setattr(
        intelligence_routes,
        "xai_engine",
        lambda *, data_dir, chain: _XaiEngineWithState(),
    )
    monkeypatch.setattr(
        intelligence_routes,
        "reliability_tracker",
        lambda *, data_dir, chain: _ReliabilityTrackerWithState(),
    )

    client = TestClient(app)
    try:
        latest = client.get("/api/xai/latest?limit=2")
        decision = client.get("/api/xai/decision/dec-1")
        reliability = client.get("/api/reliability/state")

        assert latest.status_code == 200
        assert latest.json()["storage"]["degraded"] is True
        assert decision.json()["storage"]["append"]["last_error_code"] == "audit_append_failed"
        assert reliability.json()["state"]["storage"]["bus_publish"]["last_error_code"] == "reliability_publish_failed"
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)
