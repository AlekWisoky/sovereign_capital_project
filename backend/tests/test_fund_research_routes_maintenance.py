from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from victor_ai_bot.research_pipeline.candidates import CandidateStore
from victor_ai_bot.server import app


class _FundResearchRuntime:
    def __init__(self, tmp_path: Path):
        self._research_candidates = CandidateStore(data_dir=str(tmp_path), chain="ethereum")


class _FundResearchRuntimeWithoutStore:
    pass


class _FundResearchCreateFailingStore:
    def create(self, **_: Any):
        raise OSError('candidate store not writable')


class _FundResearchPromoteFailingStore:
    def __init__(self, *, fail_on: str):
        self.fail_on = fail_on

    def evaluate_promotion(self, candidate_id: str, *, evidence: dict[str, Any] | None = None):
        if self.fail_on == 'evaluate':
            raise ValueError('candidate metadata malformed')

        class _Decision:
            allowed = True
            next_stage = 'shadow_live'

            @staticmethod
            def to_dict():
                return {'allowed': True, 'reason_code': 'promotion_ready', 'details': {'candidateId': candidate_id}}

        return _Decision()

    def transition(self, candidate_id: str, *, stage: str, reason: str, reviewer: str = ''):
        if self.fail_on == 'transition':
            raise OSError('candidate store not writable')
        return {
            'candidateId': candidate_id,
            'stage': stage,
            'history': [{'reason': reason, 'reviewer': reviewer}],
        }


class _FundResearchRuntimeWithStore:
    def __init__(self, store: Any):
        self._research_candidates = store


def test_fund_research_candidate_create_requires_explicit_valid_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    runtime = _FundResearchRuntime(tmp_path)
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    missing_thesis = client.post("/api/fund/research/candidates", json={}).json()
    assert missing_thesis["ok"] is False
    assert missing_thesis["status"] == "invalid"
    assert missing_thesis["reason_code"] == "missing_thesis"
    assert runtime._research_candidates.items() == []

    invalid_metadata = client.post(
        "/api/fund/research/candidates",
        json={"thesis": "capture basis dislocation", "metadata": ["bad"]},
    ).json()
    assert invalid_metadata["ok"] is False
    assert invalid_metadata["status"] == "invalid"
    assert invalid_metadata["reason_code"] == "invalid_mapping_value"
    assert invalid_metadata["details"]["field"] == "metadata"
    assert runtime._research_candidates.items() == []

    blank_family = client.post(
        "/api/fund/research/candidates",
        json={"family": "   ", "thesis": "capture basis dislocation"},
    ).json()
    assert blank_family["ok"] is False
    assert blank_family["status"] == "invalid"
    assert blank_family["reason_code"] == "invalid_string_value"
    assert blank_family["details"]["field"] == "family"
    assert runtime._research_candidates.items() == []

    unknown_field = client.post(
        "/api/fund/research/candidates",
        json={"thesis": "capture basis dislocation", "unexpected": True},
    ).json()
    assert unknown_field["ok"] is False
    assert unknown_field["status"] == "invalid"
    assert unknown_field["reason_code"] == "unknown_request_fields"
    assert unknown_field["details"]["fields"] == ["unexpected"]
    assert runtime._research_candidates.items() == []

    accepted = client.post(
        "/api/fund/research/candidates",
        json={
            "family": "funding_arb",
            "origin": "generated",
            "thesis": "capture basis dislocation",
            "owner": "desk",
            "generatedBy": "policy_v2",
            "metadata": {"promotion_ready": True},
        },
    ).json()
    assert accepted["ok"] is True
    assert accepted["item"]["family"] == "funding_arb"
    assert accepted["item"]["stage"] == "observe_only"
    assert accepted["item"]["generatedBy"] == "policy_v2"
    assert accepted["item"]["metadata"] == {"promotion_ready": True}


