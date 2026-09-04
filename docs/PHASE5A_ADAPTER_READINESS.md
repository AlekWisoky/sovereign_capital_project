# Phase 5A Adapter Readiness

**Status:** static architecture preparation only.  
**Repository:** `AlekWisoky/sovereign_capital_project`  
**Branch:** `architecture-c-contract-tests`  
**HEAD at inventory start:** `636b6a58f91b1fffd20edf927e4c45d54a33a55c`

Authority tests are not proven until executed in a real repository environment. Repository Git history and CI results are the authoritative recovery mechanism.

No adapters, CapitalDemandComposer, reservation writes, runtime wiring, settlement changes, or execution changes are introduced here.

## A. DecisionSnapshot input map

| Future input | Current source/symbol | Current units | Persistence/revision | Mutable/I/O | Classification and composer safety |
|---|---|---|---|---|---|
| Opportunity | `backend/victor_ai_bot/models.py: Opportunity`; `arb_engine.py`; `runtime_primary_scan_facade.py` | raw token/base-unit strings, expected profit strings, route metadata | runtime memory, per-block cache, replay summaries; block-derived IDs | runtime object mutable; quote/RPC reads upstream | `PROVEN` with mocks, `PARTIALLY_PROVEN` live; must be snapshotted outside composer |
| Capital/bankroll | `runtime_services/capital_truth_service.py: CapitalTruthService`; `bankroll.py: BankrollManager` | mixed USD, wei-shaped integers, floats, family allocations | JSON, SQLite, JSONL, capital events, timestamps | reads reconcile state; `next_amount_in()` mutates | `PARTIALLY_PROVEN`/`CONFLICTING`; not safe for pure composer directly |
| Decision | `decision_engine.py: DecisionEngine.annotate_and_decide`; `runtime_services/runtime_decision_facade.py:_safe_decide_opportunities` | `ev_wei`, p-success, float multipliers, gas budget | RL JSON/training JSONL/runtime metadata | mutable learned/runtime/config inputs; file I/O in engine | `PROVEN` component, `HEURISTIC` sizing; composer must receive immutable evidence instead |
| Risk/governance | `runtime_services/runtime_execute_dispatch_facade.py:_prepare_auto_execution_dispatch`; `ExecutionService` gates; risk/drawdown/kill-switch modules | booleans, bps, percentages, policy values | runtime controls, audit, histories/config | handlers may audit/mutate; optional hooks can continue | `PARTIALLY_PROVEN`; adapter must read, not invoke gates |
| Execution plan | `execution.py`; `calldata_builder.py`; `route_encoding.py`; test/production `ExecutionPlanSnapshot` contracts | token/base units, gas wei, deadlines, fee assumptions | runtime metadata, expected PnL, replay | construction may perform RPC/gas/simulation | `PARTIALLY_PROVEN`/`CONFLICTING`; final plan evidence must be assembled outside composer |
| Provider capacity/fee | `execution_capture/flashloan_sizing.py:choose_flashloan_size`; `config.py`; executor callbacks | dimensionless multipliers, bps, callback token units | runtime metadata/config/receipt | heuristic reads; provider observation absent | capacity `HEURISTIC`/`UNPROVEN`, fee `PARTIALLY_PROVEN` after callback |
| Freshness | `latency_profiler.py`; quote block tags/cache; `CapitalTruthService` source freshness; receipt timing | milliseconds, blocks, timestamps | mostly memory and histories | profiler reads time; no policy authority | `PARTIALLY_PROVEN` instrumentation, `UNRESOLVED` policy; composer gets evaluated snapshot only |
| Economic identity | opportunity/route IDs, replay IDs, tx hash, capital commit, ledger IDs | strings/hashes | mixed memory, SQLite, JSONL, replay | generation may mutate/persist | `PARTIALLY_PROVEN` fragments, `UNPROVEN` universal root |

### Current DecisionEngine to execution path

