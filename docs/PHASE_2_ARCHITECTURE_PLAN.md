# Phase 2 Architecture Plan

Baseline: audit commit `e7c9ba2`, repository source at parent commit `52d9669`. This is a read-only design plan. No production behavior, ABI, public API, trading mode, or contract is changed by this plan.

## Executive position

Do not start with a refactor. The safest sequence is: characterize the current path with one fixture, add an additive lineage field, seal execution behind a compatibility-preserving boundary, persist lifecycle state, then make replay inputs complete. The integrated proof runs after each boundary is observable. Keep the existing auto path and lower-level functions temporarily intact, but make live submission impossible unless a validated admission artifact is present.

## Current boundaries and evidence

- Discovery: `runtime_services/runtime_primary_scan_facade.py` -> `arb_engine.find_two_leg_opportunities` / `find_three_leg_opportunities` -> `JsonRpcClient` and quote adapters. Existing evidence: `test_arb_engine_hardening.py` and quote/RPC tests.
- Decision: runtime decision facade -> `DecisionEngine.annotate_and_decide` -> `TradeDecision`. Existing evidence: decision/RL hardening tests.
- Canonical auto admission: `runtime_services/runtime_execute_dispatch_facade.py` -> `ExecutionService.handle_auto_trade_admission` -> `auto_trade_admission_gate`, ordered hold, family, route/capture, flash-loan, treasury gates. Existing evidence: `test_auto_trade_admission_sequence_contract.py`.
- Execution: `runtime_execute_wrapper_facade.py` -> `execution.try_execute_opportunity` -> route plan, calldata, gas, simulation, safety, signing, RPC send. Existing evidence: execution hardening, preflight, calldata, gas, safety tests.
- Settlement: `runtime_receipt_facade.py` -> `PnLStore.update_receipt` / `decode_arb_executed` -> `ReceiptService.synchronize_settlement_accounting` -> `CapitalWriteService.commit_receipt_settlement`. Existing evidence: receipt truth, flash-loan lifecycle, capital-write atomicity tests.
- Replay/operator: `ReplayService` / `ReplayBundleStore`, telemetry services, `OperatorSummaryService`, mobile `commandCenter/provider.ts` and `useCommandCenter.ts`. Existing evidence: replay, operator projection, mobile projection tests. No complete fixture crosses all boundaries.

## Gap 1: one correlation/trade ID

### Current implementation and lineage
Current records use `Opportunity.id`, `route_id`, optional governance `intent_id`, deterministic replay `decision_id`/`event_id`, `tx_hash`, receipt ID, ledger `transaction_id`, and settlement `capitalCommitId`. `pnl.py` stores opportunity, route, and tx hash but no universal field. `ReplayBundleStore` derives decision/event IDs from opportunity, route, block, mode, RL state/action. `ReceiptService` joins settlement by tx hash and creates a separate capital commit ID.

Affected flow: scanner -> `Opportunity`; decision engine -> `TradeDecision`; execution service -> expected PnL/pending/replay; receipt facade -> `_pending` lookup and receipt queue; PnL -> SQLite; receipt service/capital writer -> ledger/repos/events; telemetry/operator/mobile projections.

### Existing evidence
`test_capital_write_service_atomicity.py` proves one `capitalCommitId` across settlement writes. `test_receipt_settlement_truth_path.py`, lifecycle persistence, replay store/service, and operator closed-loop tests prove partial lineage only. No test asserts one ID across all stages.

### Smallest safe change
Introduce an additive `trade_correlation_id` generated once at the canonical opportunity-to-execution boundary, preferably in the runtime auto-entry/admission context. Carry it in `Opportunity.meta`, `TradeDecision` metadata, admission plan, execution plan, pending row, PnL row, replay bundle, receipt/ledger metadata, capital events, telemetry, and operator summaries. Preserve all existing IDs and fields. For old/manual callers, generate a compatibility ID at the boundary and mark `correlation_origin=compatibility`.

Do not replace `tx_hash`, route ID, replay event ID, or capital commit ID. Do not put the correlation ID in calldata or the contract ABI.

