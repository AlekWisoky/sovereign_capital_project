from __future__ import annotations

import asyncio

from victor_ai_bot.runtime_legacy import MultiRuntimeBundle


class _Meta:
    def __init__(self):
        self.calls = []

    def state(self):
        self.calls.append(("state", None))
        return {"ok": True, "items": [1]}

    def start(self):
        self.calls.append(("start", None))

    async def stop(self):
        self.calls.append(("stop", None))

    def generate(self, runtime):
        self.calls.append(("generate", runtime))
        return [{"id": "cand-1"}]

    def apply_candidate(self, runtime, cand_id: str):
        self.calls.append(("apply", cand_id, runtime))
        return {"ok": True, "id": cand_id}


def test_multiruntime_meta_facade_preserves_meta_helper_contract() -> None:
    runtime = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    runtime._meta = _Meta()

    assert runtime.meta_state() == {"ok": True, "items": [1]}
    assert runtime.meta_start() is True
    assert asyncio.run(runtime.meta_stop()) is True
    assert runtime.meta_generate() == {"ok": True, "candidates": [{"id": "cand-1"}]}
    assert runtime.meta_apply("cand-1") == {"ok": True, "id": "cand-1"}

    assert runtime._meta.calls[0] == ("state", None)
    assert runtime._meta.calls[1] == ("start", None)
    assert runtime._meta.calls[2] == ("stop", None)
    assert runtime._meta.calls[3][0] == "generate"
    assert runtime._meta.calls[4][0] == "apply"


def test_multiruntime_meta_facade_reports_unavailable_meta() -> None:
    runtime = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    runtime._meta = None

    state = runtime.meta_state()
    assert state["ok"] is True
    assert state["enabled"] is False
    assert state["reason"] == "unavailable"
    assert state["status"] == "unavailable"
    assert state["reason_code"] == "meta_unavailable"
    assert runtime.meta_start() is False
    assert asyncio.run(runtime.meta_stop()) is False
    assert runtime.meta_generate() == {"ok": False, "status": "unavailable", "reason_code": "meta_unavailable", "reason": "meta_unavailable", "error": "meta_unavailable", "candidates": []}
    assert runtime.meta_apply("cand-1") == {"ok": False, "status": "unavailable", "reason_code": "meta_unavailable", "reason": "meta_unavailable", "error": "meta_unavailable", "id": "cand-1"}


class _ExplodingMeta:
    def state(self):
        raise RuntimeError("state_boom")

    def start(self):
        raise RuntimeError("start_boom")

    async def stop(self):
        raise RuntimeError("stop_boom")

    def generate(self, runtime):
        del runtime
        raise RuntimeError("generate_boom")

    def apply_candidate(self, runtime, cand_id: str):
        del runtime, cand_id
        raise RuntimeError("apply_boom")


def test_multiruntime_meta_facade_preserves_explicit_failure_semantics() -> None:
    runtime = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    runtime._meta = _ExplodingMeta()

    state = runtime.meta_state()
    assert state["ok"] is False
    assert state["status"] == "degraded"
    assert state["reason_code"] == "meta_state_failed"
    assert state["error"].startswith("meta_state_failed:")

    generated = runtime.meta_generate()
    assert generated["ok"] is False
    assert generated["status"] == "degraded"
    assert generated["reason_code"] == "meta_generate_failed"
    assert generated["candidates"] == []

    applied = runtime.meta_apply("cand-9")
    assert applied["ok"] is False
    assert applied["status"] == "degraded"
    assert applied["reason_code"] == "meta_apply_failed"
    assert applied["id"] == "cand-9"
