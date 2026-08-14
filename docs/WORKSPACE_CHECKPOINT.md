# WORKSPACE CHECKPOINT

## NEW WORKSPACE RECOVERY PROCEDURE

A new Codex instance must not assume conversational memory exists. The repository is the durable source of truth.

1. Read `docs/WORKSPACE_CHECKPOINT.md`.
2. Read `docs/SOVEREIGN_OS_CONTEXT.md`.
3. Read `docs/SOVEREIGN_OS_STATE.md`.
4. Read `docs/SOVEREIGN_OS_DECISIONS.md`.
5. Read `docs/SOVEREIGN_OS_CHANGELOG.md`.
6. Read `docs/AUTHORITY_DECISION_PACKET.md`.
7. Read `docs/ECONOMIC_IDENTITY_DESIGN.md` when the current task concerns lifecycle identity.
8. Read `docs/AUTHORITY_SOURCE_MAP.md` for the current read-side authority inventory.
9. Inspect the current branch and HEAD.
10. Inspect the latest checkpoint commit.
11. Verify that repository state matches this checkpoint.
12. Only then continue work.

Never infer approval from chat, workspace memory, code existence, or a candidate design.

## CHECKPOINT ID

`CHECKPOINT-2026-08-14-IMMUTABLE-AUTHORITY-CONTRACTS`

## DATE/TIME

2026-08-14, after the Phase 4 immutable read-only authority contract milestone. Exact commit timestamp is authoritative once this file is committed.

## PROJECT IDENTITY

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Branch: `architecture-c-contract-tests`
- HEAD BEFORE: `89803aee377bdaab942bcf903b4ad835cffde294`
- HEAD AFTER: populated by the commit that updates this checkpoint
- Previous checkpoint: `909db12de34d7dbc0db40f91ff649c35cbe8dd62`
- Default branch baseline: `main@52d9669bda8c44d3ed74ab3df8bb5f572ff72fb2`

This checkpoint reconstructs operational context from repository evidence, Git history, and checked-in documentation. It does not rely on conversational memory and does not authorize runtime or trading behavior.

## MILESTONE COMPLETED

Phase 4 immutable read-only authority contracts. Added `backend/victor_ai_bot/authority_contracts.py` with side-effect-free frozen evidence contracts, explicit authority classifications, snapshot states, source-specific revisions, provenance, explicit-now freshness evaluation, units/decimals, conflict representation, execution-plan identity, DecisionSnapshot validation, and a marker base for future read-only adapters. Added focused contract tests in `backend/tests/test_authority_contracts.py`.

The contracts intentionally preserve unresolved policy as `UNRESOLVED`, `POLICY_UNRESOLVED`, missing, or conflict states. No runtime consumer imports or uses them.

## CURRENT ARCHITECTURE PHASE

Phase 4 immutable read-only authority contracts, with Architecture C runtime composition still unwired.

## CURRENT PRODUCTION-READINESS CLASSIFICATION

`PARTIALLY_PROVEN` overall. The new contracts are production-shaped read-side types but do not prove production authority. CapitalDemand composition is `UNWIRED`; adapters, reservations, durable identity, pending recovery, settlement authority, deterministic replay, and live readiness remain unproven.

## PROVEN COMPONENTS

- Existing mocked quote/scanner, normalization, slippage, route/calldata, mocked gas, event decoding, canonical auto-admission, and atomic settlement component boundaries.
- Architecture C and synthetic authority snapshot semantics at contract/test level.
- Static source inventory and canonical authority decision packet.
- Phase 4 contract semantics are covered by focused tests in `backend/tests/test_authority_contracts.py`, but repository execution status is not yet established.

## PARTIALLY-PROVEN COMPONENTS

- RPC/market data, profitability, flash-loan sizing, capital/treasury admission, risk/governance coverage, receipt/PnL/ledger integration, Wealth Goals, replay persistence, telemetry/latency, operator/mobile projections, and Stage 1 characterization.

## UNPROVEN COMPONENTS

- Production authority acquisition and adapter correctness.
- Production `CapitalDemandComposer` and `DecisionSnapshot` assembly.
- Generic durable reservation and concurrency safety.
- Universal economic identity and child lineage.
- Restart, dropped-transaction, replacement, confirmation-depth, and reorg recovery.
- Authoritative receipt-derived settlement.
- Deterministic replay.
- One closed loop through reservation release and next allocation.
- Universal sealed admission for all live-capable callers.
- Live deployment or live-money behavior.

## CONFLICTING SOURCES OF TRUTH

- USD, wei, token-native units, bankroll values, and InternalPrime collateral.
- `deployable_bankroll_wei` and family allocations versus ledger-backed assets.
- Configured/provider fee assumptions versus callback fee evidence.
- Route ID versus final execution-plan identity.
- Caller-supplied settlement `realized_after` versus approved receipt-derived PnL policy.
- In-memory pending state versus durable capital/ledger state.
- JSON mirrors versus SQLite repositories and capital-event histories.
- `flash_arb` versus `flashloan_atomic` family naming.
- Surviving documentation checkpoint references versus current HEAD.

