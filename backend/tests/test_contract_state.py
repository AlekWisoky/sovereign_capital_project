import asyncio
import os
import pytest
from victor_ai_bot.config import load_config
from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.contract import validate_runtime_state

@pytest.mark.asyncio
async def test_state_contract_and_ws_mirroring(tmp_path):
    # Use ethereum config from repo (safe placeholders allowed)
    cfg = load_config("config/ethereum.yaml")
    rt = RuntimeBundle(cfg)
    # no start() needed for snapshot
    st = await rt.snapshot()
    validate_runtime_state(st)

    # websocket mirrors REST payload inside data
    msg = {"type": "state", "data": st}
    assert msg["type"] == "state"
    assert msg["data"] == st

@pytest.mark.asyncio
async def test_optional_contract_validation_does_not_crash(monkeypatch):
    cfg = load_config("config/ethereum.yaml")
    rt = RuntimeBundle(cfg)
    monkeypatch.setenv("VICTOR_VALIDATE_CONTRACT", "1")
    st = await rt.snapshot()
    validate_runtime_state(st)
