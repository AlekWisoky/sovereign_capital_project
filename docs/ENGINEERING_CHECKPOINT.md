# ENGINEERING CHECKPOINT

## Repository state

- Repository: `AlekWisoky/sovereign_capital_project`
- Branch: `architecture-c-contract-tests`
- Commit before this checkpoint: `b5d5d5a861a9da7baf37af4cb9a4180bcc8eee7a`
- This checkpoint commit: the commit containing this file
- Remote working tree: clean/unknown; GitHub cannot observe the separate Termux checkout
- Known Termux state: branch `codex/black-format-repair`, baseline `bbb89205059818862ddd3c904201d7ebc0803055`, only known local modification is `backend/requirements.txt` adding `numpy==2.1.3`
- No runtime behavior, dependency, CI, Render, wallet, signing, or trading configuration was changed by this checkpoint

## Verified and unverified evidence

Verified from repository source and documents:

- FastAPI entrypoint is `backend/victor_ai_bot/server.py:app`.
- Runtime construction goes through `runtime_core.bootstrap`, `runtime_core.coordinator`, and the legacy-backed `RuntimeBundle`.
- The active path is scan → opportunity → enrichment → decision → auto admission → execution → receipt processing → settlement/accounting → replay/telemetry/operator projections.
- Component tests cover quote/discovery, decision, admission ordering, receipt decoding, settlement, capital-write atomicity, replay storage, and operator projections.
- `docs/CURRENT_GOLDEN_PATH.md`, `docs/GOLDEN_PATH_GAPS.md`, and `docs/GOLDEN_PATH_TEST_PLAN.md` document that end-to-end production orchestration is not proven.
- Prior Termux focused authority evidence: `PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py` reported `21 passed` at `bbb8920`; this was not executed by this workspace.
- CI #47 dependency installation, NumPy installation, and Ruff passed; Black failed before Mypy and pytest. Render was not deployed for the repair.

Not verified by this workspace:

- A clean Python 3.11/Linux checkout after the dependency repair.
- Exact current Termux `git status` beyond the user-provided report.
- Full Black repair result, Mypy result, full backend pytest result, Docker build, Render startup, endpoint response, or Golden Path runtime proof.
- A production-valid universal lifecycle identity, durable pending recovery, replacement handling, finality, or reorg handling.

## Current Golden Path

```text
server:app
→ create_app()
→ runtime construction
→ RuntimeBundle / runtime_legacy tick
→ RuntimePrimaryScanFacade._scan_primary_opportunities()
→ arb_engine.find_two_leg_opportunities() or find_three_leg_opportunities()
→ Opportunity
→ runtime profitability/route/capture enrichment
→ DecisionEngine.annotate_and_decide()
→ RuntimeExecuteEntryFacade._execute_auto_entry()
→ RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch()
→ ExecutionService.auto_trade_admission_gate()
→ governance/superstructure pre-execute checks
→ RuntimeExecuteWrapperFacade._run_prepared_auto_execution()
→ execution.try_execute_opportunity()
→ requote / route mutation / calldata / gas / simulation / terminal safety
→ dry-run boundary or signing/submission
→ execution bookkeeping / expected PnL / replay draft / in-memory pending state
→ RuntimeReceiptFacade._receipt_loop()
→ PnLStore.update_receipt()
→ ReceiptService.synchronize_settlement_accounting()
→ CapitalWriteService.commit_receipt_settlement()
→ ledger / bankroll / treasury / capital events
→ replay finalization / audit / telemetry / operator summary
```

The existing closed-loop test is a compatibility/component proof, not a complete production-path proof: it injects synthetic enrichment, uses an admission probe, fabricates transaction and receipt state, calls settlement directly, and does not prove restart reconstruction.

## Money loop

- Source capital is inferred as flashloan, internal prime, or bankroll from opportunity/decision metadata.
- Capital truth and requested USD notional are evaluated by `CapitalAdmissionService.evaluate()`, but the active dispatch path also has a separate ordered `ExecutionService` gate sequence.
- No generic durable reservation ID or reserve/release/settle state machine exists.
- Borrow amount is the first route leg input.
- Intermediate and final amounts are route-leg values; gross profit is final output minus input.
- Slippage uses integer basis-point haircut and updates per-leg `min_out` during requote.
- Pretrade gas is estimated from gas price × gas limit; flash fee uses configured basis points.
- Receipt gas is `gasUsed × effectiveGasPrice`, with later conversion to profit-token or USD units where configured.
- Settlement writes ledger/bankroll/treasury/capital-event state, commonly sharing a generated `capitalCommitId`.
- Replay and audit are evidence surfaces, not economic authority.

There is no single canonical economic truth. Pretrade terminal profitability, decoded receipt truth, PnL, USD conversion, treasury projections, and ledger postings are separate representations. A known risk remains that native gas-denominated values can be subtracted from borrow-token-shaped route values before explicit conversion.

## Profitability stages

| Stage | Implementation | Status |
|---|---|---|
| Scan gross edge | `arb_engine.find_*_opportunities` | Estimate, integer route-token units |
| Scan after-gas metadata | `arb_engine.py` metadata | Estimate, denomination-sensitive |
| Enrichment | `profitability_state.py`, `runtime_services/profitability_truth.py` | Conditional authority contract |
| Route mutation | `requote_opportunity`, route-plan application | Revalidation required; no durable plan revision |
| Terminal gate | `execution.py:check_profit_and_repay` | Pretrade safety gate |
| Receipt truth | `executor_events.py`, `PnLStore.update_receipt` | Receipt-derived, fixture-proven |
| Settlement | `ReceiptService`, `CapitalWriteService` | Component-proven accounting boundary |
| Replay | `ReplayBundleStore` | Evidence only; incomplete reconstruction inputs |

