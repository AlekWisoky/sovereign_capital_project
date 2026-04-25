from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService


class _Command:
    def snapshot(self):
        return {"ok": True, "mode": "steady"}


class _Governance:
    def snapshot(self):
        return {"governance": {"health": {"status": "green", "score": 0.91}}}


class _Superstructure:
    def __init__(self):
        self.command = _Command()
        self.governance = _Governance()

    def state(self):
        return {"ok": True, "enabled": True, "agents": [{"id": "agent-1"}]}


class _Fioa:
    def __init__(self):
        self.audit = SimpleNamespace(tail=lambda limit: [{"limit": limit}])

    def state(self):
        return {"ok": True, "enabled": True, "mode": "strict"}

    def governance_report(self, *, limit_audit: int):
        return {"ok": True, "report": {"limit": limit_audit}}


class _Narrative:
    def state(self, runtime):
        del runtime
        return {"ok": True, "enabled": True, "level": "STANDARD"}

    def history(self, *, limit: int):
        return [{"limit": limit}]

    def narrative_audit_report(self, *, limit: int):
        return f"limit={limit}"

    def set_explanation_level(self, level: str):
        return level

    async def query(self, runtime, *, agent_id: str, query_text: str, data_level: str):
        del runtime
        return {"ok": True, "agent": agent_id, "query": query_text, "dataLevel": data_level}

    async def insights(self, runtime):
        del runtime
        return [{"kind": "summary"}]


class _Mev:
    def state(self):
        return {"ok": True, "enabled": True, "engine": "mev"}


class _BrokenAudit:
    def tail(self, limit: int):
        raise RuntimeError(f"audit_{limit}")


class _BrokenFioa:
    def __init__(self):
        self.audit = _BrokenAudit()

    def state(self):
        raise RuntimeError("fioa_state")

    def governance_report(self, *, limit_audit: int):
        raise RuntimeError(f"fioa_report_{limit_audit}")


class _BrokenNarrative:
    def state(self, runtime):
        del runtime
        raise RuntimeError("narrative_state")

    def history(self, *, limit: int):
        raise RuntimeError(f"narrative_history_{limit}")

    def narrative_audit_report(self, *, limit: int):
        raise RuntimeError(f"narrative_report_{limit}")

    def set_explanation_level(self, level: str):
        raise RuntimeError(f"narrative_set_level_{level}")

    async def query(self, runtime, *, agent_id: str, query_text: str, data_level: str):
        del runtime, agent_id, query_text, data_level
        raise RuntimeError("narrative_query")

    async def insights(self, runtime):
        del runtime
        raise RuntimeError("narrative_insights")


class _BrokenSuperstructure:
    @property
    def command(self):
        raise RuntimeError("command_state")

    @property
    def governance(self):
        raise RuntimeError("governance_state")

    def state(self):
        raise RuntimeError("superstructure_state")


class _BrokenMev:
    def state(self):
        raise RuntimeError("mev_state")


def test_auxiliary_overlay_state_service_reports_optional_surfaces():
    runtime = SimpleNamespace(
        _super=_Superstructure(),
        _fioa=_Fioa(),
        _inl=_Narrative(),
        _mev=_Mev(),
    )
    svc = AuxiliaryStateService()

    assert svc.superstructure_state(runtime)["agents"][0]["id"] == "agent-1"
    assert svc.superstructure_command_state(runtime)["mode"] == "steady"
    assert svc.governance_state(runtime)["governance"]["health"]["status"] == "green"
    assert svc.governance_health(runtime)["health"]["score"] == 0.91
    assert svc.fioa_state(runtime)["mode"] == "strict"
    assert svc.fioa_audit_tail(runtime, limit=7)["items"][0]["limit"] == 7
    assert svc.fioa_governance_report(runtime, limit_audit=5)["report"]["limit"] == 5
    assert svc.narrative_state(runtime)["level"] == "STANDARD"
    assert svc.narrative_history(runtime, limit=8)["items"][0]["limit"] == 8
    assert svc.narrative_report(runtime, limit=3)["report"] == "limit=3"
    assert svc.narrative_set_level(runtime, "VERBOSE")["level"] == "VERBOSE"
    assert asyncio.run(
        svc.narrative_query(runtime, agent_id="ops", query_text="status", data_level="PUBLIC")
    )["dataLevel"] == "PUBLIC"
    assert asyncio.run(svc.narrative_insights(runtime))["insights"][0]["kind"] == "summary"
    assert svc.mev_state(runtime)["engine"] == "mev"


