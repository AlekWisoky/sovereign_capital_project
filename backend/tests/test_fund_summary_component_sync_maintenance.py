from __future__ import annotations

from fastapi.testclient import TestClient


from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.capital_recovery_repository import (
    CapitalRecoveryRepository,
)
from victor_ai_bot.runtime_services.fund_service import FundService
from victor_ai_bot.server import app


class _FundSummaryDegradedRuntime:
    _fund_service = FundService()

    def capital_engine_state(self):
        raise RuntimeError("capital engine offline")

    def engine_state(self):
        raise KeyError("engine state missing")

    def telemetry_summary(self):
        raise ValueError("telemetry malformed")

    def strategy_scorecards_state(self):
        raise TypeError("scorecards malformed")

    def drawdown_state(self):
        raise RuntimeError("drawdown offline")

    def kill_switch_state(self):
        raise OSError("kill switch unreadable")

    def endpoint_quality_state(self):
        raise RuntimeError("endpoint quality offline")

    def endpoint_universe_state(self):
        raise ValueError("endpoint universe malformed")

    def route_quality_state(self):
        raise TypeError("route quality malformed")

    def research_pipeline_state(self):
        raise RuntimeError("research pipeline offline")

    def doctrine_state(self):
        raise RuntimeError("doctrine store offline")

    def ledger_state(self):
        raise ValueError("ledger corrupt")

    def internal_prime_state(self):
        raise OSError("prime snapshot unavailable")

    def capital_truth_state(self):
        raise KeyError("capital truth missing")

    def family_hardening_state(self):
        raise TypeError("family controls malformed")


class _FundSummarySuccessRuntime:
    _fund_service = FundService()

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
            "loanCount": 0,
        }

    def capital_truth_state(self):
        return {"ok": True, "deployableUsd": 12.0}

    def family_hardening_state(self):
        return {"ok": True, "items": [{"family": "funding_arb", "status": "eligible"}]}


def test_fund_summary_degrades_component_states_closed_when_runtime_component_reads_fail(
    monkeypatch,
):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryDegradedRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["capital"] == {}
    assert summary["alphaPlatform"]["scorecards"] == {"engines": []}
    assert summary["health"]["fundStage"] == "internal_capital"
    assert summary["researchPipeline"]["chain"] == "default"
    assert summary["researchPipeline"]["notesEnabled"] is True
    assert "pipelineCounts" in summary["researchPipeline"]
    assert "throughput" in summary["researchPipeline"]
    assert summary["executionQuality"]["endpointQuality"] == {}
    assert summary["executionQuality"]["endpointUniverse"] == {}
    assert summary["executionQuality"]["routeQuality"] == {}

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
    assert summary["familyHardening"]["reason_codes"] == ["family_hardening_service_unavailable"]
    assert summary["familyHardening"]["items"] == []
    assert summary["familyHardening"]["recovery_status"] == "family_hardening_restore_required"
    assert (
        summary["familyHardening"]["recovery_reason_code"] == "family_hardening_service_unavailable"
    )
    assert summary["familyHardening"]["recovery_next_action"] == "restore_family_hardening"
    assert summary["familyHardening"]["recovery_history_status"] == "degraded"
    assert summary["familyHardening"]["recovery_reliability_class"] == "unavailable"


