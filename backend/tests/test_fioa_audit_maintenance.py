from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from victor_ai_bot.fioa.audit import AuditLogger
from victor_ai_bot.fioa.config import FIOAConfig
from victor_ai_bot.fioa.runtime import FIOARuntime
from victor_ai_bot.llm_inl.config import LLMINLConfig
from victor_ai_bot.llm_inl.runtime import LLMINLRuntime


def test_audit_logger_append_failure_is_explicitly_reported(tmp_path: Path):
    logger = AuditLogger(str(tmp_path / "audit.jsonl"))
    with patch.object(logger, "_write_all", side_effect=OSError("disk full")):
        logger.append("EVENT", foo="bar")
    state = logger.state()
    assert state["degraded"] is True
    assert state["append"]["ok"] is False
    assert state["append"]["last_error_code"] == "append_write_failed"


def test_audit_logger_tail_partial_parse_is_explicitly_reported(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    path.write_bytes(b'{"ts":1,"event":"GOOD"}\n{bad json\n')
    logger = AuditLogger(str(path))
    out = logger.tail(limit=10)
    assert out == [{"ts": 1, "event": "GOOD"}]
    state = logger.state()
    assert state["degraded"] is True
    assert state["tail"]["ok"] is False
    assert state["tail"]["last_error_code"] == "tail_parse_partial"


def test_fioa_runtime_state_surfaces_audit_storage_degradation(tmp_path: Path):
    runtime = FIOARuntime(cfg=FIOAConfig(enabled=True), chain="eth", data_dir=str(tmp_path))
    with patch.object(runtime.audit, "_write_all", side_effect=OSError("disk full")):
        runtime.audit.append("EVENT", chain="eth")
    state = runtime.state()
    assert state["audit"]["degraded"] is True
    assert state["audit"]["append"]["last_error_code"] == "append_write_failed"
    report = runtime.governance_report(limit_audit=10)
    assert report["audit"]["degraded"] is True


def test_llm_inl_state_surfaces_audit_storage_degradation(tmp_path: Path):
    runtime = LLMINLRuntime(cfg=LLMINLConfig(enabled=True), chain="eth", data_dir=str(tmp_path))
    with patch.object(runtime.audit, "_write_all", side_effect=OSError("disk full")):
        runtime.audit.append("EVENT", chain="eth")
    state = runtime.state()
    assert state["audit"]["degraded"] is True
    assert state["audit"]["append"]["last_error_code"] == "append_write_failed"
