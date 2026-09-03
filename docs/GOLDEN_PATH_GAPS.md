# Golden Path Gaps

Basis: current repository HEAD `52d9669bda8c44d3ed74ab3df8bb5f572ff72fb2`, compared with the uploaded prior `SYSTEM_DEEP_DIVE.md`. The prior document is not present in the repository at this HEAD.

## Material differences from prior audit

1. **Settlement is materially more connected than the prior audit states.** `ReceiptService.synchronize_settlement_accounting` now constructs canonical receipt ledger transactions, and `CapitalWriteService.commit_receipt_settlement` atomically writes ledger, bankroll history, treasury snapshot, capital events and optional internal-prime state. `test_capital_write_service_atomicity.py` proves shared `capitalCommitId` and rollback.
2. **Canonical auto admission is now explicit and tested.** `ExecutionService.auto_trade_admission_gate` orders fund hold -> family readiness -> route/capture realism -> flash-loan truth -> treasury governance, with fail-closed short-circuit tests in `test_auto_trade_admission_sequence_contract.py`.
3. **Execution Capture can gate the canonical auto path.** A capture `drop`, private-lane conflict, non-positive post-ordering edge, missing executable route plan or missing capture-derived profitability truth blocks auto admission. It is still not universal because lower-level execution is callable directly.
4. **Wealth Goal influence is stronger but still not source-proven end to end.** Goal posture produces `aggressivenessCap`; `AdmissionService.apply_family_budget` can scale opportunity size, and treasury goal/aggressiveness affects the treasury gate. The canonical dispatch path does not visibly prove this sizing method is mandatory.
5. **Transaction lifecycle and replay conclusions are unchanged.** Receipt retries improved failure visibility, but pending state remains in-memory and deterministic replay still lacks market/RPC/nonce/mempool snapshots.
6. **Mobile fallback risk is confirmed, not merely suspected.** `useCommandCenter` defaults to `mock`; backend fallback overlays `DEMO_SNAPSHOT` and labels it `backend-mock`.

## P0

### P0.1 No durable transaction lifecycle

`RuntimeReceiptFacade` consumes an in-memory queue and map. Restart loses active polling context; no source-proven pending rehydration, nonce journal, dropped transaction detector, replacement/cancel policy, confirmation depth, canonical block hash tracking, or reorg rollback exists. A submitted trade can therefore remain unsettled or be settled against a non-final receipt.

### P0.2 Safety/admission is bypassable

The canonical auto path is strong, but not non-bypassable. `execution.try_execute_opportunity` enforces terminal economics and optional simulation/MEV checks, yet it does not require the canonical fund/family/capture/treasury/governance admission artifact. Manual/API/direct callers must be proven or changed later to call one sealed execution boundary.

### P0.3 Capital admission is not one reservation protocol

The dispatch path proves hold/family/route/flash/treasury gates, while `CapitalAdmissionService.evaluate` provides requested-notional and capital-source checks through another preflight path. A durable reservation ID and reserve/release/settle state machine are absent. Flash loans reduce principal-capital need but do not remove gas, collateral, inventory or operational exposure admission.

### P0.4 End-to-end money-loop proof is missing

Component tests prove receipt settlement and atomic capital writes, not `scan -> decision -> admission -> dry-run -> expected PnL -> receipt -> realized PnL -> treasury -> next allocation` in one deterministic test. Until that exists, the money loop is **PARTIALLY PROVEN**, not production-proven.

## P1

### P1.1 No universal correlation ID

`Opportunity.id`, `route_id`, `decision_id`, `event_id`, `intent_id`, `tx_hash`, ledger `transaction_id`, receipt ID and `capitalCommitId` form a lineage, not one enforced correlation key. Failure analysis requires joins that are not guaranteed.

### P1.2 Flash-loan denomination and fee truth are configuration-dependent

`check_profit_and_repay` subtracts configured flash fee and gas from final minOut using integer units. That is correct only when borrow token, final output and gas cost share denomination. Receipt code converts gas into the profit token, but pretrade safety generally treats native gas wei as borrow-token wei. Provider callback fee is authoritative on-chain, while backend uses configured bps.

### P1.3 Successful receipt without decoded profit blocks settlement, but recovery is incomplete

