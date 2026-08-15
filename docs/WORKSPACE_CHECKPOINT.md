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
9. Read `docs/AUTHORITY_TEST_EXECUTION.md` for the canonical focused test environment and command.
10. Read `docs/PHASE5A_ADAPTER_READINESS.md` for the current static caller/source/bypass inventory.
11. Inspect the current branch and HEAD.
12. Inspect the latest checkpoint commit.
13. Verify that repository state matches this checkpoint.

Never infer approval from chat, workspace memory, code existence, or a candidate design.

## CHECKPOINT ID

`CHECKPOINT-2026-08-14-PHASE5A-ADAPTER-READINESS`

## DATE/TIME

2026-08-14, after Phase 5A static adapter-readiness and caller/bypass inventory. Exact commit timestamp is authoritative once this file is committed.

## PROJECT IDENTITY

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Branch: `architecture-c-contract-tests`
- HEAD BEFORE: `d17df2d572b2d5c88dd9bb369b5f7390a56fe165`
- HEAD AFTER: populated by the commit that updates this checkpoint
- Previous checkpoint: `636b6a58f91b1fffd20edf927e4c45d54a33a55c`
- Default branch baseline: `main@52d9669bda8c44d3ed74ab3df8bb5f572ff72fb2`

This checkpoint reconstructs operational context from repository evidence, Git history, and checked-in documentation. It does not rely on conversational memory and does not authorize runtime or trading behavior.

## MILESTONE COMPLETED

Phase 5A static adapter-readiness, CapitalDemand readiness, execution bypass, identity, pending/recovery, and replay inventory. Detailed findings are in `docs/PHASE5A_ADAPTER_READINESS.md`.

## CURRENT ARCHITECTURE PHASE

Phase 5A static architecture preparation. Authority tests remain unexecuted; adapter implementation is blocked.

## CURRENT PRODUCTION-READINESS CLASSIFICATION

`PARTIALLY_PROVEN` overall. The inventory is documentation evidence only. Authority tests are not proven until executed in a real repository environment. CapitalDemand composition, adapters, reservations, durable identity, pending recovery, authoritative settlement, deterministic replay, and live readiness remain unproven.

## PROVEN COMPONENTS

- Existing mocked quote/scanner, normalization, slippage, route/calldata, mocked gas, event decoding, canonical auto-admission, and atomic settlement component boundaries.
- Architecture C and prior synthetic authority snapshot semantics at contract/test level.
- Static authority source inventory, canonical authority packet, and Phase 5A readiness inventory.
- Repository-native CI dependency and focused test command definition.

## PARTIALLY-PROVEN COMPONENTS

- RPC/market data, profitability, flash-loan sizing, capital/treasury admission, risk/governance coverage, receipt/PnL/ledger integration, Wealth Goals, replay persistence, telemetry/latency, operator/mobile projections, Stage 1 characterization, and Phase 4 contract semantics pending execution.

## UNPROVEN COMPONENTS

- Executed authority contract tests.
- Executed existing synthetic authority snapshot tests.
- Production authority acquisition/adapters.
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

Source: `docs/SOVEREIGN_OS_DECISIONS.md` and related contract tests. Phase 5A adds no policy approvals.

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

- Authority tests are not proven until executed in a real repository environment.
- No writable checkout or pytest runner was available in the validation sandbox.
- No approved production snapshot adapters.
- No authoritative pre-decision CapitalDemand composer.
- Legacy scalar capital inference remains in the decision path.
- No generic durable reservation protocol.
- No universal lifecycle identity across opportunity, decision, reservation, attempts, receipt, ledger, replay, and capital events.
- Pending state is primarily in memory.
- Replacement, nonce ownership, dropped transaction, finality, and reorg semantics are absent from proof.
- Settlement accepts caller-supplied realized values at the service seam.
- Replay is forensic, not deterministic.
- Freshness is instrumented but not decision-authoritative.
- Manual/API/direct execution bypass equivalence is unproven.

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

- `docs/PHASE5A_ADAPTER_READINESS.md`
- `docs/WORKSPACE_CHECKPOINT.md`

No runtime files, tests, dependencies, configuration, persistence, or contract code were changed.

## TESTS RUN AND RESULTS

- `backend/tests/test_authority_contracts.py`: **NOT EXECUTED**.
- `backend/tests/test_authority_snapshot_contracts.py`: **NOT EXECUTED**.
- Architecture C subset: **NOT EXECUTED**.
- Reason: connected interface cannot execute/observe GitHub Actions; local sandbox has no writable checkout and no pytest.
- No test counts, pass/fail results, or runtime are claimed.

## STATIC ARCHITECTURAL FINDINGS

- DecisionEngine consumes mutable runtime/config/RL/command-center inputs and legacy capital scalars, not DecisionSnapshot or CapitalDemand.
- Canonical auto admission is ordered and tested as a component but lower-level/manual/API/legacy paths are not proven to share one sealed artifact.
- Pending map and receipt queue are in memory; nonce/replacement/finality/reorg/restart recovery are not durable.
- Replay bundles are persistent forensic summaries but omit exact RPC/state/cache/nonce/clock/policy evidence needed for deterministic replay.
- Proposed adapter interfaces are documented only; none are implemented.

## SEMANTIC/POLICY SAFETY

No unresolved treasury, conversion, provider, exposure, reservation, identity, freshness, finality, replacement, reorg, retention/privacy, or multi-fill policy was selected. All adapter interfaces are design-only.

## CI/RECOVERY STATUS

`.github/workflows/ci.yml` remains the repository-native CI path using Python 3.11 and pinned backend dependencies. `docs/AUTHORITY_TEST_EXECUTION.md` remains the canonical focused test command. Authority tests are not proven until executed in a real repository environment. Repository Git history and CI results are the authoritative recovery mechanism.

## NEXT TASK

Establish a real executable repository environment and execute the focused authority suites. Do not implement adapters until those results exist and any failures are classified.

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
- `docs/AUTHORITY_TEST_EXECUTION.md`
- `docs/PHASE5A_ADAPTER_READINESS.md`

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
6. Read `docs/AUTHORITY_TEST_EXECUTION.md` for dependency installation and the canonical command.
7. Read `docs/PHASE5A_ADAPTER_READINESS.md` for static source/caller/bypass findings.
8. Read `backend/victor_ai_bot/authority_contracts.py` and `backend/tests/test_authority_contracts.py`.
9. Inspect `git status --short`, `git branch --show-current`, `git rev-parse HEAD`, and `git log --oneline --decorate -n 20`.
10. Verify HEAD contains this checkpoint commit and that no unexpected files changed.
11. Confirm the seven unresolved decisions have not been silently upgraded.
12. Re-check `dry_run`, `auto_trading`, live-strategy eligibility, and protected boundaries.
13. Establish a writable checkout using the existing CI dependency mechanism: Python 3.11, `backend/requirements-dev.txt`, constrained by `backend/constraints.txt`.
14. Execute `PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py` and record exact counts/duration.
15. Classify failures before changing code. Do not weaken tests or resolve policy to make them pass.
16. Do not implement adapters until focused tests execute and semantic defects are resolved.
17. If beginning the next milestone, update this checkpoint when the milestone is complete and commit it with a descriptive message.

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
