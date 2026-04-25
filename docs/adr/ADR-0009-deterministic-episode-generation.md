# ADR-0009: Deterministic Episode Generation

## Status
Accepted

## Decision
Generate replay bundles and episodes with stable ordering, stable hashing, and integer-only score fields.

## Rationale
Reproducibility is required for replay verification, training data hygiene, and auditability.

## Consequences
- no randomness in episode generation
- stable IDs for identical event inputs
- replay verification endpoint can detect drift