Fail-closed behavior is good: missing realized truth disables auto trading. Recovery remains manual and can leave PnL, replay and pending state in different completion phases.

### P1.4 Replay is forensic, not deterministic

Bundles contain runtime summaries, controls, goal, top opportunities, execution plan and final receipt. They omit exact RPC request/response payloads, block hash/state root, quote cache, all input edges, nonce/account state, private relay result, deterministic time and random seeds. A failed trade cannot be exactly reconstructed.

### P1.5 No market-data-to-settlement latency trace

Execution stage timing starts inside execution; submit-to-receipt is separate. There is no market observation timestamp carried through opportunity, decision, submission, receipt and capital commit.

### P1.6 Mobile can present demo-shaped values under backend mode

The explicit mock mode is honest, but the legacy backend fallback merges `DEMO_SNAPSHOT` while setting `dataSource: backend`. `liveMode: backend-mock` is available, yet screens can still render demo NAV, allocations and decisions unless every component prominently gates on it.

## P2

### P2.1 Wealth Goal influence is fragmented

Goal posture, treasury aggressiveness and capture family sizing are separate. No test proves a goal revision changes admitted notional, calldata amount, and later treasury state while respecting risk caps.

### P2.2 Optional integration failures are frequently swallowed

Governance, superstructure, capture learning, telemetry and operator overlays often catch narrow runtime errors and continue. This is appropriate for observability, dangerous for controls unless the mandatory boundary owns the fail-closed rule.

### P2.3 PnL row uniqueness is not enforced

`trades.tx_hash` is indexed but not unique. `update_receipt` updates all matching rows. Duplicate execution bookkeeping can distort summaries even though settlement itself checks duplicate receipt IDs.

### P2.4 Replay and capital stores have separate commit boundaries

Replay JSON finalization is outside the SQLite capital transaction. A settled trade can have authoritative accounting and a stale replay bundle, or vice versa.

### P2.5 Route identity can outlive route amount mutation

Notional requoting updates amounts/minOuts but route ID hashes venues/tokens/aux, not amount, block or slippage. This is useful for route-family learning but insufficient as a unique execution-plan identity.

## P3

### P3.1 Latency percentiles omit p95 and durable traces

Rolling p50/p90/p99 are in-memory. They reset on restart and cannot prove cross-process latency or incident history.

### P3.2 RPC reads have no semantic retry/backoff policy

Batch incompatibility falls back to individual calls, but transient quote/estimate/simulation errors mostly fail or wait for the next tick. There is no request-level trace ID.

### P3.3 File mirrors can diverge from canonical SQLite

Capital writes commit SQLite first, then best-effort mirror updates. Read surfaces must consistently treat repositories as authority and expose mirror degradation.

## Disconnected or configuration-dependent components

- `CapitalAdmissionService.evaluate` is substantial, but its requested-notional decision is not visibly part of `_prepare_auto_execution_dispatch`; prove the actual call graph before claiming mandatory capital admission.
- `AdmissionService.apply_control_and_risk_gates` and `apply_family_budget` exist, but the canonical auto gate is implemented separately in `ExecutionService`.
- FIOA, superstructure, consensus, governance and MEV integrations are flag/object dependent; some failures continue rather than block.
- Simulation and estimate-gas enforcement depend on safety flags.
- Live signing/submission depends on private key, executor deployment, ABI v2 compatibility, owner/allowlists, RPC/provider support and token/pool config.
- Private submission has no relay-neutral delivery/finality proof.
- The contract enforces repayment, provider callback identity, minOut and minProfit, but backend pretrade gas/fee denomination remains off-chain configuration truth.
- Wealth goal and treasury modules persist state, but one authoritative goal-to-notional policy is not proven.

## Minimum infrastructure still missing for production proof

- Durable pending transaction journal with restart recovery.
- Nonce ownership and replacement policy.
- Confirmation-depth and reorg state machine.
- Universal `trade_correlation_id` propagated to opportunity, decision, admission, tx, PnL, replay, ledger, telemetry and UI.
- Durable capital reservation/release/settle records.
- Deterministic RPC/market fixture capture for replay.
- One sealed execution API used by auto, manual, API and tests.
- UI authority contract that never mixes demo numbers into backend-live state.