def test_fund_summary_preserves_component_success_payloads(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _FundSummarySuccessRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["profitDoctrine"] == {"optimizationObjectives": {"profit": 1.0}}
    assert summary["ledger"] == {
        "balances": {"USDC": 10.0},
        "tail": [{"event": "seed"}],
        "transactions": [{"tx_type": "prime_loan_open"}],
    }
    assert summary["internalPrime"] == {
        "borrowedUsd": 1.0,
        "capacityUsd": 250.0,
        "utilization": 0.1,
        "inventory": {"USDC": 10.0},
        "familyExposure": {"flash_arb": 1.0},
        "openLoans": [],
        "loanCount": 0,
    }
    assert summary["capitalTruth"] == {"ok": True, "deployableUsd": 12.0}
    assert summary["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"
    assert summary["familyHardening"] == {
        "ok": True,
        "items": [{"family": "funding_arb", "status": "eligible"}],
    }


class _FundSummaryPrimeMismatchRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["internal_prime_journal_borrowed_mismatch"],
            "reconciliation": {
                "internal_prime_journal": {
                    "ok": False,
                    "status": "degraded",
                    "reasons": ["internal_prime_journal_borrowed_mismatch"],
                }
            },
        }


def test_fund_summary_health_fails_closed_when_capital_truth_reports_prime_journal_mismatch(
    monkeypatch,
):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryPrimeMismatchRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["capitalTruth"]["status"] == "degraded"
    assert summary["health"]["capitalTruthStatus"] == "degraded"
    assert summary["health"]["capitalTruthReasonCodes"] == [
        "internal_prime_journal_borrowed_mismatch"
    ]
    assert summary["health"]["internalPrimeReasonCodes"] == [
        "internal_prime_journal_borrowed_mismatch"
    ]
    assert summary["health"]["capitalReady"] is False
    assert summary["health"]["internalPrimeReady"] is False


class _FundSummaryPrimeStateCorruptRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "loanCount": 0,
            "stateReady": False,
            "stateStatus": "unavailable",
            "stateReasonCode": "prime_state_corrupt",
            "stateReason": "prime_state_corrupt",
        }

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["prime_state_corrupt"],
        }


def test_fund_summary_health_fails_closed_when_internal_prime_state_is_corrupt(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryPrimeStateCorruptRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["capitalTruth"]["status"] == "degraded"
    assert "prime_state_corrupt" in set(summary["capitalTruth"]["status_reasons"])
    assert summary["health"]["internalPrimeReasonCodes"] == ["prime_state_corrupt"]
    assert summary["health"]["internalPrimeReady"] is False


class _FundSummaryPrimeStateOnlyCorruptRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "loanCount": 0,
            "stateReady": False,
            "stateStatus": "degraded",
            "stateReasonCode": "prime_state_corrupt",
            "stateReason": "prime_state_corrupt",
        }

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "ok",
            "deployableUsd": 12.0,
        }


def test_fund_summary_health_fails_closed_when_internal_prime_state_is_degraded_but_capital_truth_is_stale_ok(
    monkeypatch,
):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryPrimeStateOnlyCorruptRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["capitalTruth"]["status"] == "ok"
    assert summary["health"]["capitalTruthReasonCodes"] == []
    assert summary["health"]["internalPrimeReasonCodes"] == ["prime_state_corrupt"]
    assert summary["health"]["internalPrimeReady"] is False
    assert summary["health"]["holdReasonCode"] == "prime_state_corrupt"
    assert summary["health"]["holdReasonCodes"] == ["prime_state_corrupt"]
    assert summary["health"]["suggestedNextAction"] == "repair_internal_prime_accounting"
    assert summary["health"]["recoveryStatus"] == "internal_prime_reconciliation_required"
    assert summary["health"]["recoveryReasonCode"] == "prime_state_corrupt"
    assert summary["health"]["recoveryReasonCodes"] == ["prime_state_corrupt"]
    assert summary["health"]["recoveryNextAction"] == "repair_internal_prime_accounting"


class _FundSummaryFamilyHardeningUnavailableRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def family_hardening_state(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "family_hardening_service_unavailable",
            "reason": "family_hardening_service_unavailable",
            "items": [],
        }


