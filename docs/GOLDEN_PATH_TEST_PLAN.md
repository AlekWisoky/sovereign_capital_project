# Golden Path Test Plan

Goal: the smallest deterministic, no-capital test sequence that proves the current architecture before production behavior changes. The first test uses mock RPC, dry-run execution and a fixed receipt fixture. It must not require a private key, deployed contract, mainnet, or live capital.

## Test 1: deterministic closed-loop golden path

Create one integration test, suggested path `backend/tests/test_current_golden_path_closed_loop.py`, without changing production code.

### Fixed fixtures

- Fixed chain/block: `ethereum`, block `19_000_000`, fixed block hash in fixture metadata.
- Fixed two-edge DEX quote responses returning a profitable borrow-token cycle.
- Fixed gas suggestion and `eth_estimateGas` response.
- Fixed `Opportunity.id`, `route_id`, token decimals and USD price responses.
- Execution config: `dry_run=True`, simulation required, estimate gas required, no signing key.
- Runtime services backed by temporary SQLite and temporary replay directories.
- Fixed capture decision: executable route, selected provider, sizing, private lane, positive post-ordering edge.
- Fixed fund/family/capital/treasury/governance states that admit the trade.
- Fixed `ArbExecuted` receipt fixture with known token profit, gas used, effective gas price, block number and tx hash.
- Frozen clock or injected fixed timestamps wherever IDs or latency assertions depend on time.

### Ordered assertions

1. Call `RuntimePrimaryScanFacade._scan_primary_opportunities` with the mocked quote RPC.
2. Assert exactly one normalized opportunity: stable opportunity ID, route ID, two legs, slippage-aware minOuts, `can_execute=False` at scanner output.
3. Apply the existing runtime profitability/route/capture enrichment used by the tick path. Assert authoritative positive after-cost truth and `exec_ready`.
4. Call `DecisionEngine.annotate_and_decide`; assert selected opportunity/route and bounded sizing.
5. Call `ExecutionService.auto_trade_admission_gate`; assert exact order `hold, family, route, flashloan, treasury`, all allowed, and capture/flash/provider truth present.
6. Invoke the same prepared execution wrapper used by auto trading with dry run. Assert calldata plan exists, ABI route ID matches, estimate and simulation were called, terminal safety includes slippage, flash fee and gas, and no send/sign call occurred.
7. Assert expected PnL row and replay draft/dry-run bundle are created through normal bookkeeping.
8. Promote the same execution record to a synthetic submitted tx only inside the fixture harness, enqueue its fixed tx hash, and feed the deterministic receipt to the receipt-processing boundary.
9. Assert `PnLStore.update_receipt` records status, token profit, gas cost and realized after-gas value in the correct denomination.
10. Assert `ReceiptService.synchronize_settlement_accounting` creates one receipt settlement, one bankroll history event, one treasury snapshot and capital events sharing one `capitalCommitId`.
11. Reapply the same receipt; assert no second ledger/capital mutation.
12. Assert replay finalization references the same opportunity, route and tx hash and contains receipt/reward outcome.
13. Assert execution, submit-to-receipt and settlement telemetry fields are emitted with deterministic values.
14. Build `OperatorSummaryService` output and assert it reports the authoritative receipt, settlement closed-loop state and capital truth.
15. Feed that exact backend payload through mobile projection utilities; assert `dataSource=backend`, no demo seed values, and projection compatibility is healthy.

### Pass criteria

The test passes only if the same lineage can be reconstructed across opportunity ID, route ID, tx hash, receipt ID, ledger transaction ID and capital commit ID, and every persistent write is queryable after recreating service objects from disk. This proves the existing component chain in safe fixture mode; it does not prove live submission or finality.

## Test 2: fail-closed admission matrix

Extend the canonical sequence test with one parameterized blocker per stage:

- degraded fund/capital truth;
- inactive family;
- missing/non-executable route plan;
- capture drop;
- required private lane with public mode;
- unavailable flash-loan sizing/provider;
- treasury governance denial;
- missing requested notional/capital reservation truth;
- non-positive terminal profitability;
- estimate-gas failure;
- simulation revert.

For each case assert: no signing, no submission, no pending queue entry, a stable reason code, replay/audit visibility where configured, and no capital mutation. Existing `test_auto_trade_admission_sequence_contract.py` covers stage ordering but not all side-effect absence.

## Test 3: bypass inventory contract

Statically and dynamically enumerate every caller of `try_execute_opportunity`, every trade/simulate API route and every manual execution helper. Assert each live-capable path produces the same required admission artifact before submission. Mark the test expected-fail until the architecture satisfies it; do not alter production behavior during this audit task.

