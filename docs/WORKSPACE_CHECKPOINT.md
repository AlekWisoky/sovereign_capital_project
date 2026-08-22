# WORKSPACE CHECKPOINT

## NEW WORKSPACE RECOVERY PROCEDURE

Repository Git history and CI results are the authoritative recovery mechanism. A new Codex instance must not assume conversational memory exists.

1. Read `docs/WORKSPACE_CHECKPOINT.md`.
2. Read `docs/SOVEREIGN_OS_CONTEXT.md`, `docs/SOVEREIGN_OS_STATE.md`, `docs/SOVEREIGN_OS_DECISIONS.md`, and `docs/SOVEREIGN_OS_CHANGELOG.md`.
3. Read `docs/AUTHORITY_DECISION_PACKET.md`, `docs/AUTHORITY_SOURCE_MAP.md`, `docs/ECONOMIC_IDENTITY_DESIGN.md`, `docs/AUTHORITY_TEST_EXECUTION.md`, and `docs/PHASE5A_ADAPTER_READINESS.md`.
4. Inspect the current branch, HEAD, latest checkpoint commit, and working tree.
5. Verify repository state matches this checkpoint before continuing.

## PROJECT / GIT STATE

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Branch: `architecture-c-contract-tests`
- Source HEAD inspected: `bbb89205059818862ddd3c904201d7ebc0803055`
- Source commit: `test: align authority snapshot contract expectations`
- Parent: `2d812bdd458814362d5c649673bc73a5b90f2862`
- Checkpoint commit: the commit containing this file update
- Runtime behavior changed by this checkpoint: **NO**
- Checked-in live trading status: **DISABLED** (`dry_run: true`, `auto_trading: false`)

## CURRENT PHASE / LATEST MILESTONE

Recovery synchronization, authority test repair verification, and Render staging diagnostics. The `bbb8920` repair is present and must not be duplicated:

- empty provider `capacity_units` is classified as `MISSING_AUTHORITY`;
- prohibited runtime identifiers in the source-inspection test are assembled indirectly to avoid self-reference.

## TEST EVIDENCE

### Last actually executed focused run

Reported from a real clean checkout at parent commit `2d812bdd458814362d5c649673bc73a5b90f2862`:

```bash
PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py
```

- Python: `3.13.3`
- pytest: `9.1.1`
- Total: `21`
- Passed: `19`
- Failed: `2`
- Skipped: `0` reported
- Errors: `0`
- Failures: provider missing-capacity-unit classification and self-referential source inspection.

### Current source HEAD result

The two repairs are committed at `bbb89205059818862ddd3c904201d7ebc0803055`, but the focused suites have **NOT BEEN EXECUTED at this exact HEAD by this workspace**. No green result is claimed. The canonical command remains the command above. Next validation must run it at the current branch tip in a real checkout and record exact duration/counts.

## RENDER STAGING DIAGNOSTICS

- Workspace: `My Workspace`
- Service: `sovereign_capital_project`
- Service type: Docker web service
- Region/plan: Virginia / free
- Repository: `https://github.com/AlekWisoky/sovereign_capital_project`
- Branch: `architecture-c-contract-tests`
- Auto-deploy: enabled on commit
- URL: `https://sovereign-capital-project.onrender.com`
- Service status: not suspended, but latest deployment failed
- Deployment ID: `dep-da4k8ajtqb8s73859i4g`
- Deployment commit: `bbb89205059818862ddd3c904201d7ebc0803055`
- Deployment status: `update_failed`
- Started: `2026-08-22T06:39:38Z`
- Finished: `2026-08-22T06:40:27Z`
- Build: Docker image build and production dependency installation completed far enough to start Uvicorn
- Runtime: failed during application import
- Deployed commit matched inspected GitHub HEAD `bbb8920`: **YES**, but no healthy deployment was produced

### Render blocker: numpy

`Dockerfile` uses `python:3.11-slim` and installs only `backend/requirements.txt`. That production file does not declare `numpy`. Importing `victor_ai_bot.server` reaches `runtime.py`, which imports `omar.runtime`; `backend/victor_ai_bot/omar/runtime.py` imports `numpy as np` unconditionally even though `OmarConfig.enabled` defaults to false. Render therefore exits with:

```text
ModuleNotFoundError: No module named 'numpy'
```

Diagnosis: numpy is an import-time runtime dependency of the current server import graph but is absent from the canonical production dependency set installed by Docker. This is a real deployment dependency gap, not an authority-policy decision. No dependency repair was made in this milestone because the required repository test/build validation was not available through this workspace. Do not deploy a dependency change without running the canonical focused tests and at least a server import/start smoke test in a real checkout.

## VERIFIED FACTS / ARCHITECTURAL STATUS

- Authority contracts and regression tests exist.
- The `bbb8920` test-only fix is present.
- No adapters are implemented.
- `CapitalDemandComposer` is not wired.
- DecisionEngine still uses the legacy capital path.
- Generic reservation, durable pending recovery, replacement/reorg handling, authoritative settlement, and deterministic replay remain unproven.
- Render is an observation layer, not a substitute for repository tests.

## UNRESOLVED DECISIONS

1. Treasury denomination and reservation authority.
2. Conversion and decimal authority.
3. Provider capacity and fee authority.
4. Worst-case exposure/liability formula.
5. Strategy budget and concurrent reservation semantics.
6. Durable economic/trade correlation identity origin and persistence.
7. Opportunity freshness and empirical latency horizons.

Additional unresolved lifecycle policies: finality, replacement/cancellation, reorg handling, retention/privacy, and multi-fill semantics.

## FILES CHANGED / COMMITS

- This milestone changes only `docs/WORKSPACE_CHECKPOINT.md`.
- No runtime, dependency, configuration, test, settlement, PnL, execution, reservation, or Solidity files changed.
- Commit created: the documentation checkpoint commit containing this update.

## BLOCKED OPERATIONS

Until explicit approval and executable evidence exist:

- no authority adapters;
- no CapitalDemandComposer implementation or wiring;
- no DecisionEngine integration;
- no reservation writes;
- no settlement/PnL semantic changes;
- no execution or Solidity/ABI changes;
- no production/live-trading configuration changes;
- no live signing/submission or strategy activation;
- no silent resolution of financial/risk policy.

## EXACT NEXT TASK

1. In a real clean checkout at the current branch tip, install the repository-pinned test environment.
2. Run the canonical focused authority command and record exact counts/duration.
3. If green, run the narrow Architecture C contract subset already present.
4. Separately prepare the smallest production dependency repair for numpy, then validate with focused tests plus a server import/start smoke test before allowing Render to redeploy.
5. Update this checkpoint with actual evidence and exact commit/deployment SHAs.

## IMPORTANT DURABLE DOCUMENTS

- `docs/AUTHORITY_DECISION_PACKET.md`
- `docs/AUTHORITY_SOURCE_MAP.md`
- `docs/ECONOMIC_IDENTITY_DESIGN.md`
- `docs/AUTHORITY_TEST_EXECUTION.md`
- `docs/PHASE5A_ADAPTER_READINESS.md`
- `backend/victor_ai_bot/authority_contracts.py`
- `backend/tests/test_authority_contracts.py`
- `backend/tests/test_authority_snapshot_contracts.py`