def test_fund_summary_health_fails_closed_when_family_hardening_service_is_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryFamilyHardeningUnavailableRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["familyHardening"]["status"] == "unavailable"
    assert summary["health"]["familyHardeningStatus"] == "unavailable"
    assert summary["health"]["familyHardeningReasonCodes"] == [
        "family_hardening_service_unavailable"
    ]
    assert summary["health"]["familyHardeningReady"] is False
    assert summary["health"]["holdReasonCode"] == "family_hardening_service_unavailable"
    assert summary["health"]["holdReasonCodes"] == ["family_hardening_service_unavailable"]
    assert summary["health"]["suggestedNextAction"] == "restore_family_hardening"
    assert summary["health"]["recoveryStatus"] == "family_hardening_restore_required"
    assert summary["health"]["recoveryReasonCode"] == "family_hardening_service_unavailable"
    assert summary["health"]["recoveryReasonCodes"] == ["family_hardening_service_unavailable"]
    assert summary["health"]["recoveryNextAction"] == "restore_family_hardening"
    assert summary["health"]["recoveryHistoryComponent"] == "family_hardening"
    assert summary["health"]["recoveryHistoryStatus"] == "degraded"
    assert summary["health"]["familyHardeningReliabilityClass"] == "unavailable"
    assert (
        summary["health"]["familyHardeningReliabilityReasonCode"]
        == "family_hardening_reliability_unavailable"
    )
    assert summary["health"]["recoveryReliabilityComponent"] == "family_hardening"
    assert summary["health"]["recoveryReliabilityClass"] == "unavailable"
    assert summary["health"]["recoveryReliabilityReasonCode"] == "recovery_reliability_unavailable"
    assert summary["health"]["recoveryReliabilityNextAction"] == "restore_family_hardening"


class _FundSummaryDrawdownHoldRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def drawdown_state(self):
        return {
            "drawdownPct": 7.25,
            "hardStop": {
                "active": True,
                "reason_codes": ["drawdown_hard_stop"],
            },
        }


class _FundSummaryCapitalHoldRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["capital_truth_degraded"],
        }


def test_fund_summary_health_surfaces_global_execution_hold_summary_for_drawdown_hard_stop(
    monkeypatch,
):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryDrawdownHoldRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["globalExecutionBlocked"] is True
    assert summary["health"]["globalExecutionReasonCodes"] == ["drawdown_hard_stop"]
    assert summary["health"]["holdReasonCode"] == "drawdown_hard_stop"
    assert summary["health"]["holdReasonCodes"] == ["drawdown_hard_stop"]
    assert summary["health"]["suggestedNextAction"] == "reduce_drawdown_and_clear_hard_stop"
    assert summary["health"]["recoveryReady"] is False
    assert summary["health"]["recoveryStatus"] == "global_execution_blocked"
    assert summary["health"]["recoveryReasonCode"] == "drawdown_hard_stop"
    assert summary["health"]["recoveryReasonCodes"] == ["drawdown_hard_stop"]
    assert summary["health"]["recoveryNextAction"] == "reduce_drawdown_and_clear_hard_stop"


def test_fund_summary_health_surfaces_capital_truth_hold_summary_when_execution_is_not_globally_blocked(
    monkeypatch,
):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryCapitalHoldRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["globalExecutionBlocked"] is False
    assert summary["health"]["globalExecutionReasonCodes"] == []
    assert summary["health"]["holdReasonCode"] == "capital_truth_degraded"
    assert summary["health"]["holdReasonCodes"] == ["capital_truth_degraded"]
    assert summary["health"]["suggestedNextAction"] == "restore_capital_truth"
    assert summary["health"]["recoveryReady"] is False
    assert summary["health"]["recoveryStatus"] == "capital_truth_restore_required"
    assert summary["health"]["recoveryReasonCode"] == "capital_truth_degraded"
    assert summary["health"]["recoveryReasonCodes"] == ["capital_truth_degraded"]
    assert summary["health"]["recoveryNextAction"] == "restore_capital_truth"


class _FundSummaryCapitalUnavailableRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": False,
            "status": "unavailable",
            "reason_code": "capital_truth_unavailable",
            "reason": "capital_truth_unavailable",
        }


