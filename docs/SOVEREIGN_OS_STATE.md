# Sovereign Capital OS Current State

Last reviewed: 2026-08-13. Repository: https://github.com/AlekWisoky/sovereign_capital_project

## Git and phase
- CURRENT_PHASE: Architecture C contract checkpoint; runtime composition not started
- CURRENT_BRANCH: `architecture-c-contract-tests`
- CURRENT_COMMIT: `314382c8ef545322416d7d809c887f29d1afbfb0`
- CURRENT_BASELINE: `main@52d9669`; audit `e7c9ba2`; Phase 2 plan `fe1550c`; corrected Stage 1 `24aea2b`
- LIVE_TRADING: DISABLED
- TEST EXECUTION STATUS: NOT EXECUTED during this read-only rehydration; branch-green status UNKNOWN

## Proof matrix
### PROVEN
Focused repository evidence exists for quote/scanner components, normalization, slippage, route/calldata components, mocked gas, event decoding, canonical auto-admission ordering, atomic settlement component writes, and Architecture C contract semantics including typed money, distinct exposure dimensions, freshness, capacity, conversion, provenance, conflict detection, selector projection, plan matching, Phase A eligibility, and settlement-authority invariants. This does not prove live deployment.

### PARTIALLY PROVEN
Profitability and terminal execution checks; flashloan sizing; capital and treasury admission; family readiness; Wealth Goal surfaces; receipt/PnL/ledger/bankroll/treasury integration; replay persistence; learning; operator/mobile projections; latency spans, quote batching, execution spans, rolling p50/p90/p99, and receipt timing; Stage 1 characterization.

### PRODUCTION GAP
No authoritative pre-decision CapitalDemand composer; legacy scalar inference remains in portfolio construction; production treasury denomination/conversion authority, provider-capacity and exposure composition, durable reservation protocol, universal correlation, final-plan recomputation, mandatory goal linkage, and next-allocation proof are missing.

### NOT PROVEN
One real closed capital loop; authoritative PnL-driven settlement; durable pending lifecycle; restart recovery; nonce/replacement lineage; confirmation depth/reorg handling; deterministic replay; latency-aware admission/profitability; sealed admission for every live-capable caller; authoritative operator reconstruction; live end-to-end trading.

### UNKNOWN
Actual test-suite result for this checkpoint, live provider/RPC behavior, production deployment readiness, empirical latency budgets, and whether every manual/API path is covered by equivalent admission controls.

### BLOCKED
Any runtime Architecture C wiring, live trading, additional strategy-family eligibility, Stage 1 repair, or production settlement-authority change is blocked until the relevant evidence and separate authorization exist.

## Current blockers
1. Pre-decision CapitalDemand production composition is absent.
2. Legacy `capital_required_wei` inference is ambiguous and must not be revived.
3. Production denomination, conversion, capacity, exposure, and budget authorities are not assigned.
4. Settlement accepts caller-supplied `realized_after`; authority invariant is unwired.
5. Pending transaction state is in memory.
6. Live execution admission is bypassable below the canonical auto path.
7. `flash_arb` versus `flashloan_atomic` family identity needs authoritative reconciliation.
8. Replay is forensic, not deterministic.
9. Latency is instrumented but not decision-authoritative.
10. Operator authority and demo-state exclusion are not proven end to end.

## Subsystem status
- ARCHITECTURE_C_STATUS: **CONTRACT READY FOR RUNTIME COMPOSITION; RUNTIME UNWIRED**
- CAPITAL_DEMAND_STATUS: **CONTRACT READY / PRODUCTION COMPOSITION NOT PROVEN**
- LATENCY_STATUS: **INSTRUMENTED BUT NOT DECISION-AUTHORITATIVE**
- WEALTH_GOAL_STATUS: **PARTIALLY PROVEN**
- ROLLOUT_STATUS: **PHASE A CONTRACT POLICY ONLY**
- LEDGER_STATUS: **PARTIALLY PROVEN**
- PNL_STATUS: **PARTIALLY PROVEN; denomination and uniqueness gaps remain**
- SETTLEMENT_STATUS: **NOT PROVEN AS AUTHORITATIVE**
- REPLAY_STATUS: **NOT PROVEN DETERMINISTIC**
- RECOVERY_STATUS: **NOT PROVEN**
- OPERATOR_STATUS: **NOT PROVEN AUTHORITATIVE**

## Strategy status
- LIVE_STRATEGIES: **NONE**
- STAGED_STRATEGIES: Flash-loan arbitrage components and contract policy
- SHADOW_STRATEGIES: Families permitted only for observation, research, backtest, simulation, or explicit shadow configuration
- DISABLED_STRATEGIES: Every family lacking explicit readiness and governance; all non-flash families for Phase A live eligibility

## Active work and resume point
- LAST_COMPLETED: Architecture C contract tests, latest `314382c`
- AUTHORIZED_NEXT_STEP: Tests-only expected-fail characterization at the real pre-decision boundary. A scanner-produced Phase A opportunity must require fresh authoritative CapitalDemand before portfolio selection; selector uses only strategy-budget consumption in explicit treasury denomination; missing/stale/conflicting/unconvertible/capacity-invalid/provenance-invalid/plan-mismatched demand yields no trade; no signing/submission; no fake legacy metadata.
- EXACT_RESUME_ACTION: inspect current branch, read the four Sovereign OS documents, then add only the focused characterization test after separate authorization.
- VERIFICATION COMMANDS: `git status --short`; `git log --oneline --decorate -n 20`; `pytest -q backend/tests/test_capital_demand_*.py backend/tests/test_settlement_authoritative_pnl_contract.py` (run only in an appropriately configured environment; record actual result)

## Forbidden next steps
No production edits, runtime wiring, Stage 1 repair, live-trading enablement, extra live strategy, safety-gate weakening, invented economics/provenance/denomination, ambiguous capital scalar restoration, caller-controlled settlement PnL, branch merge, PR, or unrecorded architectural change.

## Durable checkpoints
- CHECKPOINT-ARCHITECTURE: `fe1550c`, phase-2 plan, documented design; gaps remain; preserve as history.
- CHECKPOINT-CONTRACT: `314382c`, architecture-c contract branch, contract ready/unwired; next safe action is tests-only composition characterization.
- CHECKPOINT-COMPOSITION: NOT ESTABLISHED; blocked by missing production composer.
- CHECKPOINT-EXECUTION: PARTIALLY PROVEN; canonical admission and execution components exist, sealed boundary/lifecycle absent.
- CHECKPOINT-SETTLEMENT: BLOCKED; authority invariant unwired.
- CHECKPOINT-LEDGER: PARTIALLY PROVEN at component level; lifecycle/correlation/reorg gaps remain.
- CHECKPOINT-REPLAY: NOT PROVEN deterministic; forensic bundles only.
- CHECKPOINT-RECOVERY: NOT PROVEN; pending map/queue are in memory.
- CHECKPOINT-ROLLOUT: contract-only Phase A policy; keep live trading disabled.
