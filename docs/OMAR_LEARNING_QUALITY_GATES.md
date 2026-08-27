# OMAR Learning-Quality / Evaluation Gates

Phase 10 separates **learning-data integrity** from **policy-performance promotion**.

## Gate A — transition integrity

The Phase 9 gate remains the first barrier. A policy update is rejected unless the settled record is canonically attributed to the pending decision, correlation ID, opportunity, route, and action; settlement truth is verified; and the learning context carries the actual `capital_engine_state` authority with usable status/freshness.

## Gate B — dataset quality

`evaluate_learning_quality()` evaluates the accumulated settled learning events for:

- minimum observation count
- action coverage across the six OMAR actions
- state coverage
- settlement-truth verification rate
- complete decision/correlation lineage
- duplicate learning identity
- finite reward values

This gate answers: **is the training evidence structurally trustworthy enough to use?**

## Gate C — performance promotion (separate)

A quality pass is **not** proof that OMAR is profitable or better than the existing policy. Promotion requires an out-of-sample evaluation against an explicit baseline. The production system must not infer superiority from in-sample reward or observation count alone.

The next integration step is to expose Gate B through the runtime and require it, together with Gate A and the durable identity check, before OMAR's learned recommendation can influence live decisions.

## Authority boundary

These gates are learning controls only. They do not approve capital, sign transactions, bypass governance/admission, or create an alternate execution path. `capital_engine_state()` remains the capital-authority input; the canonical settled outcome ledger remains the outcome authority.