def test_fund_summary_health_fails_closed_when_capital_truth_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryCapitalUnavailableRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["capitalTruth"]["status"] == "unavailable"
    assert summary["capitalTruth"]["reason_code"] == "capital_truth_unavailable"
    assert summary["health"]["capitalTruthStatus"] == "unavailable"
    assert summary["health"]["capitalTruthReasonCodes"] == ["capital_truth_unavailable"]
    assert summary["health"]["holdReasonCode"] == "capital_truth_unavailable"
    assert summary["health"]["holdReasonCodes"] == ["capital_truth_unavailable"]
    assert summary["health"]["suggestedNextAction"] == "restore_capital_truth"
    assert summary["health"]["recoveryReady"] is False
    assert summary["health"]["recoveryStatus"] == "capital_truth_restore_required"
    assert summary["health"]["recoveryReasonCode"] == "capital_truth_unavailable"
    assert summary["health"]["recoveryReasonCodes"] == ["capital_truth_unavailable"]
    assert summary["health"]["recoveryNextAction"] == "restore_capital_truth"
    assert summary["health"]["capitalReady"] is False


class _FundSummaryInternalPrimeRecentDisputeRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["internal_prime_journal_open_loan_count_mismatch"],
            "ts_ms": 500_000_000,
            "ledger": {
                "last_ts_ms": 500_000_000,
                "transactions": [
                    {
                        "tx_type": "prime_loan_open",
                        "ts_ms": 500_000_000 - (3 * 24 * 60 * 60 * 1000),
                    },
                    {
                        "tx_type": "prime_loan_disputed",
                        "ts_ms": 500_000_000 - (5 * 60 * 1000),
                    },
                ],
            },
            "reconciliation": {
                "internal_prime_journal": {
                    "ok": False,
                    "status": "degraded",
                    "reasons": ["internal_prime_journal_open_loan_count_mismatch"],
                    "observed": {
                        "borrowed_usd": 1.0,
                        "open_loan_count": 1,
                        "family_exposure": {"flash_arb": 1.0},
                    },
                }
            },
        }


def test_fund_summary_health_treats_recent_prime_dispute_as_fresh_internal_prime_activity(
    monkeypatch,
):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryInternalPrimeRecentDisputeRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert str(summary["health"]["internalPrimeJournalLastTsMs"]) == "499700000"
    assert summary["health"]["internalPrimeFreshnessClass"] == "current"
    assert summary["health"]["internalPrimeFreshnessReasonCodes"] == []
    assert summary["health"]["recoveryFreshnessClass"] == "current"
    assert summary["health"]["recoveryFreshnessReasonCodes"] == []
    assert summary["health"]["recoveryFreshnessNextAction"] == ""


class _FundSummaryCapitalFreshnessRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["capital_truth_degraded"],
            "ts_ms": 1_000_000,
            "ledger": {"last_ts_ms": 1_000_000 - (30 * 60 * 60 * 1000)},
        }


def test_fund_summary_health_surfaces_capital_truth_freshness_for_stale_recovery(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _FundSummaryCapitalFreshnessRuntime(), raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["capitalTruthFreshnessClass"] == "stale"
    assert summary["health"]["capitalTruthFreshnessReasonCodes"] == [
        "capital_truth_freshness_stale"
    ]
    assert summary["health"]["recoveryFreshnessClass"] == "stale"
    assert summary["health"]["recoveryFreshnessReasonCode"] == "capital_truth_freshness_stale"
    assert summary["health"]["recoveryFreshnessReasonCodes"] == ["capital_truth_freshness_stale"]
    assert summary["health"]["recoveryFreshnessNextAction"] == "refresh_capital_truth_snapshot"


class _FundSummaryInternalPrimeFreshnessRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "status_reasons": ["internal_prime_journal_borrowed_mismatch"],
            "ts_ms": 400_000_000,
            "ledger": {
                "last_ts_ms": 400_000_000,
                "transactions": [
                    {
                        "tx_type": "prime_loan_open",
                        "ts_ms": 400_000_000 - (2 * 24 * 60 * 60 * 1000),
                    }
                ],
            },
            "reconciliation": {
                "internal_prime_journal": {
                    "ok": False,
                    "status": "degraded",
                    "reasons": ["internal_prime_journal_borrowed_mismatch"],
                    "observed": {
                        "borrowed_usd": 1.0,
                        "open_loan_count": 1,
                        "family_exposure": {"flash_arb": 1.0},
                    },
                }
            },
        }


