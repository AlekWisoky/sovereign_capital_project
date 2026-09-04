from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services import ReceiptService
from victor_ai_bot.runtime_services.omar_settlement_adapter import install_receipt_settlement_hook


class _Omar:
    def __init__(self):
        self.calls = []

    def observe_outcome(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "eligible_for_learning": True}


def test_receipt_settlement_adapter_calls_omar_after_canonical_commit(monkeypatch):
    original = ReceiptService.synchronize_settlement_accounting

    def fake_settlement(self, runtime, *args, **kwargs):
        return {
            "ok": True,
            "settlementCommitted": True,
            "transaction_id": "ledger-tx-9",
            "receipt_id": "0xabc",
        }

    monkeypatch.setattr(ReceiptService, "synchronize_settlement_accounting", fake_settlement)
    install_receipt_settlement_hook()

    omar = _Omar()
    runtime = SimpleNamespace(
        _omar=omar,
        capital_engine_state=lambda: {
            "authority_id": "capital-authority-1",
            "allocatable_wei": 140000,
            "available_wei": 200000,
            "status": "healthy",
        },
        _internal_prime=SimpleNamespace(
            state=lambda: {"authority_id": "prime-authority-1", "loan_id": "prime-loan-9"}
        ),
    )
    pending = {
        "opportunity_id": "opp-9",
        "route_id": "route-9",
        "amount_in": 125000,
        "strategy_family": "flashloan_atomic",
        "capital_demand": {
            "requested_wei": 150000,
            "authorized_wei": 140000,
            "deployed_wei": 125000,
            "capital_source": "internal_prime",
            "strategy_family": "flashloan_atomic",
            "treasury_denomination": "ETH",
        },
        "canonical_lineage": {
            "decision_id": "decision-9",
            "correlation_id": "corr-9",
            "execution_id": "execution-9",
            "settlement_id": "settlement-9",
        },
        "brain": {"role": "ARBITRAGE_AGENT", "rl_state": "state-9"},
    }

    result = ReceiptService().synchronize_settlement_accounting(
        runtime,
        pending=pending,
        decoded={
            "realized_profit_after_gas_wei": 5000,
            "realized_gas_cost_wei": 300,
        },
        status=1,
        amount_in=125000,
        expected_after=4000,
        realized_after=5000,
        submit_to_receipt_ms=37,
        route_id="route-9",
        route_family="flash",
        strategy_family="flashloan_atomic",
        capture_lane_pending="RECEIPT",
    )

    assert result["settlementCommitted"] is True
    assert result["omarLearning"]["ok"] is True
    assert len(omar.calls) == 1
    call = omar.calls[0]
    assert call["decision_id"] == "decision-9"
    assert call["correlation_id"] == "corr-9"
    assert call["execution_id"] == "execution-9"
    assert call["settlement_id"] == "settlement-9"
    assert call["metadata"]["capital_identity"]["internal_prime_loan_id"] == "prime-loan-9"
    assert call["metadata"]["capital_identity"]["internal_prime_authority_id"] == "prime-authority-1"
    assert call["metadata"]["capital_identity"]["authorized_wei"] == 140000
    assert call["metadata"]["source"] == "phase2_canonical_outcome_ledger"

    monkeypatch.setattr(ReceiptService, "synchronize_settlement_accounting", original)