### Risks and independence
Independent as an additive schema/data change, but lifecycle, replay, and the integrated fixture depend on it. Risks are missed propagation, duplicate generation, and accidental public response/schema coupling. Public API risk is low if fields are additive and redacted consistently; ABI risk is none. Persistence migrations must be additive and tolerant of old rows.

### Proof test
A lineage test creates one trade, asserts the same correlation ID in opportunity metadata, decision/admission artifacts, execution/PnL row, pending state, replay, receipt settlement, ledger metadata, capital events, telemetry, and operator summary. Recreating readers from disk must retain it.

## Gap 2: restart-safe transaction lifecycle

### Current implementation and lineage
`execution.py` returns a tx hash after signing/submission. `ExecutionService` records expected PnL and runtime bookkeeping. `RuntimeReceiptFacade` keeps `_pending` and `_receipt_q` in memory, then calls `JsonRpcClient.wait_for_receipt` with a 180-second timeout and 2-second polling. Receipt failures retry up to three times if no receipt was seen. `tx_confirmation.assess_submitted_tx` classifies mined, pending, sent, or receipt-unavailable but does not persist state or manage replacements.

Affected callers/callees: execution wrapper -> `_record_exec`; `_record_exec` -> pending map/receipt queue/PnL/replay; receipt loop -> RPC receipt/tx lookup -> PnL/settlement; API receipt endpoint and operator summaries read lifecycle projections.

### Existing evidence
`test_pending_state_context_maintenance.py`, receipt facade tests, `test_receipt_settlement_truth_path.py`, and execution lifecycle tests cover in-process semantics and retries. No restart, rehydration, replacement, dropped transaction, confirmation-depth, or reorg test exists.

### Smallest safe change
Add a durable `pending_transactions` repository/table in the existing SQLite persistence layer. Persist the submission envelope before or atomically with queueing: correlation ID, tx hash, chain, sender, nonce, raw/hashed transaction reference, route/opportunity IDs, admission artifact hash, submitted block, send mode, timestamps, attempt number, replacement lineage, lifecycle state, and last observed block hash. On startup, rehydrate nonterminal rows into the receipt worker. Keep `_pending` as a cache, not authority.

Phase 1 should support states `submitted`, `visible`, `mined_candidate`, `settled`, `reverted`, `timed_out`, `dropped`, `replacement_pending`, `reorged`, `manual_recovery`. Do not implement automatic replacement until nonce ownership and fee policy are explicitly specified. Require confirmation depth before final settlement, with a configurable safe default that preserves current behavior in dry-run/test fixtures.

### Risks and independence
Depends on correlation ID for stable joins and on the existing idempotent settlement checks. Can be implemented independently of deterministic replay, but the replay bundle should reference lifecycle state. Public APIs should expose additive status fields only. ABI risk is none. Main risks are duplicate settlement, startup races, and treating a stale receipt as final.

### Proof test
Use a fake RPC and SQLite: submit, persist pending, destroy runtime, recreate runtime, rehydrate, observe pending then mined, settle exactly once, simulate timeout/dropped/replacement/reorg branches, and verify old/new tx hashes share the same correlation ID and settlement receipt is idempotent.

## Gap 3: deterministic replay inputs

### Current implementation and lineage
`ReplayService.create_bundle` captures runtime context, controls, wealth goal, top opportunity summaries, execution plan, and outcome. `ReplayBundleStore` writes atomic JSON and indexes tx hash to event ID; finalization adds receipt, decoded receipt, and reward trace. It does not capture exact RPC calls/results, block hash/state, quote cache, complete edge inputs, token decimals/prices, nonce, deterministic clock/random state, or private relay response.

Affected callers/callees: scan/quote/RPC -> cache and opportunities; decision engine -> seeded selection plus evolving RL stats; execution -> gas/simulation/calldata/signing; replay service/store -> JSON bundle; receipt finalization -> replay finalizer; replay verification/API/mobile replay surfaces.

### Existing evidence
`test_replay_service_stage6.py`, replay store maintenance, RFT schema/ID tests, and lifecycle replay hooks prove persistence and hashing. They do not prove offline byte-identical reconstruction.