def test_fund_summary_health_surfaces_internal_prime_reconciliation_freshness(monkeypatch):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryInternalPrimeFreshnessRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["internalPrimeFreshnessClass"] == "stale"
    assert summary["health"]["internalPrimeFreshnessReasonCodes"] == [
        "internal_prime_reconciliation_freshness_stale"
    ]
    assert summary["health"]["recoveryFreshnessClass"] == "stale"
    assert (
        summary["health"]["recoveryFreshnessReasonCode"]
        == "internal_prime_reconciliation_freshness_stale"
    )
    assert summary["health"]["recoveryFreshnessReasonCodes"] == [
        "internal_prime_reconciliation_freshness_stale"
    ]
    assert (
        summary["health"]["recoveryFreshnessNextAction"] == "refresh_internal_prime_reconciliation"
    )


from victor_ai_bot.persistence.db import PersistenceDB


class _FundSummaryPersistentCapitalHistoryRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def __init__(self, db_path: str):
        self._db = PersistenceDB(db_path)
        self._capital_truth_payload = {
            "ok": False,
            "status": "unavailable",
            "reason_code": "capital_truth_unavailable",
            "reason": "capital_truth_unavailable",
            "ts_ms": 1_700_000_000_000,
        }

    def capital_truth_state(self):
        return dict(self._capital_truth_payload)


def test_fund_summary_persists_capital_truth_recovery_history_across_recovery_cycle(
    monkeypatch, tmp_path
):
    runtime = _FundSummaryPersistentCapitalHistoryRuntime(str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    first = client.get("/api/fund/summary").json()
    assert first["health"]["capitalTruthRecoveryHistoryStatus"] == "degraded"
    assert first["health"]["capitalTruthDegradedSinceTsMs"] == "1700000000000"
    assert first["health"]["capitalTruthRecoveredAtTsMs"] == "0"

    runtime._capital_truth_payload = {
        "ok": True,
        "status": "ok",
        "status_reasons": [],
        "ts_ms": 1_700_000_060_000,
    }
    second = client.get("/api/fund/summary").json()
    assert second["health"]["capitalTruthRecoveryHistoryStatus"] == "recovered"
    assert second["health"]["capitalTruthRecoveredAtTsMs"] == "1700000060000"
    assert second["health"]["capitalTruthDegradedSinceTsMs"] == "0"
    assert second["health"]["recoveryHistoryStatus"] == "recovered"


def test_capital_recovery_repository_tracks_degrade_count_and_last_healthy_timestamp(tmp_path):
    db = PersistenceDB(str(tmp_path / "runtime.sqlite3"))
    repo = CapitalRecoveryRepository(db, chain="eth")

    degraded = repo.observe(
        component="capital_truth", degraded=True, ts_ms=1000, reason_code="capital_truth_degraded"
    )
    recovered = repo.observe(
        component="capital_truth", degraded=False, ts_ms=2500, reason_code="ok"
    )

    assert degraded["degraded_count"] == 1
    assert recovered["degraded_count"] == 1
    assert recovered["last_healthy_ts_ms"] == 2500
    assert recovered["last_recovered_ts_ms"] == 2500


def test_fund_summary_health_surfaces_recovery_history_count_and_severity_for_capital_truth_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryCapitalUnavailableRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert int(summary["health"]["capitalTruthDegradedCount"]) >= 1
    assert int(summary["health"]["recoveryDegradedCount"]) >= 1
    assert int(summary["health"]["capitalTruthLastHealthyTsMs"]) >= 0
    assert summary["health"]["capitalTruthDegradationSeverityClass"] in {
        "acute",
        "persistent",
        "chronic",
    }
    assert summary["health"]["recoveryDegradationSeverityClass"] in {
        "acute",
        "persistent",
        "chronic",
    }


def test_fund_summary_health_surfaces_recovery_reliability_canon_for_capital_truth_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        app.state, "runtime", _FundSummaryCapitalUnavailableRuntime(), raising=False
    )
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["capitalTruthReliabilityClass"] == "unavailable"
    assert (
        summary["health"]["capitalTruthReliabilityReasonCode"]
        == "capital_truth_reliability_unavailable"
    )
    assert (
        "capital_truth_freshness_unavailable"
        in summary["health"]["capitalTruthReliabilityReasonCodes"]
    )
    assert summary["health"]["recoveryReliabilityClass"] == "unavailable"
    assert summary["health"]["recoveryReliabilityReasonCode"] == "recovery_reliability_unavailable"
    assert summary["health"]["recoveryReliabilityNextAction"] == "restore_capital_truth"


