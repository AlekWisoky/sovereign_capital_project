# WORKSPACE CHECKPOINT

## NEW WORKSPACE RECOVERY PROCEDURE

Repository history and recorded execution evidence are the authoritative recovery mechanism. Do not infer tests or deployment success from source state alone.

1. Read this checkpoint and the linked durable architecture documents.
2. Inspect branch, HEAD, and working tree before changing anything.
3. Verify repository state against this checkpoint.
4. Preserve live-trading safeguards and do not weaken authority contracts.

## PROJECT / GIT STATE

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Primary branch: `architecture-c-contract-tests`
- Starting remote HEAD for this repair: `b5d5d5a861a9da7baf37af4cb9a4180bcc8eee7a`
- Previous functional commit: `bbb89205059818862ddd3c904201d7ebc0803055`
- Validation branch: `codex/numpy-production-dependency-repair`
- Repair commit: the commit containing this checkpoint and dependency update
- Files changed: `backend/requirements.txt`, `docs/WORKSPACE_CHECKPOINT.md`
- Runtime Python source changed: **NO**
- Authority or safety behavior changed: **NO**
- Checked-in live trading status: **DISABLED** (`dry_run: true`, `auto_trading: false`)

## CURRENT MILESTONE

A minimal production dependency repair has been prepared on an isolated validation branch so the Render service, which auto-deploys the primary branch, is not touched before CI validation.

Exact dependency change:

```text
backend/requirements.txt
+numpy==2.1.3
```

No runtime Python, Docker, workflow, authority-contract, test, trading, credential, or Render setting was changed.

## WHY THIS REPAIR EXISTS

Render deployment `dep-da4k8ajtqb8s73859i4g` at commit `bbb89205059818862ddd3c904201d7ebc0803055` reached application startup and failed during import with:

```text
ModuleNotFoundError: No module named 'numpy'
```

Observed import path:

```text
victor_ai_bot.server
-> api_routes
-> api
-> api_legacy
-> runtime
-> omar.runtime
-> import numpy as np
```

The root `Dockerfile` uses `python:3.11-slim` and installs `backend/requirements.txt`. NumPy is imported directly by the current production server graph, so it is a production dependency rather than a development-only package.

## EXISTING PYTHON 3.11 / LINUX VALIDATION PATH

`.github/workflows/ci.yml` runs on `ubuntu-latest`, installs Python `3.11`, installs `backend/requirements-dev.txt` under `backend/constraints.txt`, then runs Ruff, Black, Mypy, and the full backend pytest suite. The dev requirements include `-r requirements.txt`, so the repair pin is installed by the existing CI path.

Additional existing repository validation paths:

- root `Dockerfile`: `python:3.11-slim`, production requirements, server start script;
- `backend/Dockerfile`: `python:3.11-slim`, production requirements, server start script;
- `make verify-backend` -> `scripts/verify_boot.sh`;
- `scripts/verify_boot.sh`: server import, generated-file checks, full backend pytest, RPC sanity;
- focused authority command recorded below.

No tox, nox, or new CI system was introduced.

## TEST EVIDENCE

### Verified pre-repair authority evidence from the recovered Termux checkout

The user actually executed this command at `bbb89205059818862ddd3c904201d7ebc0803055`:

```bash
PYTHONPATH=backend pytest -q \
  backend/tests/test_authority_contracts.py \
  backend/tests/test_authority_snapshot_contracts.py
```

Exact reported result:

```text
..................... [100%]
21 passed
```

This was user-provided Termux execution evidence. It was not run by this replacement workspace and it predates the dependency-file repair.

### Current repair validation status

No local command has been claimed by this workspace. Its execution sandbox does not provide the repository checkout, internet package installation, Docker, or the target Python 3.11 runtime. The following evidence is therefore still required from GitHub Actions or another real Python 3.11/Linux checkout:

```bash
python -m pip install -c backend/constraints.txt -r backend/requirements-dev.txt
python -c "import numpy; print(numpy.__version__)"
PYTHONPATH=backend python -c "import victor_ai_bot.server; print('server import OK')"
PYTHONPATH=backend pytest -q \
  backend/tests/test_authority_contracts.py \
  backend/tests/test_authority_snapshot_contracts.py
```

If appropriate in the validating checkout:

```bash
make verify-backend
```

Do not mark these commands passed until their logs actually prove it.

## CI GATE

- Existing workflow: `.github/workflows/ci.yml`
- Platform: `ubuntu-latest`
- Python: `3.11`
- Repair branch CI result: **PENDING**
- Workflow/run URL: **PENDING**
- Primary branch has not received this repair yet.
- Render must not be triggered until the repair commit has passed the required Python 3.11/Linux validation.

## RENDER STAGING

- Workspace: `My Workspace`
- Service: `sovereign_capital_project`
- Service type: Docker web service
- Region/plan: Virginia / free
- Repository: `https://github.com/AlekWisoky/sovereign_capital_project`
- Tracked branch: `architecture-c-contract-tests`
- Dockerfile: `./Dockerfile`
- Auto-deploy: enabled on commit
- URL: `https://sovereign-capital-project.onrender.com`
- Last inspected failed deployment: `dep-da4k8ajtqb8s73859i4g`
- Failed deployment commit: `bbb89205059818862ddd3c904201d7ebc0803055`
- Failed deployment status: `update_failed`
- Current repair deployment: **NOT STARTED**
- Render settings changed by this repair: **NO**

## BLOCKERS

1. Obtain and inspect actual GitHub Actions evidence for the repair commit.
2. Establish explicit NumPy import, server import, and focused 21-test evidence under Python 3.11/Linux. Existing CI installs the dependency and runs the full backend suite, but its workflow does not contain the two explicit import commands or the focused command as separate steps.
3. Do not merge/push the repair to the Render-tracked branch if required validation fails or remains unproven.

## EXACT NEXT MILESTONE

1. Wait for and inspect the existing CI run on `codex/numpy-production-dependency-repair`.
2. If CI fails, stop and diagnose the exact log failure without changing the NumPy pin.
3. If CI passes but explicit import/focused-suite evidence is absent, obtain that evidence from a real Python 3.11/Linux checkout before touching the Render-tracked branch.
4. After all repository-side gates pass, merge the validated repair into `architecture-c-contract-tests` without force-push.
5. Inspect the resulting Render auto-deployment, confirm the NumPy import error is gone, verify startup, and smoke-test the existing configured health endpoint `/api/system/services`.
6. Update this checkpoint with exact commit, CI run, deployment ID/status, logs, response, blockers, and next milestone.

## IMPORTANT DURABLE DOCUMENTS

- `docs/AUTHORITY_DECISION_PACKET.md`
- `docs/AUTHORITY_SOURCE_MAP.md`
- `docs/ECONOMIC_IDENTITY_DESIGN.md`
- `docs/AUTHORITY_TEST_EXECUTION.md`
- `docs/PHASE5A_ADAPTER_READINESS.md`
- `backend/victor_ai_bot/authority_contracts.py`
- `backend/tests/test_authority_contracts.py`
- `backend/tests/test_authority_snapshot_contracts.py`
