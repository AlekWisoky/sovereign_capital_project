# Phase 2 Test Matrix

Baseline: audit commit `e7c9ba2`. This matrix is design-only. Tests must use mocks, fixtures, dry-run, temporary SQLite/files, and offline replay. No live trading, ABI change, or production behavior change is part of this phase.

## Status and test classes

- **Existing**: already present in the repository and useful as evidence.
- **Additive**: new test or fixture with no production behavior change.
- **Expected-fail**: intentionally demonstrates a current proof gap; do not treat failure as a regression.
- **Gate**: must pass before the next implementation phase.

## Matrix

| ID | Proof target | Current boundary | Existing evidence | New test / assertion | Class | Dependencies | Pass condition |
|---|---|---|---|---|---|---|---|
| T2-01 | Current closed-loop characterization | scan facade -> execution wrapper -> receipt/capital/operator/mobile | `test_arb_engine_hardening.py`, execution preflight, admission sequence, receipt truth, capital atomicity, operator projection, mobile projection | `test_current_golden_path_closed_loop.py`: fixed scan, one opp, decision, admission, dry-run, synthetic receipt, PnL, settlement, replay, telemetry, operator and mobile projection | Additive / Gate | none for test-only baseline | Same fixture lineage and expected balances survive service recreation; no signer/send call |
| T2-02 | Exact canonical admission order | `ExecutionService.auto_trade_admission_gate` | `test_auto_trade_admission_sequence_contract.py` | Parameterize every blocker and assert short-circuit, stable reason, no side effects, no pending/capital mutation | Existing + extend / Gate | T2-01 | Only stages before first blocker execute; all live side effects absent |
| T2-03 | Correlation ID creation | canonical auto entry/admission context | no universal test; capital atomicity only proves `capitalCommitId` | Assert one generated ID per trade, stable across repeated helper calls and different components; no ID generated per leg or retry | Additive / Gate | T2-01 | One non-empty ID is present before decision/execution and remains unchanged |
| T2-04 | Correlation ID persistence | PnL SQLite, replay JSON, lifecycle DB, ledger/capital events, telemetry, operator summary | partial IDs in receipt/capital/replay tests | Seed one trade, query every durable surface, recreate services, compare exact ID; assert old records without ID remain readable | Additive / Gate | T2-03 | All surfaces share the same ID; legacy fields retain values |
| T2-05 | Correlation ID retry/idempotency | receipt retry and duplicate settlement | receipt retry handling and duplicate receipt tests | Process same tx/receipt through retry and duplicate paths; assert same ID and exactly one settlement | Additive / Gate | T2-03, T2-04 | No second ledger/capital mutation or new correlation ID |
| T2-06 | Direct execution bypass inventory | `try_execute_opportunity`, API trade/simulate, manual helpers, runtime compatibility seam | execution/API route tests; no complete caller inventory | Static list of every live-capable caller plus dynamic fake-send tests; assert required artifact absent/invalid blocks send | Additive / Gate | T2-03; source inventory | Zero live-capable caller submits without artifact; dry-run remains non-sending |
| T2-07 | Admission artifact completeness | `ExecutionService` canonical gates -> execution wrapper | current gate plan and execution plan are separate | Build artifact with correlation, IDs, ordered gate results, capture, capital, governance, terminal profitability, simulation, policy hash; reject missing/stale fields | Additive / Gate | T2-03, T2-06 | Valid artifact accepted; stale/mismatched artifact rejected before signing |
| T2-08 | Manual/API parity | API opportunity trade/simulate and operator/manual execution | mobile client exposes `/api/opportunities/trade` and `/simulate`; backend route tests exist | For every route, run a fake send with blocked fund/capture/governance and assert same admission result as auto; simulate may return plan but never send | Additive / Gate | T2-06, T2-07 | No manual/API path bypasses canonical safety; dry-run semantics explicit |
| T2-09 | Durable pending write | execution bookkeeping -> pending repository | current `_pending` map/queue only | Submit fixture, assert durable row contains tx/correlation/nonce/route/admission hash before worker polling | Additive / Gate | T2-03, T2-07 | Process can stop after write and recover all required context |
| T2-10 | Restart rehydration | runtime startup -> receipt worker | no existing restart test | Stop runtime after submit, recreate from same DB, rehydrate nonterminal rows, resume polling | Expected-fail until lifecycle fix | T2-09 | No pending trade is lost; no duplicate worker ownership |
| T2-11 | Lifecycle state machine | `tx_confirmation.assess_submitted_tx`, receipt facade | `test_pending_state_context_maintenance.py`, receipt tests | Fake RPC matrix: submitted, visible, pending, mined success, reverted, timeout, RPC error, dropped | Additive / Gate | T2-09 | Each input maps to one durable state and retry policy |
| T2-12 | Replacement/nonce lineage | submission and lifecycle manager | no replacement proof | Submit replacement with same nonce, record old/new hash, retain one correlation ID, settle only canonical winner | Expected-fail until lifecycle fix | T2-11 | Replacement is explicit, idempotent, and never double-settles |
| T2-13 | Confirmation depth/reorg | receipt finalization -> capital settlement | no confirmation-depth/reorg proof | Mine at depth 1, reorg it, require re-pending/rollback; settle only after configured depth | Expected-fail until lifecycle fix | T2-11, T2-12 | Reorg cannot leave false authoritative PnL/treasury state |
| T2-14 | Deterministic input capture | scanner/RPC/cache/decision/execution/replay | replay service/store tests only cover summary persistence | Capture ordered RPC request/results, block identity, config hash, token metadata, quote cache, seeds, calldata, nonce placeholder, receipt | Additive / Gate | T2-01, T2-03 | Envelope schema is versioned, redacts secrets, and contains all declared inputs |
| T2-15 | Offline replay equivalence | replay envelope -> verifier -> domain outputs | no byte-identical offline proof | Disable network; recreate services; run replay twice; compare canonical outputs and hashes | Expected-fail until replay fix | T2-14; T2-04 | Identical outputs, or explicit `incomplete`/`non_deterministic`, never false success |
| T2-16 | Replay failure classification | replay verifier | current store returns `None`/empty on some IO/invalid cases | Corrupt/missing/incomplete envelope; assert stable failure code and no settlement mutation | Additive / Gate | T2-14 | Invalid replay cannot be treated as authoritative evidence |
| T2-17 | Denomination correctness | pretrade safety -> receipt PnL | `test_safety.py`, flashloan sizing/lifecycle tests | WETH, USDC 6-decimal, 18-decimal token; assert gas conversion, provider fee, slippage and net profit share denomination | Additive / Gate | none, strengthens T2-01 | Mismatch/unavailable conversion fails closed; correct cases match math and receipt |
| T2-18 | Wealth-goal causality | wealth goal -> family budget/capital admission -> execution amount | wealth goal API/service and goal hardening tests | Same opp under two goal revisions; assert goal posture changes admission/sizing only within risk caps and is recorded in artifact/replay | Additive | T2-07, T2-14 | Causal change is observable; no hidden direct mutation |
| T2-19 | Atomic settlement idempotency | receipt service -> capital writer | `test_capital_write_service_atomicity.py`, receipt truth, flashloan lifecycle | Reapply same receipt after restart and after partial failure; assert one ledger/capital commit and one shared commit ID | Existing + extend / Gate | T2-04, T2-09 | Exactly one authoritative settlement; failure leaves auto-trading blocked and recoverable |
| T2-20 | Full operator authority | backend summary -> mobile command center | operator closed-loop and mobile projection tests | Backend fixture response with authoritative markers; assert no demo NAV/allocation/PnL in backend mode and explicit mock tag otherwise | Additive / Gate | T2-01, T2-04 | UI never presents demo financial state as backend-live truth |
| T2-21 | Final integrated proof | all five gaps | no current test | Extend T2-01 with correlation, restart, offline replay, bypass matrix, reorg/idempotency and mobile authority | Additive / Final Gate | T2-03, T2-07, T2-09, T2-14, T2-19, T2-20 | All A-E objectives pass repeatedly from clean checkout with no live capital |