def test_fund_summary_health_surfaces_fragile_family_hardening_reliability_when_service_recently_recovers_after_repeated_degradation(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(app.state, "runtime", _FundSummarySuccessRuntime(), raising=False)
    client = TestClient(app)

    class Runtime(_FundSummarySuccessRuntime):
        _fund_service = FundService()

        def capital_truth_state(self):
            return {"ok": True, "status": "ok", "ts_ms": 1_700_000_120_000}

        def family_hardening_state(self):
            return {
                "ok": True,
                "status": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "items": [{"family": "funding_arb", "status": "eligible"}],
            }

    runtime = Runtime()
    runtime._db = PersistenceDB(str(tmp_path / "runtime_family_hardening.sqlite3"))
    repo = CapitalRecoveryRepository(runtime._db, chain="default")
    repo.observe(
        component="family_hardening",
        degraded=True,
        ts_ms=1_700_000_000_000,
        reason_code="family_hardening_service_unavailable",
    )
    repo.observe(
        component="family_hardening", degraded=False, ts_ms=1_700_000_060_000, reason_code="ok"
    )
    repo.observe(
        component="family_hardening",
        degraded=True,
        ts_ms=1_700_000_070_000,
        reason_code="family_hardening_service_unavailable",
    )
    repo.observe(
        component="family_hardening", degraded=False, ts_ms=1_700_000_100_000, reason_code="ok"
    )
    runtime._capital_recovery_repo = repo
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)

    summary = client.get("/api/fund/summary").json()
    assert summary["health"]["familyHardeningRecoveryHistoryStatus"] == "recovered"
    assert int(summary["health"]["familyHardeningDegradedCount"]) >= 2
    assert summary["health"]["familyHardeningReliabilityClass"] in {"fragile", "cautious"}
    assert summary["health"]["recoveryHistoryComponent"] == "family_hardening"
    assert summary["health"]["recoveryReliabilityComponent"] == "family_hardening"
    assert summary["health"]["recoveryReliabilityClass"] in {"fragile", "cautious"}


def test_fund_summary_health_surfaces_fragile_recovery_reliability_when_capital_truth_recently_recovers_after_repeated_degradation(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(app.state, "runtime", _FundSummarySuccessRuntime(), raising=False)
    client = TestClient(app)

    class Runtime(_FundSummarySuccessRuntime):
        _fund_service = FundService()

        def capital_truth_state(self):
            return {"ok": True, "status": "ok", "ts_ms": 1_700_000_120_000}

    runtime = Runtime()
    runtime._db = PersistenceDB(str(tmp_path / "runtime.sqlite3"))
    repo = CapitalRecoveryRepository(runtime._db, chain="default")
    repo.observe(
        component="capital_truth",
        degraded=True,
        ts_ms=1_700_000_000_000,
        reason_code="capital_truth_unavailable",
    )
    repo.observe(
        component="capital_truth", degraded=False, ts_ms=1_700_000_060_000, reason_code="ok"
    )
    repo.observe(
        component="capital_truth",
        degraded=True,
        ts_ms=1_700_000_070_000,
        reason_code="capital_truth_unavailable",
    )
    repo.observe(
        component="capital_truth", degraded=False, ts_ms=1_700_000_100_000, reason_code="ok"
    )
    runtime._capital_recovery_repo = repo
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)

    summary = client.get("/api/fund/summary").json()
    assert summary["health"]["capitalTruthReliabilityClass"] in {"fragile", "cautious"}
    assert summary["health"]["recoveryReliabilityClass"] in {"fragile", "cautious"}
    assert int(summary["health"]["capitalTruthDegradedCount"]) >= 2


