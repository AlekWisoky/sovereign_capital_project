# OMAR Phase 6 — Production Decision/Execution/Settlement Identity

Phase 6 makes decision/execution/learning identity a first-class production concern.

## Runtime path

```text
market data
  -> strategy/opportunity scan
  -> canonical decision boundary
  -> decision_id + correlation_id
  -> OMAR recommendation (optional/bounded)
  -> governance/admission
  -> execution
  -> execution bookkeeping
  -> canonical receipt settlement
  -> exact lineage validation
  -> OMAR outcome attribution
  -> policy update
```

## Identity contract

`decision_id` and `correlation_id` are created/preserved independently of OMAR's enabled state. They are persisted on the opportunity's canonical lineage and on the decision metadata. Re-entering the same decision identity does not create a second identity.

OMAR may consume the identity, but it does not own identity creation.

## Execution propagation

The production lineage bridge copies canonical identity into the execution result plan before the existing execution bookkeeping path runs. This keeps the identity available to the existing execution/ledger machinery without introducing a second execution path.

## Settlement safety

A settled outcome is usable for OMAR learning only when the canonical settlement surface reports `status=settled` and its decision, correlation, and opportunity identities exactly match the live decision lineage. A matching transaction hash alone is insufficient for the learning attribution contract.

## Authority boundaries

- Decision engine remains responsible for selecting the executable opportunity.
- OMAR remains a bounded recommendation/learning layer.
- GMAO/governance remains authoritative.
- Execution remains the only transaction path.
- The Phase 2 settlement ledger remains the outcome authority.
- `capital_engine_state()` remains the capital-authority input; OMAR cannot approve or allocate capital.