### Smallest safe change
Add a versioned `ReplayInputEnvelope` stored beside the existing bundle, not a breaking replacement. Capture canonicalized RPC request/response records, block identity, quote cache entries, config/policy hashes, token metadata/prices, clock/random seeds, decision inputs, route plan, calldata, nonce placeholder, simulation/estimate results, and receipt fixture. Use redaction/encryption policy for secrets: never store private keys or raw secrets. Define a stable serialization and schema version. Replay must run offline against the envelope and report `complete`, `incomplete`, or `non_deterministic` rather than silently claiming determinism.

### Risks and independence
Depends on correlation ID for joining all records and on the closed-loop fixture to identify the minimum input set. It is independent of lifecycle persistence for dry-run replay, but submitted-trade replay needs durable lifecycle state. Public API risk is additive bundle fields and a stricter verifier result; ABI risk none. Storage growth, sensitive data leakage, and nondeterministic timestamps are the main risks.

### Proof test
Record Test 1 inputs, disable network, recreate services, replay twice, and assert byte-identical opportunity, decision, admission reason, calldata, expected/realized PnL, capital events, and replay hash. A deliberately incomplete envelope must fail closed as incomplete.

## Gap 4: bypassable execution safety/admission

### Current implementation and lineage
The canonical auto path goes through `RuntimeExecuteEntryFacade` -> `RuntimeExecuteDispatchFacade` -> `ExecutionService.auto_trade_admission_gate` and later governance -> `RuntimeExecuteWrapperFacade` -> `execution.try_execute_opportunity`. `try_execute_opportunity` itself enforces terminal profitability and optional simulation/MEV checks, but it does not require the full admission artifact. `CapitalAdmissionService.evaluate` is used by `ExecutionService.prepare_auto_execution`, while dispatch uses a separate ordered admission path. `AdmissionService.apply_control_and_risk_gates` and `apply_family_budget` are separate helpers. Mobile/API exposes trade and simulate routes, and direct/internal callers can reach lower layers.

Affected callers: auto runtime, API opportunity trade/simulate routes, manual execution helpers, tests/fixtures, runtime legacy compatibility seam, execution wrapper, governance/FIOA/superstructure optional layers.

### Existing evidence
`test_auto_trade_admission_sequence_contract.py` proves canonical order and short-circuiting. Execution safety/preflight tests prove lower-level gates. `test_execution_service_auto_trade_hold.py`, API route tests, and capture tests cover pieces. No static/dynamic proof enumerates every live-capable caller and requires one artifact before submission.

### Smallest safe change
Define an internal `ExecutionAdmissionArtifact` with required fields: correlation ID, opportunity/route IDs, decision ID, capture decision, capital admission, governance/risk result, terminal profitability authority, simulation/estimate result, and policy/config version. Add a single `ExecutionBoundary` adapter that accepts the artifact and calls the existing `try_execute_opportunity`; reject live submission when the artifact is absent, stale, invalid, or not approved. Initially preserve `try_execute_opportunity` for dry-run/tests and route all live-capable API/manual paths through the adapter. Do not rename or remove the existing public functions.

The boundary must distinguish `dry_run` from live: dry-run may inspect plans without a full live admission, but every result must say `observe_only` and never sign/send. Avoid optional fail-open behavior for mandatory gates; optional learning/telemetry remains best effort after the boundary.

### Risks and independence
Depends on correlation ID and on a clear artifact contract. It can be implemented before durable lifecycle, but live safety proof is stronger after lifecycle persistence because admission artifacts need durable linkage. Public API risk is controlled by additive error/status fields; ABI risk none. Main risk is accidentally blocking current safe dry-run tests or allowing a compatibility caller to claim approval without evidence.

### Proof test
Enumerate all source callers and API routes. For each live-capable path, use a fake signer/RPC and assert submission is impossible without the artifact, impossible with a stale/failed artifact, and possible only with the exact ordered gate result. Verify auto, manual, API, and direct compatibility calls produce the same rejection semantics.

## Gap 5: one deterministic closed-loop fixture