## APPROVED DECISIONS

Approved at policy or contract level, not necessarily runtime-wired:

- Architecture C is the approved capital-demand architecture, with runtime composition unwired.
- Borrowed principal is not internal treasury capital.
- The selector scalar, when eventually used, means strategy-budget consumption in an explicitly declared treasury denomination.
- Flash-loan arbitrage is the only initial live-eligible strategy at policy level, subject to full readiness evidence.
- Wealth Goals constrain pacing, allocation, sizing, and risk posture but never authorize a trade.
- AI recommendations cannot bypass governance/readiness.
- Missing, stale, contradictory, ambiguous, non-authoritative, or unreconciled critical state fails closed.
- Settlement policy requires authoritative receipt/event-derived PnL, but the invariant remains unwired.
- Durable correlation identity must remain distinct from tx hash, capital commit, execution plan, and replay identities.
- Documentation is durable memory, never runtime authorization.

Source: `docs/SOVEREIGN_OS_DECISIONS.md` and related contract tests. Phase 4 adds contracts only and no policy approvals.

## UNRESOLVED DECISIONS

1. Treasury denomination and reservation authority.
2. Conversion and decimal authority.
3. Provider capacity and fee authority.
4. Worst-case exposure/liability formula.
5. Strategy budget and concurrent reservation semantics.
6. Durable economic/trade correlation identity origin and persistence.
7. Opportunity freshness and empirical latency horizons.

Additional unresolved lifecycle questions remain: finality, replacement/cancellation, reorg handling, retention/privacy, and multi-fill semantics.

## CURRENT IMPLEMENTATION BLOCKERS

- No authoritative pre-decision CapitalDemand composer.
- Legacy scalar capital inference remains in the decision path.
- Read-only adapters are not implemented.
- No generic durable reservation protocol.
- No universal lifecycle identity across opportunity, decision, reservation, attempts, receipt, ledger, replay, and capital events.
- Pending state is primarily in memory.
- Replacement, nonce ownership, dropped transaction, finality, and reorg semantics are absent from proof.
- Settlement accepts caller-supplied realized values at the service seam.
- Replay is forensic, not deterministic.
- Freshness is instrumented but not decision-authoritative.
- Manual/API/direct execution bypass equivalence is unproven.
- Focused Phase 4 tests have been added but not executed in this environment.

## CURRENT SAFETY STATE

- Runtime behavior unchanged by this checkpoint.
- `dry_run: true` and `auto_trading: false` remain the checked-in repository defaults.
- Live trading: **DISABLED at repository level**; deployed overrides remain configuration-dependent.
- No strategy activation.
- No Solidity/ABI changes.
- No settlement/PnL semantic changes.
- No DecisionEngine integration.
- No CapitalDemandComposer wiring.
- No reservation writes.
- No production persistence or database changes.

## FILES CHANGED IN LATEST MILESTONE

- `backend/victor_ai_bot/authority_contracts.py`
- `backend/tests/test_authority_contracts.py`
- `docs/WORKSPACE_CHECKPOINT.md`

No runtime consumer, configuration, Solidity, ABI, settlement, PnL, or persistence files were changed.

## TESTS RUN AND RESULTS

- Tests created: `backend/tests/test_authority_contracts.py`.
- Tests run for this milestone: none; remote repository execution was not available in this session.
- Test result: **NOT EXECUTED**, not a pass claim.
- Static safety review: the contract module contains no RPC, database, filesystem, environment, signing, submission, reservation, allocation, settlement, or PnL calls; this is source inspection, not executable proof.

## LAST KNOWN RUNTIME BEHAVIOR

The canonical auto path can perform ordered hold, family, route/capture, flash-loan, treasury, and governance checks before lower-level execution. Discovery, execution, receipt, settlement, replay, and operator surfaces exist in components. Pending and receipt context remain primarily in memory, settlement accounting is partially connected, and live execution is not proven or enabled by checked-in defaults.

## CURRENT TASK

Preserve and review immutable read-only authority contracts without wiring them into runtime or silently resolving policy.

## NEXT TASK

Execute the focused Phase 4 contract test file in an appropriately configured checkout, then owner-review any failures. After that, implement read-only authority adapters only after explicit policy boundaries remain intact.

## TASKS EXPLICITLY FORBIDDEN

Until separately authorized and all required evidence exists:

- Do not implement or wire `CapitalDemandComposer`.
- Do not modify `DecisionEngine` integration.
- Do not create generic reservation writes or production identity persistence.
- Do not change settlement/PnL semantics.
- Do not modify Stage 1 characterization behavior.
- Do not modify Solidity or ABI behavior.
- Do not enable live signing, submission, or trading.
- Do not change production configuration, `dry_run`, or `auto_trading` defaults.
- Do not activate strategies or invent treasury, conversion, provider, exposure, budget, identity, or freshness policy.
- Do not treat heuristics, telemetry, goals, AI recommendations, or configuration as authority.
- Do not claim tests, replay, recovery, or a closed money loop are proven without executed evidence.

