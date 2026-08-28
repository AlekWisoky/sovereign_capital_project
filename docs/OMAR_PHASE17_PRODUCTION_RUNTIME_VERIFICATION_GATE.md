# OMAR Phase 17 — Production Runtime Verification Gate

## Baseline

The engineering baseline is `omar/phase-16-canonical-learning-identity`, not the earlier Phase 6 runtime-chain branch.

Phase 16 is the canonical learning-identity lineage. Its head adds the explicit contract:

`canonical decision ID -> correlation ID -> execution ID -> canonical settled outcome ID -> exact action -> policy update`

## Audited production path

The runtime path is:

1. `RuntimeBundle.__init__` initializes the runtime constructor core, execution-capture/support stacks, institutional stack, overlays, and optional families.
2. `RuntimeBundle._loop` delegates to `RuntimeLoopEntryFacade._run_loop_entry_iteration`.
3. The loop selects the read RPC and calls `_prepare_tick_iteration`.
4. `_run_contained_tick_iteration` invokes `_run_tick_scan_pipeline` and preserves fail-closed per-tick containment.
5. `_run_tick_scan_pipeline` scans opportunities, annotates execution readiness, gathers gas/market/regime/treasury context, builds predecision state, and calls `_run_decision_finalize`.
6. `_run_decision_finalize` calls `_safe_decide_opportunities`, applies treasury overlays, refreshes the auto queue, and runs postdecision state/analytics.
7. `_run_after_tick_orchestration` invokes `_maybe_dispatch_auto_trade`.
8. `_maybe_dispatch_auto_trade` selects only an execution-ready candidate, then applies OMAR through `_apply_omar_to_candidate`. The production lineage bridge ensures canonical decision/correlation identity here even when OMAR is disabled.
9. `_execute_auto` delegates through `RuntimeExecuteDispatchFacade` and `RuntimeExecuteWrapperFacade` to the real `try_execute_opportunity` boundary.
10. `ExecutionService.handle_post_execute_bookkeeping` records the execution and submission bookkeeping and is also the production seam that resolves the canonical settled outcome.
11. The Phase 2 canonical settlement interface reads only `receipt_settlement` ledger transactions and supplies the settled outcome to the lifecycle bridge.
12. The lifecycle bridge passes the settled economics and lineage into `OmarRuntime.observe_outcome`.
13. `OmarRealLearner.observe` refuses a transition without a canonical decision ID and persists the decision/correlation lineage with the learning event.
14. Live OMAR recommendation requires both the learning-quality gate and the independent OOS performance-promotion gate before learned influence is allowed.

## Verification gate

`backend/tests/test_omar_phase17_production_runtime_gate.py` verifies:

- the production runtime surface exposes the constructor/tick/decision/execution chain;
- the canonical settlement, lineage, lifecycle, and durable-learning hooks are installed;
- the actual runtime loop-entry facade delegates into the contained tick pipeline;
- the real `ExecutionService.handle_post_execute_bookkeeping` boundary can carry a canonical settled outcome into OMAR learning;
- decision ID, correlation ID, action, and settled outcome remain attributable;
- latency remains part of the settled reward path rather than becoming an execution authority;
- one successful outcome is insufficient to unlock live influence, preserving the independent learning-quality/performance gates.

## Safety boundary

This gate does not enable live trading, bypass governance, grant OMAR capital authority, or substitute a receipt/PnL cache for the canonical settlement ledger. It is an offline production-path verification gate using patched external I/O and deterministic test seams.
