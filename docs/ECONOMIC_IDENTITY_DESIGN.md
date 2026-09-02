# Economic Identity Design

## Status and scope

**Status:** design-only candidate, not runtime implementation.  
**Repository:** `AlekWisoky/sovereign_capital_project`  
**Branch at design start:** `architecture-c-contract-tests`  
**HEAD at design start:** `7ffd3574e14bce6d220a092e1fa24b13a8b852b8`

This document defines the identity architecture required for Architecture C. It does not create models, persistence, migrations, reservations, execution wiring, settlement changes, or policy approval.

The repository is the source of truth. Repository facts, recommended architecture, and unresolved policy are intentionally separated.

## 1. Current identity sources

### `Opportunity.id`

**Repository fact:** discovery creates deterministic opportunity identity from chain/route/amount/block context and stores it on `Opportunity`.  
**Role:** discovery identity.  
**Limit:** it is created before admission and does not necessarily survive material requote, replacement, restart, or reorg with a durable parent-child chain.

### `route_id`

**Repository fact:** route construction and calldata include route identity; route IDs support route learning and execution correlation.  
**Role:** route-shape identity.  
**Limit:** route identity can outlive changes to amount, quote block, min-outs, slippage, gas, provider, or deadline. It is not a complete economic identity.

### `intent_id`

**Repository fact:** intent-like fields appear in governance/execution contexts.  
**Role:** optional decision or governance identity.  
**Limit:** no repository-wide mandatory origin and persistence contract proves that it spans all lifecycle stages.

### `capitalCommitId`

**Repository fact:** atomic settlement writes can share a `capitalCommitId` across ledger, bankroll, treasury, capital-event, and optional InternalPrime writes.  
**Role:** settlement commit lineage.  
**Limit:** it begins too late to represent opportunity, decision, reservation, signing, or pending state.

### `tx_hash`

**Repository fact:** PnL, receipt processing, replay indexing, and pending processing use transaction hash.  
**Role:** transaction-attempt lookup.  
**Limit:** a replacement transaction has a different hash; no hash exists before signing/submission; a hash cannot represent an economic intent across retries or reorg recovery.

### Receipt identifiers

**Repository fact:** the current settlement path commonly uses `tx_hash` as receipt ID and duplicate key.  
**Role:** observed receipt evidence.  
**Limit:** a receipt can be provisional, can be superseded by a reorg, and is not the same as the economic trade or settlement posting.

### Ledger transaction IDs

**Repository fact:** `TreasuryLedger` and `LedgerRepository` create transaction IDs for journal postings.  
**Role:** accounting-posting identity.  
**Limit:** it represents a journal mutation, not the pretrade decision or transaction attempt. The current file ledger generates UUID-like IDs and repositories do not establish a universal lifecycle parent.

### Replay identifiers

**Repository fact:** replay storage derives `decision_id` and `event_id` from chain/block/opportunity/route/decision context and stores an event hash.  
**Role:** replay evidence identity.  
**Limit:** replay IDs identify captured evidence, not the economic intent; current bundles are forensic and omit some inputs required for deterministic reconstruction.

## 2. Why existing identities are insufficient

No current identity is simultaneously:

- created before capital admission;
- durable across restart;
- stable across retry and replacement;
- explicit across reservation, plan, attempt, receipt, settlement, ledger, and replay;
- independent of route mutation;
- independent of settlement timing;
- safe under reorg and disputed evidence;
- enforced by storage uniqueness and parent-child references.

The current identifiers form a partial lineage, not one authoritative identity graph. Joining by timestamps, route IDs, or tx hashes is unsafe when attempts are replaced, receipts are delayed, or settlement is retried.

## 3. Proposed lifecycle

The proposed hierarchy is:

```text
economic_intent
  |
  +-- reservation
  |
  +-- execution_plan (one or more immutable revisions)
  |      |
  |      +-- transaction_attempt
  |             |
  |             +-- replacement_lineage
  |                    |
  |                    +-- receipt
  |                           |
  |                           +-- settlement
  |                                  |
  |                                  +-- ledger_transaction
  |
  +-- replay_event
```

