from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution_capture.endpoint_universe import EndpointUniverse
from victor_ai_bot.rpc_preferences import RpcPreferencesStore


class _Chain:
    name = "ethereum"
    rpc_read = ["https://read-default"]
    rpc_send = ["https://send-default"]
    rpc_private = ["https://relay-default"]


class _Cfg:
    chain = _Chain()


def test_endpoint_universe_degrades_on_expected_snapshot_shape_failures():
    prefs = SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(TypeError("bad prefs")))
    manager = SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(ValueError("bad manager")))
    universe = EndpointUniverse(cfg=_Cfg(), rpc_manager=manager, rpc_preferences=prefs)
    snap = universe.candidates(lane="PRIVATE")
    assert snap["preferred"] == []
    assert snap["reason"] == "config_default"
    assert snap["relays"]


def test_endpoint_universe_does_not_swallow_unexpected_snapshot_bugs():
    class BadManager:
        @property
        def snapshot(self):
            raise ZeroDivisionError("boom")

    universe = EndpointUniverse(cfg=_Cfg(), rpc_manager=BadManager(), rpc_preferences=None)
    with pytest.raises(ZeroDivisionError):
        universe.candidates(lane="PUBLIC")


def test_endpoint_universe_filters_non_mapping_snapshots_safely():
    prefs = SimpleNamespace(snapshot=lambda: ["not", "mapping"])
    manager = SimpleNamespace(snapshot=lambda: ["still", "bad"])
    universe = EndpointUniverse(cfg=_Cfg(), rpc_manager=manager, rpc_preferences=prefs)
    snap = universe.candidates(lane="READ")
    assert snap["preferred"] == []
    assert snap["candidates"]


def test_rpc_preferences_invalid_json_degrades_to_empty(tmp_path: Path):
    store = RpcPreferencesStore(data_dir=str(tmp_path), chain="eth")
    store.path = str(tmp_path / "governance" / "rpc_preferences_eth.json")
    Path(store.path).parent.mkdir(parents=True, exist_ok=True)
    Path(store.path).write_text("{bad json", encoding="utf-8")
    loaded = store._load()
    assert loaded == {"read": [], "send": [], "private": []}


def test_rpc_preferences_non_mapping_json_degrades_to_empty(tmp_path: Path):
    store = RpcPreferencesStore(data_dir=str(tmp_path), chain="eth")
    store.path = str(tmp_path / "governance" / "rpc_preferences_eth.json")
    Path(store.path).parent.mkdir(parents=True, exist_ok=True)
    Path(store.path).write_text(json.dumps(["x"]), encoding="utf-8")
    loaded = store._load()
    assert loaded == {"read": [], "send": [], "private": []}


def test_rpc_preferences_does_not_swallow_unexpected_json_bugs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = RpcPreferencesStore(data_dir=str(tmp_path), chain="eth")
    store.path = str(tmp_path / "governance" / "rpc_preferences_eth.json")
    Path(store.path).parent.mkdir(parents=True, exist_ok=True)
    Path(store.path).write_text(json.dumps({"read": []}), encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(json, "load", boom)
    with pytest.raises(RuntimeError):
        store._load()


def test_rpc_preferences_patch_preserves_unspecified_lanes(tmp_path: Path):
    store = RpcPreferencesStore(data_dir=str(tmp_path), chain="eth")
    first = store.save(read=["https://r1"], send=["https://s1"], private=["https://p1"])
    assert first["configured"] is True
    patched = store.patch(read=[" https://r2 ", "https://r2"])
    assert patched["read"] == ["https://r2"]
    assert patched["send"] == ["https://s1"]
    assert patched["private"] == ["https://p1"]
    reloaded = store._load()
    assert reloaded == {
        "read": ["https://r2"],
        "send": ["https://s1"],
        "private": ["https://p1"],
    }
