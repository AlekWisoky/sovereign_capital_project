from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution_identity import attach_execution_identity, create_execution_identity
from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome


def _decision_and_opp():
    opp = SimpleNamespace(
        id="opp-phase21",
        route_id="route-phase21",
        meta={
            "brain": {
                "canonical_decision_id": "decision-real-21",
                "correlation_id": "corr-real-21",
            }
        },
    )
    decision = SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-real-21",
            "correlation_id": "corr-real-21",
        }
    )
    return decision, opp


def test_execution_identity_is_created_at_execution_boundary_and_is_not_synthetic():
    decision, opp = _decision_and_opp()

    identity = create_execution_identity(decision, opp)
    assert identity.decision_id == "decision-real-21"
    assert identity.correlation_id == "corr-real-21"
    assert identity.execution_id.startswith("execution_")
    assert len(identity.execution_id) > len("execution_")

    result = SimpleNamespace(plan={}, tx_hash="0xreal")
    attach_execution_identity(identity, decision=decision, opp=opp, result=result)

    assert decision.metadata["execution_id"] == identity.execution_id
    assert opp.meta["brain"]["execution_id"] == identity.execution_id
    assert result.plan["execution_id"] == identity.execution_id
    assert result.plan["execution_lineage"] == {
        "decision_id": "decision-real-21",
        "correlation_id": "corr-real-21",
        "execution_id": identity.execution_id,
    }


def test_execution_identity_requires_canonical_decision_lineage():
    decision = SimpleNamespace(metadata={})
    opp = SimpleNamespace(id="opp-no-lineage", route_id="route-no-lineage", meta={})

    with pytest.raises(ValueError, match="canonical_decision_lineage_required"):
        create_execution_identity(decision, opp)


def test_canonical_settlement_interface_requires_matching_execution_identity():
    class LedgerRepo:
        def all_transactions(self, *, chain):
            assert chain == "ethereum"
            return [
                {
                    "tx_type": "receipt_settlement",
                    "transaction_id": "ledger-tx-21",
                    "receipt_id": "0xsettled21",
                    "ts_ms": 1234,
                    "metadata": {
                        "canonical_decision_id": "decision-real-21",
                        "correlation_id": "corr-real-21",
                        "execution_id": "execution_real_21",
                        "opportunity_id": "opp-phase21",
                        "route_id": "route-phase21",
                        "capitalDemand": {
                            "requested_usd_micro": 500_000_000,
                            "authorized_usd_micro": 400_000_000,
                            "deployed_usd_micro": 390_000_000,
                            "authority_source": "internal_prime",
                            "capital_source": "internal_prime",
                        },
                        "internalPrimeAuthority": {
                            "authority_id": "prime-authority-21",
                            "approved": True,
                            "capacity_usd_micro": 2_000_000_000,
                        },
                        "truth_verified": True,
                        "realized_net_usd": 42.0,
                    },
                }
            ]

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _ledger_repo=LedgerRepo(),
    )

    outcome = canonical_settled_outcome(
        runtime,
        decision_id="decision-real-21",
        correlation_id="corr-real-21",
        opportunity_id="opp-phase21",
        execution_id="execution_real_21",
    )

    assert outcome is not None
    assert outcome["execution_id"] == "execution_real_21"
    assert outcome["canonical_lineage"]["decision_id"] == "decision-real-21"
    assert outcome["canonical_lineage"]["correlation_id"] == "corr-real-21"
    assert outcome["canonical_lineage"]["execution_id"] == "execution_real_21"
    assert outcome["capital_demand"]["requested_usd_micro"] == 500_000_000
    assert outcome["capital_demand"]["authorized_usd_micro"] == 400_000_000
    assert outcome["internal_prime_authority"]["authority_id"] == "prime-authority-21"

    assert (
        canonical_settled_outcome(
            runtime,
            decision_id="decision-real-21",
            correlation_id="corr-real-21",
            opportunity_id="opp-phase21",
            execution_id="execution_wrong",
        )
        is None
    )
