from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.caq_kds import self_evolution as se_mod
from victor_ai_bot.caq_kds.bus import BUS
from victor_ai_bot.caq_kds.knowledge_graph import GRAPH
from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.server import app
import victor_ai_bot.api_routes.intelligence_routes as intelligence_routes


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="base"))


class _KdsEngineWithState:
    def state(self):
        return {
            "enabled": True,
            "active_count": 1,
            "storage": {
                "promotion_log": {"ok": False, "last_error_code": "kds_promotion_log_failed"},
                "graph_update": {"ok": True},
                "bus_publish": {"ok": False, "last_error_code": "kds_publish_failed"},
                "degraded": True,
            },
            "graph": {"node_count": 3, "edge_count": 2, "degraded": False},
        }


def _state() -> dict:
    return {
        "margin_ratio": 0.03,
        "legs": 4,
        "S_global": {
            "regime": "high_vol_breakout",
            "features": {
                "local.margin_ratio": 0.03,
                "local.gas_ratio": 0.25,
                "local.legs": 4,
                "mev.sandwich_risk": 0.7,
                "local.vol_proxy": 0.8,
                "rel.reliability": 0.2,
                "local.slippage_bps": 40,
            },
        },
        "C_t": {"novelty": 0.9},
    }


def _reset_graph_and_bus() -> None:
    GRAPH.nodes.clear()
    GRAPH.edges.clear()
    GRAPH._status["update"].update({"ok": True, "last_error_code": "", "last_error": "", "last_update_ts": 0.0})
    GRAPH._status["degraded"] = False
    with BUS._lock:
        BUS._buckets.clear()


def test_self_evolution_tick_and_promote_publish_bus_and_graph(tmp_path, monkeypatch):
    _reset_graph_and_bus()
    monkeypatch.setenv("VICTOR_CAQ_KDS_SELF_EVOLUTION", "1")
    monkeypatch.setenv("VICTOR_KDS_MIN_TRIALS", "1")

    eng = se_mod.SelfEvolutionEngine(data_dir=str(tmp_path), chain="base-test")
    pid = eng.tick(state=_state())

    assert pid is not None
    snap = BUS.snapshot()
    assert snap["kds"]["data"]["last_id"] == pid

    tick_state = eng.state()
    assert tick_state["storage"]["bus_publish"]["ok"] is True
    assert tick_state["storage"]["graph_update"]["ok"] is True
    assert tick_state["graph"]["node_count"] >= 1

    eng.observe(hypothesis_id=str(pid), ok=True, r_total=0.05)

    promoted = eng.state()
    assert promoted["active_count"] == 0
    assert promoted["storage"]["promotion_log"]["ok"] is True
    assert promoted["storage"]["graph_update"]["ok"] is True

    lines = (Path(tmp_path) / "caq_kds" / "promoted_strategies_base-test.jsonl").read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["id"] == pid


def test_self_evolution_surfaces_bus_publish_degradation(tmp_path, monkeypatch):
    _reset_graph_and_bus()
    monkeypatch.setenv("VICTOR_CAQ_KDS_SELF_EVOLUTION", "1")
    eng = se_mod.SelfEvolutionEngine(data_dir=str(tmp_path), chain="base-bus-down")

    class _BusDown:
        def publish(self, bucket: str, payload: dict) -> None:
            raise RuntimeError("down")

    monkeypatch.setattr(se_mod, "BUS", _BusDown())
    pid = eng.tick(state=_state())

    assert pid is not None
    state = eng.state()
    assert state["storage"]["bus_publish"]["ok"] is False
    assert state["storage"]["bus_publish"]["last_error_code"] == "kds_publish_failed"
    assert state["storage"]["degraded"] is True


def test_kds_route_exposes_additive_storage_and_graph_state(monkeypatch):
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: _Runtime()
    monkeypatch.setattr(
        intelligence_routes,
        "kds_engine",
        lambda *, data_dir, chain: _KdsEngineWithState(),
    )

    client = TestClient(app)
    try:
        resp = client.get("/api/kds/state")
        assert resp.status_code == 200
        body = resp.json()["state"]
        assert body["storage"]["promotion_log"]["last_error_code"] == "kds_promotion_log_failed"
        assert body["storage"]["bus_publish"]["last_error_code"] == "kds_publish_failed"
        assert body["graph"]["node_count"] == 3
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)
