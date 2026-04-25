import types

import pytest

from victor_ai_bot.runtime_legacy import MultiRuntimeBundle


class _GoodRuntime:
    async def snapshot(self):
        return {"ok": True, "chain": "good"}


class _ValueErrorRuntime:
    async def snapshot(self):
        raise ValueError("bad_snapshot")


class _KeyErrorRuntime:
    async def snapshot(self):
        raise KeyError("unexpected")


class _SlowRuntime:
    async def snapshot(self):
        import asyncio

        await asyncio.sleep(0.05)
        return {"ok": True}


@pytest.mark.asyncio
async def test_snapshot_all_degrades_value_error_and_timeout():
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "good"
    bundle._runtimes = {
        "good": _GoodRuntime(),
        "bad": _ValueErrorRuntime(),
        "slow": _SlowRuntime(),
    }
    bundle.SNAPSHOT_TIMEOUT_S = 0.001

    snap = await MultiRuntimeBundle.snapshot_all(bundle)

    assert snap["active"] == "good"
    assert snap["chains"]["good"]["ok"] is True
    assert snap["chains"]["bad"]["ok"] is False
    assert snap["chains"]["bad"]["error"] == "snapshot_failed:bad_snapshot"
    assert snap["chains"]["slow"]["ok"] is False
    assert snap["chains"]["slow"]["error"].startswith("snapshot_failed:")


@pytest.mark.asyncio
async def test_snapshot_all_does_not_swallow_unexpected_key_error():
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = "boom"
    bundle._runtimes = {"boom": _KeyErrorRuntime()}
    bundle.SNAPSHOT_TIMEOUT_S = 0.01

    with pytest.raises(KeyError, match="unexpected"):
        await MultiRuntimeBundle.snapshot_all(bundle)