def test_fund_summary_health_fails_closed_when_internal_prime_state_payload_is_unavailable(
    monkeypatch,
):
    class _RuntimeUnavailablePrime(_FundSummarySuccessRuntime):
        def internal_prime_state(self):
            return {
                "ok": False,
                "status": "unavailable",
                "reason_code": "internal_prime_state_unavailable",
                "reason": "internal_prime_state_unavailable",
                "borrowedUsd": 0.0,
                "capacityUsd": 0.0,
                "utilization": 0.0,
                "inventory": {},
                "familyExposure": {},
                "openLoans": [],
                "loanCount": 0,
                "stateReady": False,
                "stateStatus": "unavailable",
                "stateReasonCode": "internal_prime_state_unavailable",
                "stateReason": "internal_prime_state_unavailable",
            }

    runtime = _RuntimeUnavailablePrime()
    monkeypatch.setattr(
        FundService,
        "_kill_switch_state",
        lambda self, runtime: {"active": False, "reason_codes": []},
        raising=False,
    )
    summary = FundService().summary(runtime)
    assert summary["internalPrime"]["status"] == "unavailable"
    assert summary["internalPrime"]["reason_code"] == "internal_prime_state_unavailable"
    assert summary["internalPrime"]["stateReady"] is False
    assert summary["internalPrime"]["stateReasonCode"] == "internal_prime_state_unavailable"


class _FundSummaryReceiptOutcomeTruthRuntime(_FundSummarySuccessRuntime):
    _fund_service = FundService()

    def __init__(self, db_path: str):
        self._db = PersistenceDB(db_path)

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "reason_code": "settled_profit_truth_unavailable",
            "status_reasons": ["settled_profit_truth_unavailable"],
            "ts_ms": 1_700_000_000_000,
            "reconciliation": {
                "receipt_outcome_truth": {
                    "is_degraded": True,
                    "reason_code": "settled_profit_truth_unavailable",
                    "updated_ts_ms": 1_700_000_000_000,
                }
            },
        }


def test_fund_summary_health_surfaces_receipt_outcome_truth_as_first_class_recovery_component(
    monkeypatch, tmp_path
):
    runtime = _FundSummaryReceiptOutcomeTruthRuntime(str(tmp_path / "receipt_truth.sqlite3"))
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    summary = client.get("/api/fund/summary").json()

    assert summary["health"]["holdReasonCode"] == "settled_profit_truth_unavailable"
    assert summary["health"]["receiptOutcomeTruthReasonCodes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert summary["health"]["suggestedNextAction"] == "restore_receipt_outcome_truth"
    assert summary["health"]["recoveryStatus"] == "capital_truth_restore_required"
    assert summary["health"]["recoveryReasonCode"] == "settled_profit_truth_unavailable"
    assert summary["health"]["recoveryNextAction"] == "restore_receipt_outcome_truth"
    assert summary["health"]["recoveryHistoryComponent"] == "receipt_outcome_truth"
    assert summary["health"]["receiptOutcomeTruthRecoveryHistoryStatus"] == "degraded"
    assert summary["health"]["recoveryReliabilityComponent"] == "receipt_outcome_truth"
    assert summary["health"]["receiptOutcomeTruthReliabilityClass"] == "degraded"
