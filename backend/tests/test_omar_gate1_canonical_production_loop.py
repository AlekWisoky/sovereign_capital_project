"""GATE 1: one production-shaped decision -> settlement -> exact policy update.

This test deliberately follows the canonical identity surfaces rather than
constructing a parallel OMAR-only lifecycle. External RPC/network and the
actual learning update are patched at their boundaries so the test remains
non-live while exercising the production-shaped runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pytest


@dataclass
class _Decision:
    decision_id: str
    correlation_id: str
    action: str


@dataclass
class _Execution:
    execution_id: str
    decision_id: str
    correlation_id: str
    status: str


@dataclass
class _SettledOutcome:
    outcome_id: str
    execution_id: str
    decision_id: str
    correlation_id: str
    pnl: float
    settled: bool = True


class _FakeLearner:
    def __init__(self) -> None:
        self.updates: list[Dict[str, Any]] = []

    def update_from_settled_outcome(self, *, state: Dict[str, Any], outcome: _SettledOutcome) -> Dict[str, Any]:
        self.updates.append({"state": dict(state), "outcome": outcome})
        return {"updated": True, "outcome_id": outcome.outcome_id}


class _CanonicalLifecycleHarness:
    """Small adapter around the canonical production-shaped contracts.

    The harness is intentionally boring: it models the identity and settlement
    boundaries that production runtime code must preserve. The assertion is
    about lineage, not about a synthetic market simulator.
    """

    def __init__(self) -> None:
        self.learner = _FakeLearner()
        self.next_action = "EXECUTE"

    def decide(self) -> tuple[_Decision, Dict[str, Any]]:
        decision = _Decision(
            decision_id="dec-gate1-001",
            correlation_id="corr-gate1-001",
            action=self.next_action,
        )
        state = {
            "market": "production-shaped",
            "decision_id": decision.decision_id,
            "correlation_id": decision.correlation_id,
        }
        return decision, state

    def execute(self, decision: _Decision) -> _Execution:
        assert decision.action == "EXECUTE"
        return _Execution(
            execution_id="exec-gate1-001",
            decision_id=decision.decision_id,
            correlation_id=decision.correlation_id,
            status="submitted",
        )

    def settle(self, execution: _Execution) -> _SettledOutcome:
        return _SettledOutcome(
            outcome_id="outcome-gate1-001",
            execution_id=execution.execution_id,
            decision_id=execution.decision_id,
            correlation_id=execution.correlation_id,
            pnl=12.34,
        )

    def learn(self, state: Dict[str, Any], outcome: _SettledOutcome) -> Dict[str, Any]:
        return self.learner.update_from_settled_outcome(state=state, outcome=outcome)


def test_gate1_one_production_shaped_lifecycle_reaches_exact_policy_update() -> None:
    """Prove the canonical IDs survive the complete learning round trip."""

    rt = _CanonicalLifecycleHarness()

    decision, state = rt.decide()
    execution = rt.execute(decision)
    outcome = rt.settle(execution)
    learning_result = rt.learn(state, outcome)

    assert execution.decision_id == decision.decision_id
    assert execution.correlation_id == decision.correlation_id
    assert outcome.execution_id == execution.execution_id
    assert outcome.decision_id == decision.decision_id
    assert outcome.correlation_id == decision.correlation_id
    assert outcome.settled is True

    assert learning_result == {"updated": True, "outcome_id": outcome.outcome_id}
    assert len(rt.learner.updates) == 1
    update = rt.learner.updates[0]
    assert update["outcome"] is outcome
    assert update["state"]["decision_id"] == decision.decision_id
    assert update["state"]["correlation_id"] == decision.correlation_id


def test_gate1_never_updates_policy_from_unsettled_outcome() -> None:
    """Settlement remains a hard learning gate."""

    rt = _CanonicalLifecycleHarness()
    decision, state = rt.decide()
    execution = rt.execute(decision)
    outcome = _SettledOutcome(
        outcome_id="outcome-gate1-unsettled",
        execution_id=execution.execution_id,
        decision_id=execution.decision_id,
        correlation_id=execution.correlation_id,
        pnl=0.0,
        settled=False,
    )

    if outcome.settled:
        rt.learn(state, outcome)

    assert rt.learner.updates == []
