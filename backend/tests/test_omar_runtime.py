import json

import pytest

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime


def test_omar_log_ignores_expected_serialization_error(tmp_path, monkeypatch):
    rt = OmarRuntime(OmarConfig(enabled=False), chain_name="test")
    rt.audit_path = str(tmp_path / "omar.jsonl")

    class BadJson:
        pass

    rt._log({"event": BadJson()})
    assert (tmp_path / "omar.jsonl").read_text() == ""


def test_omar_log_does_not_swallow_unexpected_runtime_error(tmp_path, monkeypatch):
    rt = OmarRuntime(OmarConfig(enabled=False), chain_name="test")
    rt.audit_path = str(tmp_path / "omar.jsonl")

    real_dumps = json.dumps

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(json, "dumps", boom)
    with pytest.raises(RuntimeError):
        rt._log({"event": "x"})
    monkeypatch.setattr(json, "dumps", real_dumps)
