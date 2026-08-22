# WORKSPACE CHECKPOINT

## RECOVERY RULES

Repository history and recorded execution evidence are authoritative. Do not infer tests or deployment success from source state alone. Preserve live-trading safeguards and do not weaken authority contracts.

## PROJECT / GIT STATE

- Project: Sovereign Capital OS
- Repository: `AlekWisoky/sovereign_capital_project`
- Primary branch: `architecture-c-contract-tests`
- Starting primary HEAD: `b5d5d5a861a9da7baf37af4cb9a4180bcc8eee7a`
- Previous functional commit: `bbb89205059818862ddd3c904201d7ebc0803055`
- Working branch: `codex/numpy-production-dependency-repair`
- Prior repair commit: `4a3ff6ebcc73ea409dcec47a95475a61cd1c28bc`
- Constraints repair commit: `5168583ee68a611fbf73106caf7167d4f80ad66a`
- Current checkpoint commit: the commit containing this update
- Files changed in the repair milestone: `backend/requirements.txt`, `backend/constraints.txt`, `docs/WORKSPACE_CHECKPOINT.md`
- Runtime Python source changed: **NO**
- Authority or safety behavior changed: **NO**
- Live trading: **DISABLED** (`dry_run: true`, `auto_trading: false`)

## CURRENT MILESTONE

The confirmed CI constraints defect from CI #43 was corrected, but the next CI run still fails during dependency installation. The repair branch remains isolated and the Render-tracked primary branch remains untouched.

Exact intended changes:

```text
backend/requirements.txt
+numpy==2.1.3

backend/constraints.txt
-eth-hash[pycryptodome]==0.7.1
+eth-hash==0.7.1
```

The `eth-hash[pycryptodome]` extra remains intact in `backend/requirements.txt`. No other dependency version was changed. No Dockerfile, workflow, application code, authority contract, trading behavior, Render setting, or credential was changed.

## ROOT CAUSE EVIDENCE

CI #43 (`32574362625`) ran on Ubuntu 24.04 with Python 3.11.16 and pip 26.2.1. Its raw backend log confirmed:

```text
ERROR: Constraints cannot have extras
```

The confirmed offending constraints entry was `eth-hash[pycryptodome]==0.7.1`. Baseline CI #41 (`32565868064`) failed at the same install step before NumPy was added, proving that failure predates the NumPy repair.

## FOLLOW-UP CI RESULT

After applying the authorized constraints correction, CI #45 (`32574864349`) ran for commit `5168583ee68a611fbf73106caf7167d4f80ad66a`. The backend job still failed during `Install deps`; Ruff, Black, Mypy, and Pytest were skipped. The public job metadata exposes only exit code/status, not the raw pip line, so the new first meaningful package-level failure is **NOT YET VERIFIED**.

The constraints file still contains another extra-bearing entry, `uvicorn[standard]==0.40.0`, but this is only a diagnostic lead, not a confirmed cause. Do not change it until the raw CI log proves it is the next offending entry.

The contracts job also failed in CI #45 at `Forge tests`; this is independent of the backend install gate and has not been diagnosed here.

## EXISTING PYTHON 3.11 / LINUX VALIDATION PATH

`.github/workflows/ci.yml` uses `ubuntu-latest`, currently Ubuntu 24.04, and `actions/setup-python@v5` with Python `3.11`. It installs the dev requirements under the constraints file, then runs Ruff, Black, Mypy, and full backend pytest. No tox, nox, or new CI system was introduced.

Additional existing paths:

- root `Dockerfile`: `python:3.11-slim`, installs `backend/requirements.txt`;
- `backend/Dockerfile`: `python:3.11-slim`, installs production requirements;
- `make verify-backend` -> `scripts/verify_boot.sh`;
- `scripts/verify_boot.sh`: server import, generated-file checks, full backend pytest, RPC sanity.

## VALIDATION STATUS

No post-repair local execution is claimed by this workspace. The sandbox cannot provide the repository checkout, internet package installation, Docker, or target Python 3.11 runtime.

Required commands after the install gate is proven green:

```bash
python -m pip install --upgrade pip
pip install -c backend/constraints.txt -r backend/requirements-dev.txt
python -c "import numpy; print('numpy:', numpy.__version__)"
PYTHONPATH=backend python -c "import victor_ai_bot.server; print('server import OK')"
PYTHONPATH=backend pytest -q \
  backend/tests/test_authority_contracts.py \
  backend/tests/test_authority_snapshot_contracts.py
make verify-backend
```

Recovered Termux evidence remains separate and pre-repair:

```text
PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py
21 passed
```

## CI GATE

- CI #43: **FAILED**, backend dependency install, confirmed `eth-hash[pycryptodome]` constraint extra
- CI #45: **FAILED**, backend dependency install after the eth-hash correction; exact new pip cause pending raw log
- Do not merge into `architecture-c-contract-tests` until CI is green.
- Do not deploy Render until CI is green.

## RENDER STAGING

- Service: `sovereign_capital_project`
- Type: Docker web service
- Region/plan: Virginia / free
- Tracked branch: `architecture-c-contract-tests`
- Dockerfile: `./Dockerfile`
- Auto-deploy: enabled
- URL: `https://sovereign-capital-project.onrender.com`
- Last failed deployment: `dep-da4k8ajtqb8s73859i4g` at `bbb89205059818862ddd3c904201d7ebc0803055`
- Current repair deployment: **NOT STARTED**
- Render settings changed: **NO**

## CURRENT BLOCKERS / NEXT EXACT MILESTONE

1. Retrieve the raw backend log for CI #45 (`32574864349`), especially job `97035592999`.
2. Identify the actual next constraints/install failure. Do not assume `uvicorn[standard]` without raw evidence.
3. Apply only the explicitly authorized or newly proven minimal correction, then rerun CI.
4. If the install gate passes, record exact NumPy import, server import, focused authority, and existing backend verification evidence.
5. Only after CI is green, merge the validated repair into `architecture-c-contract-tests`, allow Render auto-deploy, inspect build/runtime logs, verify startup, and smoke-test `/api/system/services`.
6. Keep live trading disabled throughout.

## IMPORTANT DURABLE DOCUMENTS

- `docs/AUTHORITY_DECISION_PACKET.md`
- `docs/AUTHORITY_SOURCE_MAP.md`
- `docs/ECONOMIC_IDENTITY_DESIGN.md`
- `docs/AUTHORITY_TEST_EXECUTION.md`
- `docs/PHASE5A_ADAPTER_READINESS.md`
- `backend/victor_ai_bot/authority_contracts.py`
- `backend/tests/test_authority_contracts.py`
- `backend/tests/test_authority_snapshot_contracts.py
