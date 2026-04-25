from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.advanced import router as advanced_router
from victor_ai_bot.api_routes.engine_routes import router as engine_router
from victor_ai_bot.api_routes.governance_routes import router as governance_router
from victor_ai_bot.api_routes.intelligence_routes import router as intelligence_router
from victor_ai_bot.api_routes.ops_routes import router as ops_router
from victor_ai_bot.api_routes.overlay_routes import router as overlay_router
from victor_ai_bot.api_routes.runtime_routes import router as runtime_router
from victor_ai_bot.api_routes.superstructure_routes import router as superstructure_router
from victor_ai_bot.optional_family_status import build_optional_family_status
from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_capital_facade import RuntimeCapitalFacade

ROOT = Path(__file__).resolve().parents[2]
OPTIONAL_STATUS_JSON = ROOT / "docs" / "generated" / "optional_family_status.json"


class _Threat:
    def snapshot(self) -> dict[str, Any]:
        return {"level": "low"}


class _Gov:
    def __init__(self) -> None:
        self.threat = _Threat()

    def view_intent(self, intent_id: str) -> dict[str, Any]:
        return {"ok": True, "intent_id": str(intent_id)}


class _DummyRuntime:
    def __init__(self) -> None:
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
        self._gov = _Gov()

    def capital_contract(self) -> dict[str, Any]:
        return {"contractVersion": "capital_contract_v1"}

    def capital_policy(self) -> dict[str, Any]:
        return {"policyVersion": "capital_policy_v1"}

    async def snapshot(self) -> dict[str, Any]:
        return {"ok": True, "mode": "ready"}

    def brain_state(self) -> dict[str, Any]:
        return {"ok": True, "brain": {"enabled": True}}

    def engine_state(self) -> dict[str, Any]:
        return {"ok": True, "items": [], "summary": {"engines": []}}

    def mev_state(self) -> dict[str, Any]:
        return {"ok": True, "enabled": True}

    def meta_state(self) -> dict[str, Any]:
        return {"ok": True, "enabled": True}

    def superstructure_state(self) -> dict[str, Any]:
        return {"ok": True, "stability": {"score": 0.9}}

    def governance_state(self) -> dict[str, Any]:
        return {"ok": True, "enabled": True}

    def governance_health(self) -> dict[str, Any]:
        return {"ok": True, "health": "green"}

    def fioa_state(self) -> dict[str, Any]:
        return {"ok": True, "enabled": True}

    def fioa_governance_report(self, limit_audit: int = 200) -> dict[str, Any]:
        return {"ok": True, "items": [], "limit": int(limit_audit)}

    def narrative_state(self) -> dict[str, Any]:
        return {"ok": True, "enabled": True}

    def meta_generate(self) -> dict[str, Any]:
        return {"ok": True, "candidates": [{"id": "cand-1"}]}

    async def pnl_summary(self, window: int = 100) -> dict[str, Any]:
        return {"ok": True, "window": int(window)}

    def behaveagent_state(self) -> dict[str, Any]:
        return {"ok": True, "label": "calm"}

    def blockspace_state(self) -> dict[str, Any]:
        return {"ok": True, "congestion": "low"}


class _FakeTracker:
    def state(self) -> dict[str, Any]:
        return {"ok": True, "score": 0.99}


class _FakeKds:
    def state(self) -> dict[str, Any]:
        return {"ok": True, "mode": "observe"}


class _FakeAudit:
    def latest(self, limit: int = 50) -> list[dict[str, Any]]:
        return [{"id": "x1", "ts": 1.0}][: int(limit)]

    def get(self, decision_id: str) -> dict[str, Any] | None:
        return {"id": str(decision_id)}

    def state(self) -> dict[str, Any]:
        return {"append": {"ok": True}}


class _FakeXai:
    def __init__(self) -> None:
        self.audit = _FakeAudit()


class _TxEntry:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeLedger:
    def __init__(self) -> None:
        self.tx_rows: list[dict[str, Any]] = []
        self.append_calls = 0

    def append(self, **kwargs: Any) -> _TxEntry:
        self.append_calls += 1
        metadata = dict(kwargs.get("metadata") or {})
        tx = {
            "transaction_id": f"tx-{self.append_calls}",
            "ts_ms": 1,
            "tx_type": str(kwargs["entry_type"]),
            "chain": str(kwargs["chain"]),
            "receipt_id": "",
            "lines": [
                {
                    "account": f"asset:{kwargs['asset']}",
                    "asset": str(kwargs["asset"]),
                    "amount": float(kwargs["amount"]),
                    "family": str(kwargs.get("family") or ""),
                    "venue": str(kwargs.get("venue") or ""),
                    "note": str(kwargs.get("note") or ""),
                },
                {
                    "account": "equity:offset",
                    "asset": "USD",
                    "amount": float(-float(kwargs["amount"])),
                    "family": str(kwargs.get("family") or ""),
                    "venue": str(kwargs.get("venue") or ""),
                    "note": f"offset:{str(kwargs.get('note') or kwargs['entry_type'])}",
                },
            ],
            "metadata": {
                "event_key": str(metadata.get("event_key") or ""),
                "entry_type": str(kwargs["entry_type"]),
                "asset": str(kwargs["asset"]),
                "venue": str(kwargs.get("venue") or ""),
                "family": str(kwargs.get("family") or ""),
                "note": str(kwargs.get("note") or ""),
            },
        }
        self.tx_rows.append(tx)
        return _TxEntry(
            {
                "ts_ms": 1,
                "entry_type": str(kwargs["entry_type"]),
                "asset": str(kwargs["asset"]),
                "amount": float(kwargs["amount"]),
                "venue": str(kwargs.get("venue") or ""),
                "chain": str(kwargs["chain"]),
                "family": str(kwargs.get("family") or ""),
                "note": str(kwargs.get("note") or ""),
                "transaction_id": tx["transaction_id"],
                "receipt_id": "",
                "metadata": dict(tx["metadata"]),
            }
        )

    def transactions_all(self) -> list[dict[str, Any]]:
        return list(self.tx_rows)


