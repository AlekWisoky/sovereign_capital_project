from fastapi.testclient import TestClient
from victor_ai_bot.server import app

import pytest

from victor_ai_bot.runtime_legacy import MultiRuntimeBundle


class _GoodRuntime:
    async def summary(self):
        return {"ok": True, "chain": "good"}


class _ValueErrorRuntime:
    async def summary(self):
        raise ValueError("bad_summary")


class _KeyErrorRuntime:
    async def summary(self):
        raise KeyError("unexpected")


class _SlowRuntime:
    async def summary(self):
        import asyncio

        await asyncio.sleep(0.05)
        return {"ok": True}


@pytest.mark.asyncio
async def test_summary_all_degrades_value_error_and_timeout():
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "good"
    bundle._runtimes = {
        "good": _GoodRuntime(),
        "bad": _ValueErrorRuntime(),
        "slow": _SlowRuntime(),
    }
    bundle.SNAPSHOT_TIMEOUT_S = 0.001

    snap = await MultiRuntimeBundle.summary_all(bundle)

    assert snap["active"] == "good"
    assert snap["summaryContract"]["truthFamily"] == "multichain_runtime"
    assert snap["summaryContract"]["readModel"] == "multichain_runtime_summary_projection_v1"
    assert snap["chains"]["good"]["ok"] is True
    assert snap["chains"]["bad"]["ok"] is False
    assert snap["chains"]["bad"]["error"] == "summary_failed:bad_summary"
    assert snap["chains"]["slow"]["ok"] is False
    assert snap["chains"]["slow"]["error"].startswith("summary_failed:")


@pytest.mark.asyncio
async def test_summary_all_does_not_swallow_unexpected_key_error():
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "boom"
    bundle._runtimes = {"boom": _KeyErrorRuntime()}
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    with pytest.raises(KeyError, match="unexpected"):
        await MultiRuntimeBundle.summary_all(bundle)


class _SingleRuntime:
    class _Cfg:
        class chain:
            name = "ethereum"

    cfg = _Cfg()

    async def summary(self):
        return {"ok": True, "summaryContract": {"truthFamily": "runtime_operator"}}


def test_multichain_summary_route_single_runtime_exposes_outer_summary_contract(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _SingleRuntime(), raising=False)
    client = TestClient(app)

    payload = client.get("/api/multichain/summary").json()

    assert payload["summaryContract"]["truthFamily"] == "multichain_runtime"
    assert payload["summaryContract"]["readModel"] == "multichain_runtime_summary_projection_v1"
    assert payload["chains"]["ethereum"]["summaryContract"]["truthFamily"] == "runtime_operator"