The hierarchy is a candidate architecture, not an approved production schema.

### Economic intent

Represents one intended economic trade or allocation decision. It is created after an opportunity is selected and the immutable decision evidence exists, but before reservation or signing.

Required properties:

- immutable `economic_intent_id`;
- immutable `trade_correlation_id` or equivalent owner-approved identity;
- opportunity and strategy-family references;
- DecisionSnapshot content hash and policy revision;
- creation evidence and provenance;
- explicit lifecycle state.

One economic intent must not silently become multiple trades because of retries or replacement attempts. If the system intentionally supports multiple fills, that requires an explicit child-intent or fill policy.

### Reservation

Represents the capital and exposure commitment for an economic intent. It binds to the intent, a treasury revision, an exposure vector, family budget policy, and a reservation revision.

A replacement transaction retains the same economic intent and reservation unless an approved policy explicitly creates a new reservation revision. Releasing a reservation is an accounting/lifecycle event, not deletion.

### Execution plan

Represents immutable executable economics for one plan revision: route, amount, quote evidence, min-outs, provider, fee evidence, gas assumptions, calldata, deadline, simulation state, policy revisions, and reservation fit.

A material change to amount, provider, quote, gas, min-outs, calldata, deadline, or policy evidence creates a new execution-plan identity and requires revalidation against the reservation and demand.

### Transaction attempt

Represents one signing/submission attempt. It owns nonce evidence, sender/account identity, send mode, signed-payload reference or digest, submission response, and tx hash when available.

A retry may create a new attempt under the same intent and reservation. The attempt must never be mistaken for a new economic trade.

### Replacement lineage

Represents the relationship between original and replacement/cancel transactions sharing nonce ownership and economic intent. It must retain the original attempt, successor attempt, replacement reason, fee policy revision, and lifecycle state.

The lineage itself is durable and immutable by append-only child events. A tx hash changes; the lineage does not.

### Receipt

Represents observed chain evidence for an attempt: tx hash, receipt payload or canonical digest, block number/hash, status, logs, decoded event reference, observation time, and finality status.

A receipt is initially a candidate. It becomes settlement-eligible only after the approved confirmation/finality policy. Reorged receipts remain evidence but cannot continue to authorize capital availability.

### Settlement

Represents one authoritative economic outcome derived from final receipt/event/gas/provider/conversion evidence. It references the economic intent, reservation, receipt, PnL result, and treasury revision transition.

Settlement must be exactly-once by durable identity. A repeated receipt or worker retry must find the existing settlement rather than post again.

### Ledger transaction

Represents the accounting posting created by settlement or another approved capital mutation. It must reference the settlement and economic intent, but remains distinct because one economic intent may produce multiple accounting postings across domains.

### Replay event

Represents captured evidence for reconstruction. It references the intent and all relevant child identities. Replay identity and event hash provide evidence integrity; they do not authorize economic state.

## 4. Creation, ownership, and persistence

### Creation point

The recommended creation point is the canonical opportunity-to-decision boundary after selection and before CapitalDemand composition/reservation. The exact point is unresolved until the owner approves the DecisionSnapshot and intent policy.

Creating intent earlier risks assigning identities to every scanner candidate. Creating it later leaves capital admission and reservation without a durable root.

### Ownership

- Economic intent: lifecycle/decision authority.
- Reservation: treasury/reservation authority.
- Execution plan: execution-plan authority, bound to intent and reservation.
- Transaction attempt: transaction lifecycle authority.
- Replacement lineage: nonce/transaction lifecycle authority.
- Receipt: chain-observation authority.
- Settlement: authoritative PnL/settlement authority.
- Ledger transaction: accounting repository authority.
- Replay event: replay evidence authority.

No child authority may invent or replace the parent identity.

### Persistence requirements

Every nonterminal identity and relationship must survive process restart. Durable records must support:

- immutable IDs and schema revisions;
- explicit parent IDs;
- unique constraints appropriate to identity type;
- append-only state transitions or guarded revisions;
- timestamps and observation block/hash where relevant;
- source/provenance and content hashes;
- terminal and exceptional states;
- idempotent lookup by parent and child identity.

The in-memory `_pending` map and `_receipt_q` may remain caches in a future design, but cannot be lifecycle authority.

## 5. Immutability and child relationships

Immutable:

- economic intent identity and creation evidence;
- reservation identity and each reservation revision;
- execution-plan identity and material fields;
- transaction-attempt identity and signed-payload digest;
- replacement-lineage identity and parent/child links;
- receipt evidence identity and observed payload digest;
- settlement identity and authoritative outcome evidence;
- ledger transaction identity and journal payload;
- replay event identity and captured-input hash.

Mutable only through append-only lifecycle transitions or new revisions:

- state/status;
- last-observed metadata;
- finality/reorg classification;
- retry counters;
- recovery notes;
- operational timestamps.

Every child must reference its direct parent and the economic intent root. No join may depend only on `tx_hash`, route ID, timestamp, or array position.

## 6. Retry behavior

A failed RPC read, receipt poll, or worker retry does not create a new economic intent. It updates operational state or appends an attempt/recovery event.

A new signing/submission attempt creates a new `transaction_attempt_id` under the same execution plan, reservation, replacement lineage where applicable, and economic intent.

Repeated settlement processing uses the existing settlement identity and must be idempotent. A retry after ambiguous submission remains reserved until lifecycle authority resolves the transaction.

## 7. Replacement behavior

A replacement transaction:

- keeps the same economic intent;
- keeps the same reservation unless policy requires a revision;
- keeps or updates the execution-plan revision only if economics changed;
- creates a new transaction attempt;
- links both attempts through one replacement lineage;
- records nonce, replacement reason, fee policy, and old/new tx hashes;
- cannot create a second PnL trade merely because the hash changed.

If the replacement changes amount, route, provider, or other material economics, it must create a new plan revision and revalidate demand, exposure, risk, simulation, and reservation fit before signing.

## 8. Restart recovery

On restart, the system must reconstruct all nonterminal intents, reservations, plans, attempts, replacement lineages, and candidate receipts from durable storage. It must resume observation from the latest lifecycle state, not from an empty in-memory map.

Recovery must be idempotent and compare-and-swap guarded. A worker discovering an already-settled intent must not post another settlement. A worker discovering an attempt with unknown submission status must preserve reservation and move to an explicit recovery state rather than assume failure.

## 9. Reorg handling

A receipt observed in a non-final block is candidate evidence. If its block is no longer canonical:

1. retain the receipt evidence and block identity;
2. append a `REORGED` transition for the attempt/receipt;
3. keep the economic intent and reservation active or disputed;
4. reverse or mark provisional any pre-final accounting according to approved policy;
5. re-observe the replacement lineage and canonical chain;
6. settle only from final, canonical evidence.

A reorg must never create a new economic intent by default. Finality depth, provisional accounting, and reorg reversal policy remain unresolved owner decisions.

## 10. Settlement linkage

Settlement should be linked by immutable parent references:

```text
economic_intent_id
  -> reservation_id
  -> execution_plan_id
  -> transaction_attempt_id
  -> replacement_lineage_id
  -> receipt_id
  -> settlement_id
  -> ledger_transaction_id
```

`tx_hash` remains an indexed lookup field for chain interaction. `capitalCommitId` remains an accounting commit-group identifier. Neither replaces the intent root.

Settlement must store the authoritative receipt/event/gas/provider/conversion evidence hash and the treasury revision before/after settlement. Caller-supplied values may be retained as observations for reconciliation but must not become authority.

## 11. Replay linkage

Replay events must reference the economic intent and all available child identities. A replay bundle should distinguish:

- decision evidence;
- plan evidence;
- attempt/submission evidence;
- receipt evidence;
- settlement/ledger evidence;
- recovery/reorg evidence.