class _FlakyRepo:
    def __init__(self) -> None:
        self.calls = 0

    def append(self, *, chain: str, payload: dict[str, Any]) -> None:
        self.calls += 1
        raise RuntimeError("repo_write_failed")

    def all_transactions(self, *, chain: str) -> list[dict[str, Any]]:
        return []


class _CapitalFacadeHarness(RuntimeCapitalFacade):
    def __init__(self) -> None:
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
        self._ledger = _FakeLedger()
        self._ledger_repo = _FlakyRepo()
        self._auxiliary_state_service = SimpleNamespace(
            wealth_goal_state=lambda _runtime: {"ok": True}
        )


def _app_with_runtime(runtime: _DummyRuntime) -> FastAPI:
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(engine_router)
    app.include_router(governance_router)
    app.include_router(superstructure_router)
    app.include_router(overlay_router)
    app.include_router(ops_router)
    app.include_router(runtime_router)
    app.include_router(advanced_router)
    app.include_router(intelligence_router)
    app.dependency_overrides[RuntimeBundle.dep] = lambda: runtime
    return app


def test_noncore_summary_routes_emit_canonical_summary_contract(monkeypatch) -> None:
    runtime = _DummyRuntime()
    monkeypatch.setattr(
        "victor_ai_bot.api_routes.intelligence_routes.reliability_tracker",
        lambda **_: _FakeTracker(),
    )
    monkeypatch.setattr(
        "victor_ai_bot.api_routes.intelligence_routes.kds_engine",
        lambda **_: _FakeKds(),
    )
    monkeypatch.setattr(
        "victor_ai_bot.api_routes.intelligence_routes.xai_engine",
        lambda **_: _FakeXai(),
    )
    client = TestClient(_app_with_runtime(runtime))

    checks = {
        "/api/engines/state": "engine_state",
        "/api/governance/threat_status": "governance_threat",
        "/api/org/state": "superstructure_state",
        "/api/fioa/state": "fioa_state",
        "/api/mev/state": "mev_state",
        "/api/state": "runtime_state",
        "/api/meta/candidates": "meta_candidates",
        "/api/reliability/state": "reliability_state",
        "/api/kds/state": "kds_state",
        "/api/xai/latest": "xai_latest",
        "/api/inl/daily_digest": "inl_daily_digest",
    }
    for path, family in checks.items():
        body = client.get(path).json()
        assert body["summaryContract"]["truthFamily"] == family, path
        assert (
            body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
        ), path


def test_runtime_capital_facade_dedupes_retry_after_repo_failure() -> None:
    facade = _CapitalFacadeHarness()

    first = facade.record_ledger_entry(
        entry_type="capital_control",
        asset="USD",
        amount=5.0,
        venue="TREASURY",
        family="ops",
        note="retry-proof",
    )
    assert first == {}
    assert facade._ledger.append_calls == 1
    assert facade._ledger_repo.calls == 1

    second = facade.record_ledger_entry(
        entry_type="capital_control",
        asset="USD",
        amount=5.0,
        venue="TREASURY",
        family="ops",
        note="retry-proof",
    )
    assert second["entry_type"] == "capital_control"
    assert second["metadata"]["event_key"]
    assert facade._ledger.append_calls == 1


def test_optional_family_status_report_is_generated_and_classified() -> None:
    payload = json.loads(OPTIONAL_STATUS_JSON.read_text())
    live = build_optional_family_status()

    assert payload == live
    assert payload["contractVersion"] == "optional_family_status_v2"
    assert payload["classificationEngine"] == "automatic_runtime_reachability_v3"
    assert payload["statusDerivation"] == [
        "mountedRoutes",
        "runtimeInitialization",
        "importReachability",
        "gatingConditions",
    ]

    for row in payload["families"]:
        evidence = row["evidence"]
        ungated_runtime = [
            item
            for item in evidence["runtimeInitialization"]
            if item not in set(evidence["gatingConditions"])
        ]
        if evidence["mountedRoutes"] or ungated_runtime:
            expected_status = "live"
        elif evidence["runtimeInitialization"] or evidence["gatingConditions"]:
            expected_status = "staged"
        elif evidence["importReachability"]:
            expected_status = "shadow"
        else:
            expected_status = "dead"
        assert row["status"] == expected_status

    families = {row["family"]: row for row in payload["families"]}
    assert families["aqe"]["evidence"]["runtimeInitialization"]
    assert families["omar"]["evidence"]["gatingConditions"]
    assert families["market_making"]["evidence"]["importReachability"]
    assert families["simulator"]["evidence"]["mountedRoutes"] == []
