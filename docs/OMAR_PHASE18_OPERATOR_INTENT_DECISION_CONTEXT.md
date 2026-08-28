# OMAR Phase 18 — Canonical Operator-Intent Decision Context

## Purpose

Make the effective operator intent a first-class, immutable attribution context at the production decision boundary.

The canonical lifecycle remains:

`operator intent -> canonical decision identity -> correlation -> execution -> canonical settled outcome -> OMAR learning`

## Intent captured

The decision attribution snapshot may contain:

- command-center aggression mode
- bounded risk multiplier
- active wealth-goal target amount
- target return percentage
- goal timeframe
- goal revision / active goal identity
- current return and drawdown
- latest operator-facing AI recommendation and confidence

## Authority boundary

Operator intent is contextual attribution. It is not execution authority.

- GMAO/governance remains authoritative.
- `capital_engine_state()` remains the capital-authority input.
- admission and `ExecutionService` remain execution authorities.
- OMAR remains recommendation/learning-only.
- intent cannot sign, submit, approve capital, bypass governance, or upsize capital.

## Write-once identity rule

Once canonical decision identity has an operator-intent snapshot, later operator changes apply only to future decisions. Historical decision attribution is not rewritten.

The stable intent fingerprint is for lineage/attribution only and is not used as the generalized OMAR learning state key.

## Verification

`backend/tests/test_omar_phase18_operator_intent_decision_context.py` verifies the production lineage bridge attaches the effective intent to canonical decision metadata and preserves an existing snapshot when operator state changes.