A replay event may be created before submission and finalized later, but finalization must be append-only or revisioned and must not mutate the meaning of prior evidence silently. Incomplete replay must be labeled incomplete or nondeterministic.

## 12. Required identity invariants

1. One economic intent cannot be counted as multiple trades because of retry or replacement.
2. Every reservation, plan, attempt, receipt, settlement, ledger transaction, and replay event has an explicit parent chain to the intent.
3. IDs are immutable; state changes are append-only or guarded revisions.
4. Unknown submission status retains reservation and enters explicit recovery.
5. Reorged receipts cannot authorize final settlement or capital release.
6. Settlement is exactly-once and idempotent.
7. Material plan changes create a new plan identity and trigger revalidation.
8. Identity records include provenance, schema revision, and content identity where applicable.
9. Replay evidence cannot authorize capital or replace accounting authority.
10. Missing identity or broken lineage fails closed for any future live-capable path.

## 13. Unresolved policy decisions

Repository evidence is insufficient to approve the following:

- exact economic-intent creation boundary;
- whether one intent may produce multiple fills;
- cross-chain identity scope;
- public/API exposure of identity fields;
- finality depth and provisional settlement policy;
- replacement/cancellation and nonce ownership policy;
- whether plan changes create a new reservation revision or a new intent;
- retention, privacy, and redaction requirements;
- owner and operator authority for disputed/reorged states.

These remain **UNRESOLVED**. The seven authority decisions, especially treasury/reservation, exposure, and freshness, must be approved before implementation.

## 14. Implementation dependencies and no-go boundary

Required before production identity implementation:

1. Owner approval of the seven authority decisions or explicit identity-specific policy boundaries.
2. Production snapshot schemas for DecisionSnapshot, Treasury, Exposure, Risk, Governance, and Freshness.
3. Read-only authority adapters with provenance, revisions, freshness, and conflict states.
4. Approved reservation lifecycle and concurrency semantics.
5. Durable persistence design and uniqueness constraints.
6. Pending/replacement/reorg lifecycle design.
7. Settlement authority design that rejects caller-controlled economics.
8. Replay evidence envelope and identity redaction policy.
9. Contract tests before runtime integration.

Forbidden before those conditions:

- wiring identity into live execution;
- changing PnL/settlement semantics;
- creating reservation writes;
- modifying DecisionEngine or CapitalDemand runtime composition;
- changing Solidity/ABI or production configuration;
- enabling live trading.

## 15. Status classification

- Existing identity sources: **PARTIALLY_PROVEN** as component fields.
- Universal durable economic identity: **UNPROVEN**.
- Proposed hierarchy: **CANDIDATE**, not approved policy.
- Replacement/reorg/restart semantics: **UNPROVEN**.
- Settlement and replay linkage: **UNPROVEN** end to end.

## References

- `docs/SOVEREIGN_OS_CONTEXT.md`
- `docs/SOVEREIGN_OS_STATE.md`
- `docs/SOVEREIGN_OS_DECISIONS.md`
- `docs/WORKSPACE_CHECKPOINT.md`
- `docs/AUTHORITY_DECISION_PACKET.md` when present on the branch
- `docs/CURRENT_GOLDEN_PATH.md`
- `docs/GOLDEN_PATH_GAPS.md`
- `docs/GOLDEN_PATH_TEST_PLAN.md`
- `backend/tests/test_authority_snapshot_contracts.py`
- `backend/victor_ai_bot/capital_demand.py`
- `backend/victor_ai_bot/runtime_services/runtime_receipt_facade.py`
- `backend/victor_ai_bot/runtime_services/receipt_service.py`
- `backend/victor_ai_bot/runtime_subsystems/replay_store.py`
- `backend/victor_ai_bot/treasury/ledger.py`
- `backend/victor_ai_bot/persistence/repositories/ledger_repository.py`
- `backend/victor_ai_bot/pnl.py`
