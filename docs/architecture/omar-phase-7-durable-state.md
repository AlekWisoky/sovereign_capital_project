# OMAR Phase 7 — Durable State

OMAR durable policy and learning state lives beneath the canonical backend data root:

`backend/data/superstructure/omar/`

Runtime code resolves the root through `canonical_data_dir()` rather than maintaining a second data-root convention.

## Persistence contract

- Canonical SQLite settlement ledger remains authoritative for settled trade outcomes.
- OMAR policy checkpoints are a derived learning artifact, not a source of settlement truth.
- Policy state is atomically checkpointed and reloaded at process restart.
- The OMAR learning event stream retains decision/route/transaction lineage needed to audit a policy update.
- Containerized production deployments persist `/app/backend/data`.

## Restart invariant

`trade → canonical settlement → OMAR update → shutdown → restart → reload`

must preserve the learned state and the decision/execution/outcome lineage. A restart must not manufacture a settlement or replay an already-consumed outcome as a new learning observation.
