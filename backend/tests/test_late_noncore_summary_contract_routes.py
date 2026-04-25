from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.api_routes import (
    command_center_routes,
    evolution,
    operator_command_routes,
    withdraw_all_routes,
)


class _Runtime:
    def __init__(self) -> None:
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))

    def capital_contract(self) -> dict:
        return {"contractVersion": "capital_truth_contract_v1", "ok": True}

    def capital_policy(self) -> dict:
        return {"contractVersion": "capital_policy_contract_v1", "ok": True}

    def meta_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def superstructure_command_state(self) -> dict:
        return {"ok": True, "enabled": True, "directive": "hold"}


class _CommandCenterService:
    def audit_tail(self, runtime, limit: int = 200) -> dict:
        del runtime
        return {"ok": True, "items": [{"kind": "patch"}], "limit": int(limit)}

    async def explain(self, runtime) -> dict:
        del runtime
        return {"ok": True, "text": "steady", "facts": {}, "causal": {}}


class _WithdrawAllService:
    async def state(self, runtime) -> dict:
        del runtime
        return {"ok": True, "status": "ready"}

    async def preview(self, runtime) -> dict:
        del runtime
        return {"ok": True, "status": "preview", "items": []}


def test_evolution_route_emits_summary_contract() -> None:
    runtime = _Runtime()
    body = evolution.evolution_state(rt=runtime)
    assert body["summaryContract"]["truthFamily"] == "evolution_state"
    assert body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"


def test_operator_command_state_emits_summary_contract(monkeypatch) -> None:
    runtime = _Runtime()
    monkeypatch.setattr(operator_command_routes, "get_runtime", lambda request: runtime)
    body = asyncio.run(operator_command_routes.command_state(request=SimpleNamespace()))
    assert body["summaryContract"]["truthFamily"] == "operator_command_state"
    assert body["summaryContract"]["capitalContractVersion"] == "capital_truth_contract_v1"
    assert body["summaryContract"]["capitalPolicyVersion"] == "capital_policy_contract_v1"


def test_command_center_audit_and_explain_emit_summary_contract(monkeypatch) -> None:
    runtime = _Runtime()
    runtime._command_center_service = _CommandCenterService()
    monkeypatch.setattr(command_center_routes, "get_runtime", lambda request: runtime)

    audit = asyncio.run(command_center_routes.commandcenter_audit_tail(SimpleNamespace(), limit=5))
    assert audit["summaryContract"]["truthFamily"] == "command_center_audit"
    assert audit["summaryContract"]["capitalContractVersion"] == "capital_truth_contract_v1"

    explain = asyncio.run(command_center_routes.commandcenter_explain(SimpleNamespace()))
    assert explain["summaryContract"]["truthFamily"] == "command_center_explain"
    assert explain["summaryContract"]["capitalPolicyVersion"] == "capital_policy_contract_v1"


def test_withdraw_all_state_and_preview_emit_summary_contract(monkeypatch) -> None:
    runtime = _Runtime()
    runtime._withdraw_all_service = _WithdrawAllService()
    monkeypatch.setattr(withdraw_all_routes, "_runtime", lambda request: runtime)

    async def _ok_preview(_request):
        return None

    monkeypatch.setattr(withdraw_all_routes, "_preview_request_body_error", _ok_preview)

    state_body = asyncio.run(withdraw_all_routes.withdraw_all_state(SimpleNamespace()))
    assert state_body["summaryContract"]["truthFamily"] == "withdraw_all_state"
    assert state_body["summaryContract"]["capitalContractVersion"] == "capital_truth_contract_v1"

    preview_body = asyncio.run(withdraw_all_routes.withdraw_all_preview(SimpleNamespace()))
    assert preview_body["summaryContract"]["truthFamily"] == "withdraw_all_preview"
    assert preview_body["summaryContract"]["capitalPolicyVersion"] == "capital_policy_contract_v1"
