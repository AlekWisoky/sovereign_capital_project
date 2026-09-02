from victor_ai_bot.identity import (
    TradeIdentity,
    attach_identity,
    identity_from,
    new_decision_identity,
    new_execution_identity,
    new_settlement_identity,
)
from victor_ai_bot.outcomes import ExecutionOutcome
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    RuntimeExecuteWrapperFacade,
)


def test_identity_progresses_without_regenerating_decision_correlation():
    decision = new_decision_identity()
    execution = new_execution_identity(decision)
    settlement = new_settlement_identity(execution)

    assert decision.decision_id == execution.decision_id == settlement.decision_id
    assert decision.correlation_id == execution.correlation_id == settlement.correlation_id
    assert execution.execution_id
    assert settlement.settlement_id
    assert settlement.complete_for_settlement


def test_identity_attachment_is_visible_on_runtime_objects():
    class Target:
        def __init__(self):
            self.metadata = {}
            self.plan = {}

    target = Target()
    identity = new_execution_identity(new_decision_identity())
    attach_identity(target, identity)

    recovered = identity_from(target)
    assert recovered == identity
    assert target.metadata["identity"]["decision_id"] == identity.decision_id
    assert target.plan["lineage"]["execution_id"] == identity.execution_id


def test_execution_outcome_resolves_identity_from_details():
    identity = TradeIdentity(
        decision_id="decision_1",
        correlation_id="corr_1",
        execution_id="exec_1",
        settlement_id="",
    )
    outcome = ExecutionOutcome(
        status="accepted",
        reason_code="submitted",
        retryable=False,
        details={"identity": identity.to_dict()},
    )

    assert outcome.decision_id == "decision_1"
    assert outcome.correlation_id == "corr_1"
    assert outcome.execution_id == "exec_1"
    assert outcome.settlement_id == ""


def test_execution_wrapper_creates_attempt_id_under_decision_lineage():
    class Result:
        plan = {}

    decision = new_decision_identity()
    result = RuntimeExecuteWrapperFacade._ensure_execution_identity(Result(), decision)

    assert result.decision_id == decision.decision_id
    assert result.correlation_id == decision.correlation_id
    assert result.execution_id.startswith("exec_")
    assert result.plan["identity"]["decision_id"] == decision.decision_id
