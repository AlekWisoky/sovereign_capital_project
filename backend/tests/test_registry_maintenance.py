from pathlib import Path

from victor_ai_bot.superstructure.registry import AgentRegistry, default_registry
from victor_ai_bot.superstructure.types import AgentState


class _ExplodingBus:
    def update(self, bucket, data):
        raise RuntimeError(f"bus offline for {bucket}")


def test_registry_snapshot_exposes_runtime_degradation_for_meta_and_bus(monkeypatch, tmp_path: Path):
    reg = default_registry(data_dir=str(tmp_path), chain="test")
    monkeypatch.setattr("victor_ai_bot.superstructure.registry.BUS", _ExplodingBus())

    reg.transition("coordinator", AgentState.NEGOTIATING, reason="probe", meta=object())

    snap = reg.snapshot()
    runtime = snap["runtime"]

    assert snap["agents"]
    assert snap["transitions"][-1]["new"] == AgentState.NEGOTIATING.value
    assert runtime["meta_update"]["ok"] is False
    assert runtime["meta_update"]["last_error_code"] == "registry_meta_invalid"
    assert runtime["bus_publish"]["ok"] is False
    assert runtime["bus_publish"]["last_error_code"] == "registry_bus_publish_failed"
    assert runtime["storage"]["ok"] is True
    assert runtime["degraded"] is True


def test_registry_snapshot_exposes_storage_failure(monkeypatch, tmp_path: Path):
    reg = AgentRegistry(data_dir=str(tmp_path), chain="test")
    reg.upsert(default_registry(data_dir=str(tmp_path), chain="seed").get("coordinator"))

    def _boom(fd, payload):
        raise OSError("disk full")

    monkeypatch.setattr(reg, "_write_all", _boom)

    reg.transition("coordinator", AgentState.EXECUTING, reason="write-probe")

    snap = reg.snapshot()
    runtime = snap["runtime"]

    assert snap["transitions"][-1]["new"] == AgentState.EXECUTING.value
    assert runtime["storage"]["ok"] is False
    assert runtime["storage"]["last_error_code"] == "registry_transition_write_failed"
    assert runtime["degraded"] is True
