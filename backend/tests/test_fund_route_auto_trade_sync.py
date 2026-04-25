from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


class _FundServiceStub:
    def summary(self, _runtime):
        return {
            "ok": True,
            "health": {"status": "ok"},
            "fundOs": {"enabled": True},
        }


class _FundRuntime:
    _fund_service = _FundServiceStub()

    def capital_truth_state(self):
        return {"ok": True, "deployableUsd": 12.0}

    def family_hardening_state(self):
        return {"ok": True, "items": [{"family": "funding_arb", "status": "eligible"}]}

    def doctrine_state(self):
        return {"optimizationObjectives": {"profit": 1.0}}

    def ledger_state(self):
        return {"balances": {"USDC": 10.0}, "tail": [], "transactions": []}

    def internal_prime_state(self):
        return {
            "borrowedUsd": 1.0,
            "capacityUsd": 250.0,
            "utilization": 0.1,
            "inventory": {"USDC": 10.0},
            "familyExposure": {"flash_arb": 1.0},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
        }


class _BrokenFundService:
    def summary(self, _runtime):
        raise RuntimeError("fund summary exploded")


class _BrokenSummaryRuntime(_FundRuntime):
    _fund_service = _BrokenFundService()


class _UnavailableRuntime:
    pass


def test_fund_read_routes_surface_auto_trade_projection(monkeypatch):
    runtime = _FundRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    for path in (
        "/api/fund/summary",
        "/api/fund/capital-truth",
        "/api/fund/family-hardening",
        "/api/fund/doctrine",
        "/api/fund/ledger",
        "/api/fund/internal-prime",
    ):
        payload = client.get(path).json()
        assert "auto_trade_recovery" in payload, path
        assert "auto_trade_gate" in payload, path
        assert payload["auto_trade_gate"]["allowed"] is True, path


def test_fund_summary_route_returns_deterministic_error_payload_when_summary_builder_raises(
    monkeypatch,
):
    runtime = _BrokenSummaryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    payload = client.get("/api/fund/summary").json()

    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "fund_summary_failed"
    assert payload["reason"] == "fund_summary_failed"
    assert payload["error"] == "fund_summary_failed"
    assert "auto_trade_recovery" in payload
    assert "auto_trade_gate" in payload
    assert "profitDoctrine" in payload


def test_fund_component_routes_return_deterministic_error_payloads_when_response_builder_raises(
    monkeypatch,
):
    runtime = _UnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")

    from victor_ai_bot.api_routes import fund_routes

    monkeypatch.setattr(
        fund_routes,
        "_component_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("component boom")),
    )

    client = TestClient(app)

    cases = {
        "/api/fund/capital-truth": ("fund_capital_truth_failed", "capitalTruth"),
        "/api/fund/family-hardening": ("fund_family_hardening_failed", "familyHardening"),
        "/api/fund/doctrine": ("fund_doctrine_failed", "doctrine"),
        "/api/fund/ledger": ("fund_ledger_failed", "ledger"),
        "/api/fund/internal-prime": ("fund_internal_prime_failed", "internalPrime"),
    }
    for path, (reason_code, component_key) in cases.items():
        payload = client.get(path).json()
        assert payload["ok"] is False, path
        assert payload["status"] == "degraded", path
        assert payload["reason_code"] == reason_code, path
        assert payload["reason"] == reason_code, path
        assert payload["error"] == reason_code, path
        assert component_key in payload, path
        assert "auto_trade_recovery" in payload, path
        assert "auto_trade_gate" in payload, path
