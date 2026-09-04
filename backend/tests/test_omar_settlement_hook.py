from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.lifecycle_bridge import (
    build_canonical_settled_outcome,
    settlement_hook,
)


class _Omar:
    def __init__(self):
        self.calls = []

    def observe_outcome(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "eligible_for_learning": True}


def _pending():
    return {
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "amount_in": 125000,
        "strategy_family": "flashloan_atomic",
        "capital_source": "internal_prime",
        "prime_loan_id": "prime-loan-7",
        "internal_prime_authority": {"authority_id": "prime-authority-1"},
        "capital_demand": {
            "requested_wei": 150000,
            "authorized_wei": 140000,
            "deployed_wei": 125000,
            "capital_source": "internal_prime",
            "strategy_family": "flashloan_atomic",
            "treasury_denomination": "ETH",
        },
        "brain": {
            "role": "ARBITRAGE_AGENT",
            "rl_state": "state-42",
        },
        "canonical_lineage": {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
            "execution_id": "execution-1",
            "settlement_id": "settlement-1",
        },
    }


def _outcome():
    return {
        "status": "settled",
        "truth_verified": True,
        "tx_hash": "0xabc",
        "realized_pnl_wei": 5000,
        "gas_cost_wei": 300,
        "realized_net_usd": 4.7,
        "latency_ms": 37,
    }


def _committed():
    return {
        "ok": True,
        "settlementCommitted": True,
        "transaction_id": "ledger-tx-1",
        "receipt_id": "0xabc",
    }


def test_settlement_hook_requires_canonical_commit():
    omar = _Omar()
    runtime = SimpleNamespace(_omar=omar)
    result = settlement_hook(
        runtime,
        pending=_pending(),
        outcome=_outcome(),
        committed_record={"ok": False},
    )
    assert result["reason_code"] == "settlement_not_committed"
    assert omar.calls == []


def test_settlement_hook_emits_complete_identity_and_capital_identity():
    omar = _Omar()
    runtime = SimpleNamespace(_omar=omar)
    result = settlement_hook(
        runtime,
        pending=_pending(),
        outcome=_outcome(),
        committed_record=_committed(),
    )

    assert result["ok"] is True
    assert len(omar.calls) == 1
    canonical = result["canonical_outcome"]
    call = omar.calls[0]

    assert canonical["decision_id"] == "decision-1"
    assert canonical["correlation_id"] == "corr-1"
    assert canonical["execution_id"] == "execution-1"
    assert canonical["settlement_id"] == "settlement-1"
    assert canonical["metadata"]["source"] == "phase2_canonical_outcome_ledger"
    assert canonical["capital_identity"]["requested_wei"] == 150000
    assert canonical["capital_identity"]["authorized_wei"] == 140000
    assert canonical["capital_identity"]["deployed_wei"] == 125000
    assert canonical["capital_identity"]["internal_prime_loan_id"] == "prime-loan-7"
    assert canonical["capital_identity"]["internal_prime_authority_id"] == "prime-authority-1"
    assert canonical["capital_identity"]["capital_demand_id"].startswith("capital_demand_")
    assert canonical["capital_identity"]["internal_prime_identity"].startswith("internal_prime_")
    assert canonical["outcome_identity"].startswith("settled_outcome_")

    assert call["decision_id"] == "decision-1"
    assert call["correlation_id"] == "corr-1"
    assert call["execution_id"] == "execution-1"
    assert call["settlement_id"] == "settlement-1"
    assert call["tx_hash"] == "0xabc"
    assert call["state_key"] == "state-42"
    assert call["metadata"]["capital_identity"]["internal_prime_loan_id"] == "prime-loan-7"


def test_canonical_settled_identity_is_deterministic():
    first = build_canonical_settled_outcome(
        pending=_pending(), outcome=_outcome(), committed_record=_committed()
    )
    second = build_canonical_settled_outcome(
        pending=_pending(), outcome=_outcome(), committed_record=_committed()
    )
    assert first["outcome_identity"] == second["outcome_identity"]
    assert first["capital_identity"]["capital_demand_id"] == second["capital_identity"]["capital_demand_id"]
    assert first["capital_identity"]["internal_prime_identity"] == second["capital_identity"]["internal_prime_identity"]