Required artifact fields: opportunity ID, route ID, decision ID, capture decision, canonical gate result, capital source/notional decision, terminal profitability authority, simulation result and correlation ID.

## Test 4: transaction lifecycle restart and recovery

Design as expected-fail against current source:

1. Submit a deterministic raw transaction through a fake RPC and persist pending state.
2. Destroy and recreate the runtime.
3. Rehydrate pending state and resume receipt polling.
4. Exercise not-found, pending, dropped, replacement, mined, timeout and RPC-error states.
5. Require nonce ownership, old/new tx lineage and exactly-once settlement.
6. Feed a receipt at depth 1, then a conflicting canonical chain; require rollback/re-pending before final settlement.

Current expected result: failure because pending queue/map, confirmation depth, replacement and reorg state are not durable.

## Test 5: flash-loan economics by denomination

Parameterize WETH, USDC (6 decimals) and an 18-decimal non-native borrow token. For Aave and Balancer fixtures assert:

- actual provider fee from fixture/config;
- all leg minOuts;
- final output converted into borrow-token units;
- native gas converted into borrow-token units at the quoted block;
- gross profit minus flash fee minus gas equals terminal after-cost profit;
- on-chain `minProfit` is not falsely treated as including gas;
- receipt realized PnL uses the same token and USD conversion basis;
- mismatched or unavailable denomination fails closed.

Current safety unit tests prove arithmetic, not cross-token denomination correctness.

## Test 6: deterministic replay completeness

Capture all inputs used by Test 1: RPC method/params/results, block number/hash/state root, quote cache, config hash, token metadata/prices, clock, decision seed, route plan, calldata, nonce placeholder, simulated response and receipt. Replay with network access disabled and assert byte-identical opportunity, decision, calldata, admission reasons, PnL and capital events.

Current expected result: failure because replay bundles are forensic summaries and omit several inputs.

## Test 7: Wealth Goal causality

Run the same fixed opportunity under two goal revisions while all market/risk inputs remain fixed. Assert the goal revision and aggressiveness cap are persisted, admission invokes the goal-derived policy, admitted notional changes predictably, calldata borrow amount matches the admitted notional, risk caps dominate any aggressive goal, and settlement feeds the next allocation snapshot. Current expected result is **PARTIALLY PROVEN** until the canonical dispatch call graph demonstrates this.

## Test 8: mobile authority and fallback

In backend mode, provide a complete authoritative command-center response and assert no field equals `DEMO_SNAPSHOT` unless the backend explicitly supplied that value. For command-center failure plus legacy `/api/state`, assert every demo-derived field is either absent or visibly tagged as non-authoritative; fail if demo NAV, allocations, decisions or PnL appear as backend truth. Assert the app's initial source policy is explicit and production builds do not default to mock.

## Smallest execution order

```bash
cd backend
pytest -q \
  tests/test_arb_engine_hardening.py \
  tests/test_execution_preflight_profitability_contract.py \
  tests/test_auto_trade_admission_sequence_contract.py \
  tests/test_execution_hardening.py \
  tests/test_receipt_settlement_truth_path.py \
  tests/test_capital_write_service_atomicity.py \
  tests/test_replay_store_maintenance.py \
  tests/test_operator_receipt_closed_loop_projection_maintenance.py

cd ../mobile
npm test -- --runInBand \
  tests/execution-summary.test.ts \
  tests/capital-truth-health.test.ts \
  tests/projection-compatibility.test.ts \
  tests/wealth-goal-summary.test.ts
```

Then add and run Test 1 alone. Only after Test 1 passes should expected-fail Tests 3, 4 and 6 become implementation work.

## Evidence required before any testnet submission

- Existing focused backend/mobile suite passes from a clean checkout.
- Foundry executor tests pass without ABI changes.
- Deterministic Test 1 passes repeatedly and after process recreation.
- No live-capable API bypasses canonical admission.
- Flash-loan denomination Test 5 passes for deployed token decimals/provider fee.
- Pending lifecycle restart test passes for dropped/replaced/reorg fixtures.
- Mobile backend mode shows no demo-derived financial state.

## Evidence required before live capital

A testnet or fork run must add deployed executor version/owner/allowlist proof, archive-capable block-tag simulation, private relay delivery semantics, confirmation depth, reorg handling, RPC failover, durable pending recovery, treasury reconciliation against on-chain balances, and operator kill-switch drills. Mainnet submission remains out of scope.