def test_fund_research_promote_requires_valid_candidate_and_evidence(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    runtime = _FundResearchRuntime(tmp_path)
    seed = runtime._research_candidates.create(
        family="funding_arb",
        origin="hybrid",
        thesis="capture basis dislocation",
        metadata={"telemetry_count": 8, "success_rate": 0.82, "drawdown_pct": 2.5},
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    missing_candidate = client.post("/api/fund/research/promote", json={}).json()
    assert missing_candidate["ok"] is False
    assert missing_candidate["status"] == "invalid"
    assert missing_candidate["reason_code"] == "missing_candidate_id"

    candidate_not_found = client.post(
        "/api/fund/research/promote",
        json={"candidateId": "missing"},
    ).json()
    assert candidate_not_found["ok"] is False
    assert candidate_not_found["status"] == "invalid"
    assert candidate_not_found["reason_code"] == "candidate_not_found"
    assert candidate_not_found["details"]["field"] == "candidateId"

    invalid_telemetry = client.post(
        "/api/fund/research/promote",
        json={"candidateId": seed["candidateId"], "telemetryCount": "later"},
    ).json()
    assert invalid_telemetry["ok"] is False
    assert invalid_telemetry["status"] == "invalid"
    assert invalid_telemetry["reason_code"] == "invalid_integer_value"
    assert invalid_telemetry["details"]["field"] == "telemetryCount"

    invalid_score = client.post(
        "/api/fund/research/promote",
        json={"candidateId": seed["candidateId"], "score": "high"},
    ).json()
    assert invalid_score["ok"] is False
    assert invalid_score["status"] == "invalid"
    assert invalid_score["reason_code"] == "invalid_float_value"
    assert invalid_score["details"]["field"] == "score"

    invalid_stage = client.post(
        "/api/fund/research/promote",
        json={"candidateId": seed["candidateId"], "stage": "moonshot"},
    ).json()
    assert invalid_stage["ok"] is False
    assert invalid_stage["status"] == "invalid"
    assert invalid_stage["reason_code"] == "invalid_stage"
    assert "shadow_live" in invalid_stage["details"]["allowed_stages"]

    unknown_field = client.post(
        "/api/fund/research/promote",
        json={"candidateId": seed["candidateId"], "unexpected": True},
    ).json()
    assert unknown_field["ok"] is False
    assert unknown_field["status"] == "invalid"
    assert unknown_field["reason_code"] == "unknown_request_fields"
    assert unknown_field["details"]["fields"] == ["unexpected"]

    promoted = client.post(
        "/api/fund/research/promote",
        json={
            "candidateId": seed["candidateId"],
            "telemetryCount": 12,
            "score": 0.88,
            "riskScore": 2.0,
            "stage": "capped_live",
            "reason": "meets threshold",
            "reviewer": "governance",
        },
    ).json()
    assert promoted["ok"] is True
    assert promoted["decision"]["nextStage"] == "capped_live"
    assert promoted["item"]["stage"] == "capped_live"
    assert promoted["item"]["history"][-1]["reason"] == "meets threshold"
    assert promoted["item"]["history"][-1]["reviewer"] == "governance"


def test_fund_research_mutation_routes_surface_store_unavailable_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    runtime = _FundResearchRuntimeWithoutStore()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    created = client.post(
        "/api/fund/research/candidates",
        json={"thesis": "capture basis dislocation"},
    ).json()
    assert created["ok"] is False
    assert created["status"] == "unavailable"
    assert created["reason_code"] == "candidate_store_unavailable"
    assert created["error"] == "candidate_store_unavailable"

    promoted = client.post(
        "/api/fund/research/promote",
        json={"candidateId": "missing"},
    ).json()
    assert promoted["ok"] is False
    assert promoted["status"] == "unavailable"
    assert promoted["reason_code"] == "candidate_store_unavailable"
    assert promoted["error"] == "candidate_store_unavailable"


def test_fund_research_promotion_blocked_payload_is_explicit(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")
    runtime = _FundResearchRuntime(tmp_path)
    seed = runtime._research_candidates.create(
        family="funding_arb",
        origin="hybrid",
        thesis="capture basis dislocation",
        metadata={"telemetry_count": 2, "success_rate": 0.82, "drawdown_pct": 2.5},
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    blocked = client.post(
        "/api/fund/research/promote",
        json={"candidateId": seed["candidateId"]},
    ).json()

    assert blocked["ok"] is False
    assert blocked["status"] == "blocked"
    assert blocked["reason_code"] == "insufficient_telemetry"
    assert blocked["reason"] == "insufficient_telemetry"
    assert blocked["details"]["candidateId"] == seed["candidateId"]
    assert blocked["decision"]["allowed"] is False
    assert blocked["decision"]["reason_code"] == "insufficient_telemetry"


def test_fund_research_mutation_routes_surface_store_runtime_failures_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ALLOW_INSECURE_LOCAL_ADMIN", "1")

    create_runtime = _FundResearchRuntimeWithStore(_FundResearchCreateFailingStore())
    monkeypatch.setattr(app.state, "runtime", create_runtime, raising=False)
    client = TestClient(app)

    created = client.post(
        "/api/fund/research/candidates",
        json={"thesis": "capture basis dislocation"},
    ).json()
    assert created["ok"] is False
    assert created["status"] == "unavailable"
    assert created["reason_code"] == "candidate_store_unavailable"
    assert created["error"] == "candidate_store_unavailable"

    evaluate_runtime = _FundResearchRuntimeWithStore(_FundResearchPromoteFailingStore(fail_on='evaluate'))
    monkeypatch.setattr(app.state, "runtime", evaluate_runtime, raising=False)
    evaluation = client.post(
        "/api/fund/research/promote",
        json={"candidateId": "candidate-1"},
    ).json()
    assert evaluation["ok"] is False
    assert evaluation["status"] == "unavailable"
    assert evaluation["reason_code"] == "candidate_store_unavailable"
    assert evaluation["error"] == "candidate_store_unavailable"

    transition_runtime = _FundResearchRuntimeWithStore(_FundResearchPromoteFailingStore(fail_on='transition'))
    monkeypatch.setattr(app.state, "runtime", transition_runtime, raising=False)
    transition = client.post(
        "/api/fund/research/promote",
        json={"candidateId": "candidate-1"},
    ).json()
    assert transition["ok"] is False
    assert transition["status"] == "unavailable"
    assert transition["reason_code"] == "candidate_store_unavailable"
    assert transition["error"] == "candidate_store_unavailable"