### Current implementation and lineage
The intended chain is scan facade -> arb engine/quotes -> Opportunity -> runtime enrichment/DecisionEngine -> auto admission -> execution dry run/submission bookkeeping -> PnL -> receipt facade -> event decoder -> ReceiptService -> CapitalWriteService -> replay/telemetry/operator/mobile. Existing tests are component tests and use separate runtime doubles; no test crosses all boundaries.

Affected callers/callees: all components above, plus SQLite persistence, replay files, fake RPC, operator summary and mobile projection utilities.

### Existing evidence
Arb hardening, execution preflight, admission sequence, receipt settlement truth, capital-write atomicity, flash-loan lifecycle, replay service, and operator projection tests each prove slices. The prior `GOLDEN_PATH_TEST_PLAN.md` already sketches the required sequence.

### Smallest safe change
Add one integration test and fixture harness only. Do not add production abstractions first. Use a fixed block, mock quote/gas/simulation RPC, dry-run execution, synthetic `ArbExecuted` receipt, temporary SQLite/replay directories, deterministic clock/random state, and a fully admitted capture/governance/capital fixture. Assert all writes and projections, then recreate readers from disk. This test is the contract that later phases must preserve.

### Risks and independence
The fixture can be written independently as a characterization test, but it will expose the other four gaps. It should start before production changes and be expanded after each fix. No public API or ABI changes are required. Main risk is building a fake path that bypasses the actual runtime wrappers; call the same facades and normal bookkeeping used in production.

### Proof test
The fixture itself: one opportunity from scan to dry-run, synthetic receipt to realized PnL and atomic treasury settlement, replay finalization, telemetry, operator summary, mobile backend projection, duplicate receipt, and process recreation checks.

## Dependency graph and smallest implementation order

```text
Phase 2A: closed-loop characterization fixture (tests only)
        |
        +--> Phase 2B: additive trade_correlation_id propagation
        |          |
        |          +--> Phase 2C: durable pending/lifecycle repository
        |          |          |
        |          |          +--> Phase 2D: deterministic replay envelope
        |          |
        |          +--> Phase 2E: sealed execution admission boundary
        |                     |
        |                     +--> Phase 2F: final integrated proof and bypass matrix
        ```

Recommended reviewable commits:

1. **Tests only:** add the deterministic closed-loop fixture in dry-run mode; no production changes.
2. **Additive lineage:** add and persist `trade_correlation_id`; preserve all old IDs and APIs.
3. **Lifecycle persistence:** add pending repository, startup rehydration, state transitions, exactly-once settlement, then dropped/replacement/reorg tests.
4. **Admission boundary:** add the internal artifact and route all live-capable callers through it; keep lower-level direct API for dry-run compatibility only.
5. **Replay envelope:** capture complete deterministic inputs and offline verifier; preserve old forensic bundle fields.
6. **Final proof:** extend the fixture to restart, replay offline, enumerate bypasses, and prove mobile/operator authority.

This order is intentionally conservative: the first commit proves the current system, correlation gives every later store a join key, lifecycle protects submitted state, the sealed boundary removes bypasses, and replay captures the now-stable lineage.

## Compatibility and rollout constraints

- Add fields and tables; do not rename or remove existing fields.
- Keep ABI v2 and all contract addresses unchanged.
- Keep `try_execute_opportunity` callable for dry-run and test harnesses; deny live mode without a valid admission artifact after the boundary lands.
- Default new live behavior to fail closed; default dry-run behavior to remain safe and non-submitting.
- Migrate old rows lazily with null/compatibility correlation IDs, never guess lineage.
- Use feature flags only for observation/shadow instrumentation, never to bypass mandatory safety.
- Do not mark a phase complete from unit tests alone; require the integration evidence described below.

## Exit criteria for Phase 2

Phase 2 is complete only when: one correlation ID is queryable across every durable surface; restart rehydrates and settles pending transactions exactly once; replay can reproduce a captured fixture offline or explicitly reports incomplete; every live-capable caller reaches one admission boundary; and the closed-loop fixture passes repeatedly with no live capital or mainnet submission.
