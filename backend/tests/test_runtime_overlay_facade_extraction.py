import asyncio

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_overlay_facade import RuntimeOverlayFacade


EXTRACTED_METHODS = {
    "superstructure_state",
    "superstructure_pause",
    "superstructure_resume",
    "superstructure_command_state",
    "fioa_state",
    "fioa_set_safe_mode",
    "narrative_state",
    "narrative_subscribe",
    "narrative_unsubscribe",
}


class _FakeAuxiliaryStateService:
    def superstructure_state(self, runtime):
        return {"ok": True, "source": "aux", "chain": getattr(runtime, "chain", "")}

    def superstructure_command_state(self, runtime):
        return {"ok": True, "mode": "steady"}

    def governance_state(self, runtime):
        return {"ok": True, "mode": "strict"}

    def governance_health(self, runtime):
        return {"ok": True, "healthy": True}

    def fioa_state(self, runtime):
        return {"ok": True, "enabled": True, "mode": "strict"}

    def fioa_audit_tail(self, runtime, limit: int = 200):
        return {"ok": True, "items": [{"limit": limit}]}

    def fioa_governance_report(self, runtime, limit_audit: int = 200):
        return {"ok": True, "report": {"limit": limit_audit}}

    def narrative_state(self, runtime):
        return {"ok": True, "enabled": True, "level": "STANDARD"}

    def narrative_history(self, runtime, limit: int = 100):
        return {"ok": True, "items": [{"limit": limit}]}

    def narrative_report(self, runtime, limit: int = 100):
        return {"ok": True, "report": f"limit={limit}"}

    def narrative_set_level(self, runtime, level: str):
        return {"ok": True, "level": level}

    async def narrative_query(self, runtime, agent_id: str, query_text: str, data_level: str):
        return {"ok": True, "agent_id": agent_id, "query_text": query_text, "data_level": data_level}

    async def narrative_insights(self, runtime):
        return {"ok": True, "insights": [{"kind": "summary"}]}


class _Registry:
    def __init__(self):
        self.calls = []

    def set_suspended(self, agent_id: str, on: bool, reason: str):
        self.calls.append((agent_id, on, reason))
        return True


class _Command:
    def __init__(self):
        self.calls = []

    def set_risk_multiplier(self, m: float):
        self.calls.append(("risk", m))

    def set_exploration_cap(self, cap: float):
        self.calls.append(("exploration", cap))

    def approve(self, proposal_id: str, ttl_s: float):
        self.calls.append(("approve", proposal_id, ttl_s))


class _Super:
    def __init__(self):
        self.registry = _Registry()
        self.command = _Command()
        self.directive_calls = []
        self.safe_mode_calls = []

    def set_directive(self, directive: dict, ttl_s: float):
        self.directive_calls.append((directive, ttl_s))

    def force_safe_mode(self, ttl_s: float, reason: str):
        self.safe_mode_calls.append((ttl_s, reason))


class _FIOA:
    def __init__(self):
        self.restricted = []
        self.resumed = []
        self.safe_mode = []

    def restrict_agent(self, agent_id: str, reason: str = ""):
        self.restricted.append((agent_id, reason))

    def resume_agent(self, agent_id: str):
        self.resumed.append(agent_id)
        return True

    def _set_safe_mode(self, on: bool, ttl_s: float, reason: str):
        self.safe_mode.append((on, ttl_s, reason))


class _Narrative:
    def __init__(self):
        self.q = asyncio.Queue()
        self.unsubscribed = []

    def subscribe(self):
        return self.q

    def unsubscribe(self, q):
        self.unsubscribed.append(q)


class _DummyRuntime(RuntimeOverlayFacade):
    def __init__(self):
        self.chain = "ethereum"
        self._auxiliary_state_service = _FakeAuxiliaryStateService()
        self._super = _Super()
        self._fioa = _FIOA()
        self._inl = _Narrative()
        self.settings_calls = []

    def set_settings(self, **kwargs):
        self.settings_calls.append(kwargs)


def test_runtime_bundle_inherits_extracted_overlay_facade():
    assert issubclass(RuntimeBundle, RuntimeOverlayFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_overlay_facade_preserves_control_and_overlay_behavior():
    runtime = _DummyRuntime()

    assert runtime.superstructure_state()["chain"] == "ethereum"
    assert runtime.superstructure_pause("agent-1") is True
    assert runtime.superstructure_resume("agent-1") is True
    assert runtime.superstructure_command_state()["mode"] == "steady"
    assert runtime.superstructure_set_directive({"mode": "steady"}, ttl_s=30.0) is True
    assert runtime.superstructure_set_risk_multiplier(0.5) is True
    assert runtime.superstructure_set_exploration_cap(0.2) is True
    assert runtime.superstructure_approve("proposal-1", ttl_s=12.0) is True
    assert runtime.superstructure_force_safe_mode(ttl_s=9.0, reason="stress") is True
    assert runtime.fioa_state()["mode"] == "strict"
    assert runtime.fioa_restrict_agent("agent-1", reason="policy") is True
    assert runtime.fioa_resume_agent("agent-1") is True
    assert runtime.fioa_set_safe_mode(True, ttl_s=45.0, reason="stress") is True
    assert runtime.settings_calls[-1] == {"auto_trading": False}
    assert runtime.narrative_state()["level"] == "STANDARD"
    assert runtime.narrative_history(limit=8)["items"][0]["limit"] == 8
    assert runtime.narrative_report(limit=5)["report"] == "limit=5"
    assert runtime.narrative_set_level("VERBOSE")["level"] == "VERBOSE"
    assert asyncio.run(runtime.narrative_query("ops", "status", data_level="PUBLIC"))["data_level"] == "PUBLIC"
    assert asyncio.run(runtime.narrative_insights())["insights"][0]["kind"] == "summary"
    q = runtime.narrative_subscribe()
    assert q is runtime._inl.q
    runtime.narrative_unsubscribe(q)
    assert runtime._inl.unsubscribed == [q]


def test_runtime_overlay_facade_unavailable_defaults_remain_operator_safe():
    runtime = _DummyRuntime()
    runtime._super = None
    runtime._fioa = None
    runtime._inl = None

    assert runtime.superstructure_pause("agent-1") is False
    assert runtime.superstructure_set_directive({"mode": "steady"}) is False
    assert runtime.fioa_restrict_agent("agent-1") is False
    assert runtime.fioa_set_safe_mode(True, ttl_s=20.0, reason="stress") is False
    assert runtime.narrative_subscribe() is None
    runtime.narrative_unsubscribe(asyncio.Queue())
