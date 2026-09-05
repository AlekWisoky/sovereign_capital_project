from victor_ai_bot.identity import (
    identity_from,
    new_execution_identity,
    new_settlement_identity,
    new_decision_identity,
)
from victor_ai_bot.omar.real_learning import OmarRealLearningLoop


def test_production_lineage_identity_survives_decision_execution_settlement_learning(
    tmp_path,
):
    """Contract-test the canonical identity chain at the real-learning boundary."""
    policy_updates = []

    def policy_updater(attribution):
        policy_updates.append(attribution)
        return {"ok": True, "learning_id": attribution.learning_id}

    identity = new_decision_identity()
    decision = {
        "identity": identity.to_dict(),
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
    }

    execution_identity = new_execution_identity(identity)
    execution = {
        "identity": execution_identity.to_dict(),
        "decision_id": execution_identity.decision_id,
        "correlation_id": execution_identity.correlation_id,
        "execution_id": execution_identity.execution_id,
    }

    settlement_identity = new_settlement_identity(execution_identity)
    settled_outcome = {
        "identity": settlement_identity.to_dict(),
        "decision_id": settlement_identity.decision_id,
        "correlation_id": settlement_identity.correlation_id,
        "execution_id": settlement_identity.execution_id,
        "settlement_id": settlement_identity.settlement_id,
    }

    assert identity_from(decision) == identity
    assert identity_from(execution) == execution_identity
    assert identity_from(settled_outcome) == settlement_identity

    loop = OmarRealLearningLoop(
        data_dir=str(tmp_path),
        policy_updater=policy_updater,
    )
    loop.record_decision(
        decision_id=identity.decision_id,
        correlation_id=identity.correlation_id,
        action="trade",
        metadata={"lineage": identity.to_dict()},
    )
    loop.bind_execution(
        decision_id=execution_identity.decision_id,
        correlation_id=execution_identity.correlation_id,
        execution_id=execution_identity.execution_id,
        status="filled",
        action="trade",
        tx_hash="0xproduction-contract-test",
        latency_ms=17.5,
    )
    attribution = loop.settle_outcome(
        decision_id=settlement_identity.decision_id,
        correlation_id=settlement_identity.correlation_id,
        execution_id=settlement_identity.execution_id,
        settlement_id=settlement_identity.settlement_id,
        status="settled",
        realized_pnl_wei=125,
        realized_slippage_bps=2.5,
        realized_gas_wei=15,
        risk_cost_wei=5,
    )

    assert attribution.decision_id == identity.decision_id
    assert attribution.correlation_id == identity.correlation_id
    assert attribution.execution_id == execution_identity.execution_id
    assert attribution.settlement_id == settlement_identity.settlement_id
    assert attribution.action == "trade"
    assert attribution.reward_wei == 105
    assert attribution.eligible_for_learning is True
    assert len(policy_updates) == 1
    assert policy_updates[0] == attribution


def test_production_lineage_rejects_cross_trade_execution_identity(tmp_path):
    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    first = new_decision_identity()
    second = new_decision_identity()

    loop.record_decision(
        decision_id=first.decision_id,
        correlation_id=first.correlation_id,
        action="trade",
    )

    try:
        loop.bind_execution(
            decision_id=first.decision_id,
            correlation_id=second.correlation_id,
            execution_id=new_execution_identity(first).execution_id,
            status="filled",
            action="trade",
        )
    except ValueError as exc:
        assert str(exc) == "correlation_id_mismatch"
    else:
        raise AssertionError("cross-trade correlation must be rejected")


def test_settlement_requires_the_same_execution_lineage(tmp_path):
    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    first = new_decision_identity()
    second = new_decision_identity()
    first_execution = new_execution_identity(first)
    second_execution = new_execution_identity(second)

    loop.record_decision(
        decision_id=first.decision_id,
        correlation_id=first.correlation_id,
        action="trade",
    )
    loop.record_decision(
        decision_id=second.decision_id,
        correlation_id=second.correlation_id,
        action="trade",
    )
    loop.bind_execution(
        decision_id=first_execution.decision_id,
        correlation_id=first_execution.correlation_id,
        execution_id=first_execution.execution_id,
        status="filled",
        action="trade",
    )
    loop.bind_execution(
        decision_id=second_execution.decision_id,
        correlation_id=second_execution.correlation_id,
        execution_id=second_execution.execution_id,
        status="filled",
        action="trade",
    )

    try:
        loop.settle_outcome(
            decision_id=first.decision_id,
            correlation_id=first.correlation_id,
            execution_id=second_execution.execution_id,
            settlement_id="settle_cross_trade",
            status="settled",
        )
    except ValueError as exc:
        assert str(exc) == "execution_identity_mismatch"
    else:
        raise AssertionError("cross-trade settlement must be rejected")