## RELEVANT ARCHITECTURAL DOCUMENTS

- `docs/SOVEREIGN_OS_CONTEXT.md`
- `docs/SOVEREIGN_OS_STATE.md`
- `docs/SOVEREIGN_OS_DECISIONS.md`
- `docs/SOVEREIGN_OS_CHANGELOG.md`
- `docs/CURRENT_GOLDEN_PATH.md`
- `docs/GOLDEN_PATH_GAPS.md`
- `docs/GOLDEN_PATH_TEST_PLAN.md`
- `docs/PHASE_2_ARCHITECTURE_PLAN.md`
- `docs/AUTHORITY_DECISION_PACKET.md`
- `docs/ECONOMIC_IDENTITY_DESIGN.md`
- `docs/AUTHORITY_SOURCE_MAP.md`

## RELEVANT TESTS AND SOURCE

- `backend/tests/test_authority_contracts.py`
- `backend/tests/test_authority_snapshot_contracts.py`
- `backend/tests/test_capital_demand_contract.py`
- `backend/tests/test_capital_demand_policy_constraints.py`
- `backend/tests/test_capital_demand_predecision_composition.py`
- `backend/tests/test_capital_demand_projection.py`
- `backend/tests/test_settlement_authoritative_pnl_contract.py`
- `backend/tests/test_current_golden_path_closed_loop.py`
- `backend/victor_ai_bot/authority_contracts.py`
- `backend/victor_ai_bot/capital_demand.py`
- `backend/victor_ai_bot/decision_engine.py`
- `backend/victor_ai_bot/runtime.py`
- `backend/victor_ai_bot/runtime_core/coordinator.py`
- `backend/victor_ai_bot/runtime_services/runtime_decision_facade.py`
- `backend/victor_ai_bot/runtime_services/runtime_execute_dispatch_facade.py`
- `backend/victor_ai_bot/runtime_services/runtime_receipt_facade.py`
- `backend/victor_ai_bot/runtime_services/capital_truth_service.py`
- `backend/victor_ai_bot/runtime_services/receipt_service.py`
- `backend/victor_ai_bot/treasury/ledger.py`
- `backend/victor_ai_bot/persistence/repositories/ledger_repository.py`
- `backend/victor_ai_bot/pnl.py`
- `backend/victor_ai_bot/runtime_subsystems/replay_store.py`
- `backend/victor_ai_bot/latency_profiler.py`

## EXACT RESUME INSTRUCTIONS FOR A NEW CODEX WORKSPACE

1. Read this file first.
2. Read the four Sovereign OS documents listed above.
3. Read `docs/AUTHORITY_DECISION_PACKET.md`.
4. Read `docs/ECONOMIC_IDENTITY_DESIGN.md` for identity architecture context.
5. Read `docs/AUTHORITY_SOURCE_MAP.md` for the read-only source inventory.
6. Read `backend/victor_ai_bot/authority_contracts.py` and `backend/tests/test_authority_contracts.py`.
7. Inspect `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, and `git log --oneline --decorate -n 20`.
8. Verify HEAD contains this checkpoint commit and that no unexpected files changed.
9. Confirm the seven unresolved decisions have not been silently upgraded.
10. Re-check `dry_run`, `auto_trading`, live-strategy eligibility, and protected boundaries.
11. Execute the focused contract tests in an appropriately configured checkout; record the actual result.
12. Do not implement runtime behavior until owner approval and the next authorized milestone are explicit.
13. If beginning the next milestone, update this checkpoint when the milestone is complete and commit it with a descriptive message.

## CHECKPOINT PROTOCOL

Every meaningful milestone must update this document or a clearly linked successor. Each checkpoint records:

- checkpoint ID;
- date/time;
- branch;
- HEAD before and after;
- milestone completed;
- files changed;
- tests and actual results;
- decisions and discoveries;
- risks and blockers;
- safety state;
- next task;
- forbidden work;
- exact resume instructions.

Checkpoint commits should be small, understandable, documentation-focused, and created at meaningful milestones. Never create a checkpoint commit to smuggle runtime behavior, financial policy, strategy activation, or live trading changes.

## CHECKPOINT REPORT TEMPLATE

Every substantial task response must end with:

```text
STATUS:
MILESTONE:
BRANCH:
HEAD:
FILES CHANGED:
TESTS RUN:
TEST RESULTS:
DECISIONS MADE:
DECISIONS STILL UNRESOLVED:
RUNTIME BEHAVIOR CHANGED:
LIVE TRADING STATUS:
CHECKPOINT UPDATED:
CHECKPOINT COMMIT:
NEXT TASK:
BLOCKED TASKS:
```
