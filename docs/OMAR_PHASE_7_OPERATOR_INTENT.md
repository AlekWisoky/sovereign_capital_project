# OMAR Phase 7 — Decision-Time Operator Intent

## Purpose

Make human input a first-class, auditable learning context without making human controls an execution bypass or allowing later edits to rewrite historical attribution.

## Canonical boundary

`operator controls + wealth goal + AI recommendation`
→ immutable decision-time snapshot
→ canonical `decision_id` / `correlation_id`
→ execution record
→ canonical settled outcome
→ OMAR learning attribution.

## Captured context

- aggressiveness mode
- risk multiplier when supplied
- control mode and brain mode
- defensive mode
- wealth-goal target amount and timeframe
- goal target/current return and drawdown when supplied
- AI recommendation payload when present
- explicit gas/send execution preferences
- deterministic intent fingerprint

The snapshot is deep-copied at the identity boundary and is write-once for that decision. A later operator change therefore affects future decisions but cannot change what OMAR learns about a completed trade.

## Authority separation

Human intent is contextual. It does not replace GMAO/governance, capital admission, internal-prime authority, or execution. `capital_engine_state()` remains the capital authority input. OMAR remains unable to sign, execute, approve capital, or bypass governance.

## Learning semantics

The intent snapshot is attribution metadata, not a new learning state identity. The learner can correlate outcomes with intent while retaining generalization across decisions. The fingerprint is deterministic and contains no raw secret/credential material.

## Validation

`backend/tests/test_omar_operator_intent.py` verifies capture, deterministic fingerprinting, write-once preservation, and propagation at the production decision boundary with OMAR disabled.