`RuntimeDecisionFacade._safe_decide_opportunities()` reads `capital_engine_state()`, extracts `deployable_bankroll_wei` and `family_allocations_wei`, then calls `DecisionEngine.annotate_and_decide()`. The engine reads config execution/safety values, pending count, gas budget, route statistics, RL state, command-center risk multiplier, and opportunity metadata. A selected `TradeDecision` is passed toward `_maybe_dispatch_auto_trade()` and `_execute_auto()`.

This is legacy runtime composition, not Architecture C. No production `DecisionSnapshot` or `CapitalDemand` is present in this path.

## B. Authority source map

The detailed inventory remains in `docs/AUTHORITY_SOURCE_MAP.md`. Proposed future adapter responsibilities are design-only:

| Snapshot | Current sources | Current status | Future read-only responsibility | Policy dependency |
|---|---|---|---|---|
| `TreasurySnapshot` | `TreasuryLedger`, `LedgerRepository`, `CapitalTruthService`, bankroll, InternalPrime | `PARTIALLY_PROVEN` / `CONFLICTING` | assemble scoped balances, asset units, revisions, provenance, conflicts without reserving | treasury denomination/scope/reservation authority |
| `ConversionSnapshot` | `usd_pricing.py`, `ConversionEvidence`, receipt conversion | `PARTIALLY_PROVEN` / `HEURISTIC` | capture source/target units, decimals, quote/oracle evidence, block/hash, rounding and freshness | conversion/decimal authority and USD role |
| `ProviderCapacitySnapshot` | `flashloan_sizing.py`, provider config/runtime metadata | `HEURISTIC` / `UNPROVEN` | read measured provider capacity in explicit units and revision | provider capacity authority |
| `ProviderFeeSnapshot` | config fee bps, Aave/Balancer callbacks, executor events | `PARTIALLY_PROVEN` / `CONFLICTING` | separate fee schedule/callback evidence and revision | provider fee authority |
| `ExposureSnapshot` | execution gas/fees/slippage, risk, InternalPrime collateral, drawdown/kill-switch | `PARTIALLY_PROVEN` / `UNPROVEN` | expose component vector and conflicts, never invent aggregation | exposure/liability formula |
| `RiskSnapshot` | risk engine, drawdown, kill switch, execution gates | `PARTIALLY_PROVEN` | read policy/state revisions and degraded/conflict markers | risk policy and mandatory gates |
| `GovernanceSnapshot` | governance runtime, command-center controls, pre-execution handlers | `PARTIALLY_PROVEN` | read governance/readiness/operator state without invoking mutation | governance authority and manual approval rules |
| `GoalSnapshot` | `wealth_goal_service.py`, treasury goal config/meta | `PARTIALLY_PROVEN` / `HEURISTIC` influence | read goal posture/revision as constraint only | goal-to-sizing policy |
| `FreshnessSnapshot` | quote block tags, latency profiler, source timestamps | `PARTIALLY_PROVEN` instrumentation / `UNRESOLVED` policy | evaluate explicit-now age/revision state without inventing TTL | freshness and empirical latency horizons |
| `ExecutionPlanSnapshot` | execution/calldata/route builders, test contract | `PARTIALLY_PROVEN` / `CONFLICTING` | capture final material plan identity and evidence; no signing/submission | plan revision and final-plan synchronization |
| `DecisionSnapshot` | no current aggregate source; authority test contract only | `UNWIRED` | compose compatible immutable references and policy revisions; no I/O | all seven authorities and identity policy |

## C. Execution bypass map

### Canonical admitted path, `A`

`RuntimeDecisionFacade._maybe_dispatch_auto_trade()` -> `RuntimeBundle._execute_auto()` -> `RuntimeExecuteEntryFacade._execute_auto_entry()` -> `RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch()` -> `ExecutionService.handle_auto_trade_admission()` / `auto_trade_admission_gate()` -> governance/superstructure preflight -> `RuntimeExecuteWrapperFacade` -> `execution.try_execute_opportunity()`.

