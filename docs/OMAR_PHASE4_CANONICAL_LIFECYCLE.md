# OMAR Phase 4 — Canonical Decision / Execution / Settlement Lifecycle

Phase 4 closes the remaining lineage boundary between OMAR and the real runtime.

## Canonical flow

`market -> strategy -> decision -> correlation -> governance -> execution -> canonical settled outcome -> exact action attribution -> OMAR update`

## Capital authority

OMAR does not maintain a second capital model. Its decision context reads the runtime's existing `capital_engine_state()` and carries forward:

- available capital
- allocatable/deployable capital
- family allocations
- authority status/freshness
- capital source
- stable internal-prime economics (availability, capacity, cost)

Missing authority remains unavailable and is never interpreted as approval.

## Lineage

The bridge persists:

- `canonical_decision_id`
- `correlation_id`

on both the selected opportunity metadata and decision metadata. Correlation identifiers remain lineage data and are excluded from the OMAR learning state key.

## Settlement boundary

OMAR learning is triggered only after a canonical outcome source reports a settled/closed/completed outcome. A transaction receipt alone is not considered sufficient economic truth.

The bridge searches the runtime's canonical outcome ledger surfaces and supports common settled lookup methods without creating a second outcome store.

## Safety

The bridge is additive and fail-closed:

- OMAR cannot authorize capital.
- OMAR cannot bypass governance.
- OMAR cannot sign or submit transactions.
- Learning failures cannot break execution bookkeeping.
- Unsettled outcomes do not update policy.