Positive scan-time edge can become negative after quote aging, requote, slippage, gas, fees, capture risk, simulation, or denomination mismatch. The terminal gate blocks many cases, but direct execution and optional integration paths are not universally sealed.

## Latency stages

```text
T0 observation → T1 discovery → T2/T3 quote request/response → T4 opportunity
→ T5 enrichment → T6 decision → T7 admission → T8 preparation → T9 requote
→ T10 route mutation → T11 gas → T12 simulation → T13 signing
→ T14 submission → T15 relay/mempool → T16 inclusion → T17 receipt
→ T18 decode → T19 PnL → T20 treasury commit → T21 replay finalization
```

The code measures parts of execution with `LatencySpan`, submit-to-receipt latency, and in-memory p50/p90/p99 summaries. It does not carry one durable observation timestamp or trace ID from market observation through settlement. Receipt polling can wait up to 180 seconds with a two-second interval; scan budgets are approximately 1500 ms for two-leg and 1600 ms for three-leg discovery.

## Correlation IDs

Current partial lineage:

```text
Opportunity.id → route_id → optional intent_id → replay decision_id/event_id
→ tx_hash → receipt_id → ledger transaction_id → capitalCommitId
```

There is no durable execution-attempt ID, admission ID, replacement lineage ID, or universal trade correlation ID. Proposed future field, not implemented: `trade_correlation_id`, created after decision selection and before admission, immutable across retries/replacements, persisted before reservation/signing, and referenced by reservation, plan revisions, attempts, receipts, settlement, ledger, treasury, replay, audit, and telemetry.

## Rollout state machine

```text
V1_ONLY / flash_arb live label
→ readiness evaluation
→ activation decision
→ capped_live or live
→ realized execution evidence
→ stable multi-strategy rollout

active family → degraded / observe_only / quarantined / disabled
```

`LaunchProfile` defaults to `V1_ONLY`, active family `flash_arb`, and other families `observe_only`; rollout state is persisted through `LaunchRepository`. Secondary-family acceleration expects at least 3 realized executions at 65% success for seed readiness and 5 at 70% for stability. Rollout labels are not equivalent to signing being enabled. Actual execution still depends on `dry_run`, `auto_trading`, keys, executor, governance, simulation, and safety configuration.

## Durability and restart gaps

Durable or persisted: PnL SQLite rows, ledger SQLite plus JSONL mirror, bankroll history, treasury snapshots, capital events, replay JSON/index, audit JSONL, rollout profile, and partial RL/telemetry data.

Primarily in memory: current opportunities, admission context, execution plans, `_pending`, `_receipt_q`, nonce ownership, replacement lineage, receipt finality/reorg state, and rolling latency windows. A crash after submission can lose pending context; a crash between accounting and replay can leave stale evidence; receipt settlement is more idempotent than pending recovery but does not constitute a full lifecycle journal.

## Findings

### P0

- Complete scan-to-settlement Golden Path is not executable without synthetic handoffs.
- Active auto admission and lower-level execution are not one sealed universal boundary.
- No durable pending transaction lifecycle, nonce/replacement policy, confirmation depth, or reorg state machine.
- No generic durable capital reservation protocol.

### P1

- No universal correlation ID.
- Economic truth and denominations are distributed and can conflict.
- Replay omits exact RPC inputs/results, block/state context, nonce, mempool/private relay evidence, and deterministic clock state.
- Route ID is not an immutable execution-plan identity.
- Replay and accounting have separate commit boundaries.
- Goal-to-notional-to-calldata causality is not proven.

### P2

- Render is blocked by dependency/CI/Docker validation; previous startup failed on missing NumPy.
- CI has had dependency constraints and Black-gate failures.
- Runtime coordinator remains a wildcard compatibility shell over `runtime_legacy`.
- Verification reports inventory/configured checks, not successful execution evidence.
- Optional governance/telemetry integrations often fail soft.

### P3

- Latency summaries are not durable and omit a full lifecycle trace.
- File mirrors can diverge from SQLite authority.
- PnL uniqueness and route-plan revision identity need stronger constraints.
- Large compatibility surface and duplicated preflight paths remain.

## Target engineering sequence

1. Isolated dependency/constraints repair.
2. Isolated Black repair.
3. Economic truth/denomination contract.
4. Correlation/lifecycle contract.
5. Deterministic no-capital Golden Path.
6. Durable pending/recovery.
7. Receipt finality/reorg handling.
8. Replay/observability proof.
9. Latency instrumentation.
10. Performance optimization.
11. Render deployment and smoke verification.
12. Later VPS migration.

## Exact next milestone

Complete the isolated Black repair and Python 3.11/Linux validation without touching the primary branch. Then run the existing CI workflow and record actual Black, Mypy, and pytest evidence before any merge or Render deployment.

## Safety state

```text
dry_run=true
auto_trading=false
no private key
no broadcast
```

Live trading is disabled. Render deployment is **NOT yet authorized**. No real wallet, private key, signing, or transaction broadcasting is part of this checkpoint.
