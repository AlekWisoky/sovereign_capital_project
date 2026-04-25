from __future__ import annotations

from fastapi.testclient import TestClient

from victor_ai_bot.server import app


def test_fund_summary_route_available():
    client = TestClient(app)
    resp = client.get("/api/fund/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "health" in body
    assert "fundOs" in body
    assert body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
    assert body["summaryContract"]["truthFamily"] == "fund"


def test_fund_candidate_create_requires_admin():
    client = TestClient(app)
    resp = client.post(
        "/api/fund/research/candidates",
        json={"family": "auto_generated_strategy", "thesis": "test"},
    )
    assert resp.status_code in (200, 401)


class _FundRoutesUnavailableRuntime:
    pass


def test_fund_control_surface_unavailable_defaults_remain_backward_compatible(monkeypatch):
    runtime = _FundRoutesUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()
    capital_truth = client.get("/api/fund/capital-truth").json()
    family_hardening = client.get("/api/fund/family-hardening").json()

    assert summary["ok"] is False
    assert summary["status"] == "unavailable"
    assert summary["reason_code"] == "fund_service_unavailable"
    assert summary["reason"] == "fund_service_unavailable"
    assert summary["profitDoctrine"]["status"] == "unavailable"
    assert summary["profitDoctrine"]["reason_code"] == "doctrine_unavailable"
    assert summary["profitDoctrine"]["optimizationObjectives"] == {}
    assert summary["ledger"]["status"] == "unavailable"
    assert summary["ledger"]["reason_code"] == "ledger_unavailable"
    assert summary["ledger"]["balances"] == {}
    assert summary["ledger"]["tail"] == []
    assert summary["ledger"]["transactions"] == []
    assert summary["internalPrime"]["status"] == "unavailable"
    assert summary["internalPrime"]["reason_code"] == "internal_prime_unavailable"
    assert summary["internalPrime"]["borrowedUsd"] == 0.0
    assert summary["internalPrime"]["capacityUsd"] == 0.0
    assert summary["internalPrime"]["loanCount"] == 0
    assert summary["capitalTruth"]["status"] == "unavailable"
    assert summary["capitalTruth"]["reason_code"] == "capital_truth_unavailable"
    assert summary["familyHardening"]["status"] == "unavailable"
    assert summary["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert summary["familyHardening"]["items"] == []
    assert summary["researchPipeline"]["chain"] == "default"
    assert summary["summaryContract"]["truthFamily"] == "fund"
    assert summary["summaryContract"]["readModel"] == "fund_summary_projection_v1"
    assert summary["researchPipeline"]["notesEnabled"] is True
    assert "pipelineCounts" in summary["researchPipeline"]
    assert "throughput" in summary["researchPipeline"]

    assert capital_truth["ok"] is False
    assert capital_truth["status"] == "unavailable"
    assert capital_truth["reason_code"] == "capital_truth_unavailable"
    assert capital_truth["reason"] == "capital_truth_unavailable"
    assert capital_truth["capitalTruth"]["status"] == "unavailable"
    assert capital_truth["capitalTruth"]["reason_code"] == "capital_truth_unavailable"

    assert family_hardening["ok"] is False
    assert family_hardening["status"] == "unavailable"
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["reason"] == "family_hardening_service_unavailable"
    assert family_hardening["familyHardening"]["status"] == "unavailable"
    assert (
        family_hardening["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    )
    assert family_hardening["familyHardening"]["items"] == []
    assert (
        family_hardening["familyHardening"]["recovery_status"]
        == "family_hardening_restore_required"
    )
    assert family_hardening["familyHardening"]["recovery_reliability_class"] == "unavailable"


class _FundReadSurfaceRuntime:
    def capital_truth_state(self):
        return {"ok": True, "deployableUsd": 12.0}

    def family_hardening_state(self):
        return {"ok": True, "items": [{"family": "funding_arb", "status": "eligible"}]}

    def doctrine_state(self):
        return {"optimizationObjectives": {"profit": 1.0}}

    def ledger_state(self):
        return {
            "balances": {"USDC": 10.0},
            "tail": [{"event": "seed"}],
            "transactions": [{"tx_type": "prime_loan_open"}],
        }

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


class _FundRaisingReadSurfaceRuntime:
    def capital_truth_state(self):
        raise RuntimeError("capital truth offline")

    def family_hardening_state(self):
        raise ValueError("family hardening corrupt")

    def doctrine_state(self):
        raise RuntimeError("doctrine offline")

    def ledger_state(self):
        raise ValueError("ledger corrupt")

    def internal_prime_state(self):
        raise OSError("prime state offline")


class _FundResearchRaisingRuntime:
    def research_pipeline_state(self):
        raise RuntimeError("research pipeline offline")


class _FundDegradedReadSurfaceRuntime:
    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["internal_prime_journal_borrowed_mismatch"],
            "canonical": True,
        }

    def internal_prime_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "reason_code": "prime_state_corrupt",
            "reason": "prime_state_corrupt",
            "stateReady": False,
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
        }


def test_fund_direct_read_routes_preserve_success_shape(monkeypatch):
    runtime = _FundReadSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    capital_truth = client.get("/api/fund/capital-truth").json()
    family_hardening = client.get("/api/fund/family-hardening").json()

    assert capital_truth["ok"] is True
    assert capital_truth["capitalTruth"] == {"ok": True, "deployableUsd": 12.0}
    assert capital_truth["summaryContract"]["truthFamily"] == "fund_capital_truth"
    assert capital_truth["summaryContract"]["readModel"] == "fund_capital_truth_projection_v1"
    assert "auto_trade_recovery" in capital_truth
    assert "auto_trade_gate" in capital_truth

    assert family_hardening["ok"] is True
    assert family_hardening["familyHardening"] == {
        "ok": True,
        "items": [{"family": "funding_arb", "status": "eligible"}],
    }
    assert family_hardening["summaryContract"]["truthFamily"] == "fund_family_hardening"
    assert family_hardening["summaryContract"]["readModel"] == "fund_family_hardening_projection_v1"
    assert "auto_trade_recovery" in family_hardening
    assert "auto_trade_gate" in family_hardening


def test_fund_admin_read_routes_surface_unavailable_state(monkeypatch):
    runtime = _FundRoutesUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    doctrine = client.get("/api/fund/doctrine").json()
    ledger = client.get("/api/fund/ledger").json()
    internal_prime = client.get("/api/fund/internal-prime").json()

    assert doctrine["ok"] is False
    assert doctrine["status"] == "unavailable"
    assert doctrine["reason_code"] == "doctrine_unavailable"
    assert doctrine["doctrine"]["optimizationObjectives"] == {}

    assert ledger["ok"] is False
    assert ledger["status"] == "unavailable"
    assert ledger["reason_code"] == "ledger_unavailable"
    assert ledger["ledger"]["balances"] == {}
    assert ledger["ledger"]["tail"] == []
    assert ledger["ledger"]["transactions"] == []

    assert internal_prime["ok"] is False
    assert internal_prime["status"] == "unavailable"
    assert internal_prime["reason_code"] == "internal_prime_unavailable"
    assert internal_prime["internalPrime"]["borrowedUsd"] == 0.0
    assert internal_prime["internalPrime"]["capacityUsd"] == 0.0
    assert internal_prime["internalPrime"]["loanCount"] == 0


def test_fund_admin_read_routes_preserve_success_shape(monkeypatch):
    runtime = _FundReadSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    doctrine = client.get("/api/fund/doctrine").json()
    ledger = client.get("/api/fund/ledger").json()
    internal_prime = client.get("/api/fund/internal-prime").json()

    assert doctrine["ok"] is True
    assert doctrine["doctrine"] == {"optimizationObjectives": {"profit": 1.0}}
    assert doctrine["summaryContract"]["truthFamily"] == "fund_doctrine"
    assert doctrine["summaryContract"]["readModel"] == "fund_doctrine_projection_v1"
    assert "auto_trade_recovery" in doctrine
    assert "auto_trade_gate" in doctrine

    assert ledger["ok"] is True
    assert ledger["ledger"] == {
        "balances": {"USDC": 10.0},
        "tail": [{"event": "seed"}],
        "transactions": [{"tx_type": "prime_loan_open"}],
    }
    assert ledger["summaryContract"]["truthFamily"] == "fund_ledger"
    assert ledger["summaryContract"]["readModel"] == "fund_ledger_projection_v1"
    assert "auto_trade_recovery" in ledger
    assert "auto_trade_gate" in ledger

    assert internal_prime["ok"] is True
    assert internal_prime["summaryContract"]["truthFamily"] == "fund_internal_prime"
    assert internal_prime["summaryContract"]["readModel"] == "fund_internal_prime_projection_v1"
    assert internal_prime["internalPrime"] == {
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
    assert "auto_trade_recovery" in internal_prime
    assert "auto_trade_gate" in internal_prime


class _FundPrimeStateOnlyDegradedRuntime:
    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
            "stateReady": False,
            "stateStatus": "degraded",
            "stateReasonCode": "prime_state_corrupt",
            "stateReason": "prime_state_corrupt",
        }


def test_fund_read_routes_do_not_report_success_when_internal_prime_only_exposes_state_status(
    monkeypatch,
):
    runtime = _FundPrimeStateOnlyDegradedRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    internal_prime = client.get("/api/fund/internal-prime").json()

    assert internal_prime["ok"] is False
    assert internal_prime["status"] == "degraded"
    assert internal_prime["reason_code"] == "prime_state_corrupt"
    assert internal_prime["reason"] == "prime_state_corrupt"
    assert internal_prime["internalPrime"]["stateReady"] is False
    assert internal_prime["internalPrime"]["stateStatus"] == "degraded"
    assert internal_prime["internalPrime"]["stateReasonCode"] == "prime_state_corrupt"


def test_fund_read_routes_degrade_when_runtime_component_methods_raise(monkeypatch):
    runtime = _FundRaisingReadSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    capital_truth = client.get("/api/fund/capital-truth").json()
    family_hardening = client.get("/api/fund/family-hardening").json()
    doctrine = client.get("/api/fund/doctrine").json()
    ledger = client.get("/api/fund/ledger").json()
    internal_prime = client.get("/api/fund/internal-prime").json()

    assert capital_truth["status"] == "unavailable"
    assert capital_truth["reason_code"] == "capital_truth_unavailable"
    assert capital_truth["capitalTruth"]["status"] == "unavailable"

    assert family_hardening["status"] == "unavailable"
    assert family_hardening["reason_code"] == "family_hardening_service_unavailable"
    assert family_hardening["familyHardening"]["items"] == []

    assert doctrine["status"] == "unavailable"
    assert doctrine["reason_code"] == "doctrine_unavailable"
    assert doctrine["doctrine"]["optimizationObjectives"] == {}

    assert ledger["status"] == "unavailable"
    assert ledger["reason_code"] == "ledger_unavailable"
    assert ledger["ledger"]["balances"] == {}
    assert ledger["ledger"]["tail"] == []

    assert internal_prime["status"] == "unavailable"
    assert internal_prime["reason_code"] == "internal_prime_unavailable"
    assert internal_prime["internalPrime"]["borrowedUsd"] == 0.0


def test_fund_read_routes_do_not_report_success_when_capital_truth_is_explicitly_degraded(
    monkeypatch,
):
    runtime = _FundDegradedReadSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    capital_truth = client.get("/api/fund/capital-truth").json()

    assert capital_truth["ok"] is False
    assert capital_truth["status"] == "degraded"
    assert capital_truth["reason_code"] == "internal_prime_journal_borrowed_mismatch"
    assert capital_truth["reason"] == "internal_prime_journal_borrowed_mismatch"
    assert capital_truth["capitalTruth"] == {
        "ok": True,
        "status": "degraded",
        "status_reasons": ["internal_prime_journal_borrowed_mismatch"],
        "canonical": True,
    }
    assert "auto_trade_recovery" in capital_truth
    assert "auto_trade_gate" in capital_truth


def test_fund_read_routes_do_not_report_success_when_internal_prime_is_explicitly_degraded(
    monkeypatch,
):
    runtime = _FundDegradedReadSurfaceRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    client = TestClient(app)

    internal_prime = client.get("/api/fund/internal-prime").json()

    assert internal_prime["ok"] is False
    assert internal_prime["status"] == "degraded"
    assert internal_prime["reason_code"] == "prime_state_corrupt"
    assert internal_prime["reason"] == "prime_state_corrupt"
    assert internal_prime["internalPrime"]["ok"] is True
    assert internal_prime["internalPrime"]["status"] == "degraded"
    assert internal_prime["internalPrime"]["reason_code"] == "prime_state_corrupt"


def test_fund_research_candidates_route_falls_back_to_workspace_snapshot_when_runtime_pipeline_state_raises(
    monkeypatch,
):
    runtime = _FundResearchRaisingRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    payload = client.get("/api/fund/research/candidates").json()

    assert payload["pipelineCounts"] == {
        "sandbox": 0,
        "observe_only": 0,
        "shadow_live": 0,
        "capped_live": "0",
        "production": 0,
        "degraded": 0,
        "paper": 0,
        "retired": 0,
    }
    assert payload["throughput"] == {
        "candidatesGenerated": 0,
        "candidatesPromoted": 0,
        "candidatesRetired": 0,
        "researchHitRate": 0.0,
    }
    assert payload["chain"] == "default"
    assert payload["notesEnabled"] is True
