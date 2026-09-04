# WORKSPACE CHECKPOINT

## NEW WORKSPACE RECOVERY PROCEDURE

A new Codex instance must not assume conversational memory exists. The repository is the durable source of truth.

1. Read `docs/WORKSPACE_CHECKPOINT.md`.
2. Read `docs/SOVEREIGN_OS_CONTEXT.md`.
3. Read `docs/SOVEREIGN_OS_STATE.md`.
4. Read `docs/SOVEREIGN_OS_DECISIONS.md`.
5. Read `docs/AUTHORITY_DECISION_PACKET.md`.
6. Read `docs/ECONOMIC_IDENTITY_DESIGN.md` when the current task concerns lifecycle identity.
7. Read `docs/AUTHORITY_SOURCE_MAP.md` for the current read-side authority inventory.
8. Read `docs/AUTHORITY_TEST_EXECUTION.md` for the canonical focused test environment and command.
9. Read `docs/PHASE5A_ADAPTER_READINESS.md` for the current static caller/source/bypass inventory.
10. Inspect the current branch and HEAD.
11. Inspect the latest checkpoint commit.
12. Verify that repository state matches this checkpoint.

Never infer approval from chat, workspace memory, code existence, or a candidate design.

## CHECKPOINT ID

`CHECKPOINT-2026-09-04-PR70-CI-RECOVERY`

## DATE/TIME

2026-09-04, after PR #70 was synchronized onto current `main` and the OMAR canonical economic-learning work was prepared for the Linux CI gate. Exact commit timestamp is authoritative once this file is committed.

## PROJECT IDENTITY

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Current integration target: PR #70, `codex/omar-phase-final-main-sync`
- Default branch baseline: `main`
- Current task: clear the Linux CI `action_required` gate, require green CI, then perform Render staging/runtime verification and the production-method-chain regression.

## CURRENT ARCHITECTURE / GOAL

The approved learning lifecycle is:

`market data -> strategy/signals -> canonical decision -> decision_id/correlation_id -> OMAR observation/recommendation -> governance/risk -> capital authority -> execution -> execution_id -> authoritative settlement -> settled outcome -> exact action attribution -> OMAR policy update -> next decision`

OMAR is a learning subsystem, not execution authority. OMAR-disabled operation must still preserve canonical decision/execution/outcome identity and lineage.

## CURRENT AUTHORITY INVARIANTS

- `capital_engine_state()` is the actual read-side capital-authority input for OMAR learning context.
- Internal-prime authority is learned from authoritative capital state; it is not inferred as fake additive bankroll.
- Governance/risk remains authoritative.
- Signing and transaction execution remain authoritative and outside OMAR.
- Human/operator intent, aggressiveness, wealth-goal posture, and AI recommendation are decision-time attribution/context, not authority to bypass hard constraints.
- Latency, slippage, gas, realized/expected economics, and truth verification remain part of outcome/learning context.
- Exact action/route/transaction attribution must survive settlement.
- Learning is gated on canonical settled outcomes with complete identity lineage.

## CURRENT CI / STAGING GATE

PR #70 is open and mergeable. Its head is `14efb2fbfd7460c51455c5ff7129a8cf470e625d`.

The first Linux GitHub Actions run for that head (`CI` run `33907531193`) currently reports `action_required` and produced no jobs. The next recovery action is a human-authored repository commit so the corrected Linux CI workflow can execute normally; this checkpoint update is intentionally documentation-only and does not alter trading semantics.

Required gate sequence after CI starts:

1. Linux CI executes.
2. All required CI checks are green.
3. Render staging/runtime verification is performed without enabling live signing, capital approval, or broadcast.
4. The actual production-method-chain regression is run against the staging runtime.
5. Verify `decision -> correlation -> execution -> settled outcome -> OMAR learning` with exact identity continuity.
6. Verify `capital_engine_state()` is the actual capital-authority input.
7. Verify no OMAR path bypasses governance, capital authority, signing, or execution.
8. Only after those gates pass, begin merge/completion.

## SAFETY STATE

- No live trade is authorized by this checkpoint.
- No OMAR path may sign, approve capital, submit a transaction, or bypass governance.
- Render remains staging/observation only.
- Documentation does not constitute runtime authorization.

## RECOVERY NOTE

This checkpoint update is intentionally small and exists to provide durable recovery state and to move CI execution away from the prior `github-actions[bot]`-authored formatting commit that produced the `action_required` run. No production trading behavior is changed here.