## Dependency order

```text
T2-01 -> T2-03 -> T2-04 -> T2-05
                |       \
                |        -> T2-14 -> T2-15 -> T2-16
                -> T2-06 -> T2-07 -> T2-08
                -> T2-09 -> T2-10 -> T2-11 -> T2-12 -> T2-13
T2-17 and T2-18 strengthen the artifact and integrated proof
T2-19 and T2-20 -> T2-21
```

## Review gates and recommended commits

1. **Gate 0, tests only:** T2-01 and the expanded T2-02. No production code.
2. **Gate 1, additive lineage:** T2-03 through T2-05. Preserve old IDs and schemas.
3. **Gate 2, execution boundary:** T2-06 through T2-08. Live-capable calls fail closed without an artifact; dry-run remains safe.
4. **Gate 3, lifecycle:** T2-09 through T2-13 and T2-19. Rehydration and exactly-once settlement pass before any live consideration.
5. **Gate 4, replay:** T2-14 through T2-16. Offline replay is honest about incompleteness.
6. **Gate 5, causality/operator:** T2-17, T2-18, T2-20.
7. **Final Gate:** T2-21, then review before any implementation work beyond Phase 2.

## Compatibility checks on every phase

- Existing public routes, method names, response fields, and contract ABI remain unchanged.
- Existing rows/bundles without new fields remain readable.
- `try_execute_opportunity` remains available for dry-run and tests; live calls without a valid artifact fail closed only after the boundary is introduced.
- No private key, raw secret, or live RPC response containing credentials enters replay storage.
- Repeated receipt processing is exactly-once for capital state.
- Every new failure is explicit, observable, and safe by default.
