from victor_ai_bot.omar.real_learning import OmarRealLearningLoop


def test_real_learning_requires_identity_and_preserves_correlation(tmp_path):
    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    loop.record_decision(
        decision_id="decision_1",
        correlation_id="corr_1",
        action="trade",
        opp_id="opp_1",
        route_id="route_1",
    )

    loop.bind_execution(
        decision_id="decision_1",
        correlation_id="corr_1",
        execution_id="exec_1",
        status="filled",
        action="trade",
        tx_hash="0xabc",
    )

    attribution = loop.settle_outcome(
        decision_id="decision_1",
        correlation_id="corr_1",
        execution_id="exec_1",
        settlement_id="settle_1",
        status="settled",
        realized_pnl_wei=100,
        realized_gas_wei=10,
        risk_cost_wei=5,
    )

    assert attribution.eligible_for_learning is True
    assert attribution.reward_wei == 85
    assert attribution.decision_id == "decision_1"
    assert attribution.correlation_id == "corr_1"
    assert attribution.execution_id == "exec_1"
    assert attribution.settlement_id == "settle_1"


def test_real_learning_rejects_correlation_mismatch(tmp_path):
    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    loop.record_decision(decision_id="decision_1", correlation_id="corr_1", action="trade")

    try:
        loop.bind_execution(
            decision_id="decision_1",
            correlation_id="corr_2",
            execution_id="exec_1",
            status="filled",
            action="trade",
        )
    except ValueError as exc:
        assert str(exc) == "correlation_id_mismatch"
    else:
        raise AssertionError("expected correlation_id_mismatch")


def test_missing_capital_authority_is_not_approval(tmp_path):
    loop = OmarRealLearningLoop(data_dir=str(tmp_path))
    authority = loop.read_capital_authority()
    assert authority.status == "unavailable"
    assert authority.allocatable_wei == 0
    assert "capital_authority_reader_unavailable" in authority.reason_codes