Gates: command-center pause/sandbox/defensive controls, fund hold, family, route/capture realism, flash-loan truth, treasury governance, superstructure, governance. No CapitalDemand-like artifact. Execution plan exists downstream. Canonical auto is currently disabled by checked-in `auto_trading: false` and `dry_run: true`, but source is live-capable under external configuration.

### Manual/operator path, `B`

Manual/API helpers and execution-service preparation can reach lower-level execution or simulation without demonstrably producing the same canonical admission artifact. `CapitalAdmissionService.evaluate()` exists as a separate preflight but is not proven to be mandatory for every lower-level caller. Bypass risk: **UNPROVEN / potentially bypassable**.

### API path, `C`

REST routes under `backend/victor_ai_bot/api_routes/` expose execution, simulation, control, withdrawal, and operator surfaces. Exact live-capable caller equivalence requires source enumeration; the repository documents that direct/manual/API paths may reach lower-level functions without the canonical ordered artifact. Classification: **UNPROVEN**, potentially live-capable under configuration; checked-in live posture disabled.

### Test-only path, `D`

`backend/tests/test_current_golden_path_closed_loop.py` calls scanner, `DecisionEngine`, admission probe, `try_execute_opportunity`, PnL, receipt settlement, and replay with synthetic enrichment and a hypothetical submitted transaction. It is characterization evidence only and does not prove production caller safety.

### Legacy path, `E`

`runtime.py` re-exports `runtime_core`; `runtime_core/coordinator.py` wildcard-imports `runtime_legacy.py`. Legacy runtime surfaces remain reachable for compatibility. Their complete execution/admission equivalence is **UNPROVEN**.

### Unknown path, `F`

Any direct import/call of `try_execute_opportunity`, API helper, manual helper, or optional overlay not covered by the canonical facade remains an unknown bypass until static caller enumeration and dynamic fake-submission tests are completed.

## D. Economic identity map

| Identity | Generated/persisted | Retry/replacement/restart | Parent suitability |
|---|---|---|---|
| `Opportunity.id` | scanner/model; runtime/replay summaries | deterministic only within discovery context; not universal durable | opportunity child, not economic root |
| `route_id` | route encoding/scanner/execution metadata | can survive route amount mutation; not plan-complete | route child, not root |
| `decision_id` | replay store content-derived from chain/block/opportunity/route/decision | stable for identical captured decision; not lifecycle identity | replay/decision evidence |
| `event_id` | replay store content-derived; bundle filename/index | stable for same captured event; not trade authority | replay evidence |
| `intent_id` | governance/execution contexts | origin/persistence not universal | candidate intent child; unresolved root policy |
| `tx_hash` | signing/submission; PnL/receipt/replay lookup | changes on replacement; may be absent before submit; durable only where rows exist | transaction attempt only |
| receipt ID | usually tx hash in receipt/settlement | candidate receipt can reorg; no separate finality identity | receipt evidence child |
| `capitalCommitId` | settlement/capital write service | commit-group identity, starts too late | settlement commit child |
| ledger transaction ID | `TreasuryLedger`/`LedgerRepository` | journal identity; file side uses UUID-like generation | accounting child |
| loan ID | InternalPrime allocator/request/loan position | specialized persistence; not universal trade identity | prime-loan child |
| replay identifiers | `ReplayBundleStore` decision/event IDs and event hash | bundle persisted, but input set incomplete for deterministic replay | replay evidence child |

Universal economic identity remains **UNPROVEN**. Candidate hierarchy and unresolved semantics are in `docs/ECONOMIC_IDENTITY_DESIGN.md`.

## E. Pending/recovery map