def test_auxiliary_overlay_state_service_preserves_failure_payloads():
    runtime = SimpleNamespace(
        _super=_BrokenSuperstructure(),
        _fioa=_BrokenFioa(),
        _inl=_BrokenNarrative(),
        _mev=_BrokenMev(),
    )
    svc = AuxiliaryStateService()

    assert svc.superstructure_state(runtime)["error"] == "superstructure_state_failed:superstructure_state"
    assert svc.superstructure_command_state(runtime)["error"] == "command_state_failed:command_state"
    assert svc.governance_state(runtime)["error"] == "governance_state_failed:governance_state"
    assert svc.governance_health(runtime)["error"] == "governance_health_failed:governance_state"
    fioa_audit = svc.fioa_audit_tail(runtime, limit=11)
    assert fioa_audit["items"] == []
    assert fioa_audit["error"] == "fioa_audit_failed:audit_11"
    assert svc.fioa_governance_report(runtime, limit_audit=9)["error"] == "fioa_report_failed:fioa_report_9"
    narrative_history = svc.narrative_history(runtime, limit=13)
    assert narrative_history["items"] == []
    assert narrative_history["error"] == "narrative_history_failed:narrative_history_13"
    narrative_report = svc.narrative_report(runtime, limit=4)
    assert narrative_report["report"] == ""
    assert narrative_report["error"] == "narrative_report_failed:narrative_report_4"
    assert svc.narrative_set_level(runtime, "STRICT")["error"] == "narrative_set_level_failed:narrative_set_level_STRICT"
    assert asyncio.run(
        svc.narrative_query(runtime, agent_id="ops", query_text="status", data_level="PUBLIC")
    )["error"] == "narrative_query_failed:narrative_query"
    assert asyncio.run(svc.narrative_insights(runtime))["error"] == "narrative_insights_failed:narrative_insights"
    assert svc.mev_state(runtime)["error"] == "mev_state_failed:mev_state"


def test_auxiliary_overlay_state_service_returns_unavailable_defaults():
    runtime = SimpleNamespace(_super=None, _fioa=None, _inl=None, _mev=None)
    svc = AuxiliaryStateService()

    unavailable = {
        "ok": True,
        "enabled": False,
        "status": "unavailable",
        "reason_code": "unavailable",
        "reason": "unavailable",
    }
    assert svc.superstructure_state(runtime) == unavailable
    assert svc.superstructure_command_state(runtime) == unavailable
    assert svc.governance_state(runtime) == unavailable
    assert svc.governance_health(runtime) == unavailable
    assert svc.fioa_state(runtime) == unavailable
    assert svc.fioa_audit_tail(runtime) == {**unavailable, "items": []}
    assert svc.fioa_governance_report(runtime) == unavailable
    assert svc.narrative_state(runtime) == unavailable
    assert svc.narrative_history(runtime) == {**unavailable, "items": []}
    assert svc.narrative_report(runtime) == {**unavailable, "report": ""}
    narrative_unavailable = {
        "ok": False,
        "status": "unavailable",
        "reason_code": "narrative_unavailable",
        "reason": "narrative_unavailable",
        "error": "narrative_unavailable",
    }
    assert svc.narrative_set_level(runtime, "VERBOSE") == narrative_unavailable
    assert asyncio.run(svc.narrative_query(runtime, agent_id="ops", query_text="status")) == narrative_unavailable
    assert asyncio.run(svc.narrative_insights(runtime)) == narrative_unavailable
    assert svc.mev_state(runtime) == unavailable
