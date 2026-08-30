# Phase 7 — Operator-Intent Attribution

## Contract

The effective operator intent is captured at the canonical decision boundary and carried forward as immutable attribution context:

`human controls + wealth goal + AI recommendation -> decision snapshot -> execution record -> canonical settled outcome -> OMAR learning`

The snapshot includes aggression mode, risk multiplier, wealth-goal target/timeframe/revision/progress, and the operator-facing AI recommendation. It is fingerprinted for exact attribution.

## Immutability rule

Execution-time code MUST NOT re-read mutable operator controls and overwrite an existing decision snapshot. If an opportunity already contains a decision-time `operator_intent`, execution reuses it. Live operator inputs are only resolved as a compatibility fallback for legacy callers that have no snapshot.

## Authority boundary

Operator intent is context, not authority. It cannot approve capital, sign transactions, bypass governance, change admission, or directly authorize execution. Capital authority remains `capital_engine_state()`, governance remains authoritative, and execution remains the existing execution stack.

## Learning boundary

OMAR receives the attributed intent alongside canonical decision/execution/settlement lineage. Changing aggression, wealth goal, or AI recommendation for a later decision must create a distinct attribution fingerprint while leaving prior decisions unchanged.

A settled outcome must still come from the canonical outcome ledger; a receipt or mutable runtime state alone is not sufficient evidence for learning.