- Pending map: `RuntimeReceiptFacade`/runtime execution `_pending`, in memory.
- Receipt queue: `_receipt_q`, in-memory async queue.
- Retry state: `_receipt_retry_count`, last error, exhausted state, in-memory pending metadata.
- Nonce: queried during execution where needed; no durable nonce journal/ownership authority proven.
- Replacement: no durable replacement manager or lineage handling proven.
- Confirmation depth: receipt observation exists; no approved depth/finality state machine.
- Reorg: no canonical block-hash tracking/rollback state machine proven.
- Restart: pending map and queue are lost; no source-proven rehydration.
- Dropped transaction: receipt visibility/retry classification exists, but durable dropped policy is absent.

Durable PnL, ledger, capital events, and replay do not replace a pending lifecycle journal. This is the largest operational gap after CapitalDemand composition.

## F. Replay-readiness map

`runtime_subsystems/replay_store.py: ReplayBundleStore` and `runtime_services/replay_service.py` persist atomic hashed JSON bundles and tx indexes. Current bundles include runtime summaries, controls, wealth goal, opportunity summaries, execution plan, receipt, decoded receipt, and reward trace where available.

Missing or incomplete deterministic inputs:

- exact RPC requests/results and provider responses;
- block hash/state root and complete market state;
- all quote edges and cache contents;
- token metadata/decimals and conversion evidence;
- provider capacity and fee snapshots;
- treasury/risk/governance/goal revisions;
- clock values and random/RL state sufficient for reconstruction;
- nonce/account state and private relay response;
- durable lifecycle/replacement/reorg evidence;
- universal economic identity and final settlement linkage.

Current classification: **PARTIALLY_PROVEN forensic replay, UNPROVEN deterministic replay**.

## G. Proposed adapter interfaces, design only

These are names and responsibilities, not production implementations:

```text
read_treasury_snapshot(context) -> TreasurySnapshot
read_conversion_snapshot(context) -> ConversionSnapshot | explicit unavailable/conflict
read_provider_capacity_snapshot(context) -> ProviderCapacitySnapshot | explicit unavailable
read_provider_fee_snapshot(context) -> ProviderFeeSnapshot | explicit unavailable/conflict
read_exposure_snapshot(context) -> ExposureSnapshot | explicit unresolved/conflict
read_risk_snapshot(context) -> RiskSnapshot
read_governance_snapshot(context) -> GovernanceSnapshot
read_goal_snapshot(context) -> GoalSnapshot | explicit unavailable
read_freshness_snapshot(context, now) -> FreshnessSnapshot
read_execution_plan_snapshot(plan_inputs) -> ExecutionPlanSnapshot
read_decision_snapshot(evidence_bundle, now) -> DecisionSnapshot
```

Each future adapter must be read-only, provenance-bearing, source-revision-aware, explicit about missing/conflicting evidence, and incapable of reservation, allocation, signing, submission, or settlement.

## H. Unresolved policy dependencies

1. Treasury denomination and reservation authority.
2. Conversion and decimal authority.
3. Provider capacity and fee authority.
4. Worst-case exposure/liability formula.
5. Strategy budget and concurrent reservation semantics.
6. Durable economic identity origin/persistence.
7. Opportunity freshness and empirical latency horizons.
8. Finality/confirmation depth.
9. Replacement/cancellation and nonce ownership.
10. Reorg handling and provisional settlement.
11. Retention/privacy of identity and replay evidence.
12. Multi-fill semantics.

## I. Exact implementation order after tests become executable

1. Execute and record both authority contract suites; classify failures.
2. Fix only confirmed contract defects; rerun and record.
3. Reconcile the production contract model with `capital_demand.py` without runtime imports.
4. Obtain explicit owner decisions for the seven authorities and lifecycle policies.
5. Define adapter context and source-specific read contracts; still no writes.
6. Implement one read-only adapter at a time with fixture tests and conflict/freshness cases.
7. Assemble DecisionSnapshot in a non-runtime test harness only.
8. Prove deterministic validation and no hidden I/O.
9. Only after separate approval consider CapitalDemandComposer design/wiring.

## Safety boundary

No runtime behavior, test assertions, configuration, persistence, settlement/PnL, Solidity/ABI, signing, submission, reservation, or strategy activation changed in this inventory.
