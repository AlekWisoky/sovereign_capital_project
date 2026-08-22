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
- Current progress commit: the commit containing this checkpoint and constraints repair
- Files changed in this progress commit: `backend/constraints.txt`, `docs/WORKSPACE_CHECKPOINT.md`
- Runtime Python source changed: **NO**
- Authority or safety behavior changed: **NO**
- Live trading: **DISABLED** (`dry_run: true`, `auto_trading: false`)

## CURRENT MILESTONE

The confirmed pre-existing GitHub Actions packaging defect was repaired with the smallest repository-consistent change. The production extra remains intact in `backend/requirements.txt`; only the constraints copy removes the extra marker so pip accepts it as a constraint.

Exact changes:

```text
backend/requirements.txt
+numpy==2.1.3

backend/constraints.txt
-eth-hash[pycryptodome]==0.7.1
+eth-hash==0.7.1
```

No other dependency versions were changed. No Dockerfile, workflow, application code, authority contract, trading behavior, Render setting, or credential was changed.

## ROOT CAUSE EVIDENCE

GitHub Actions run `CI #43` (`32574362625`) failed in the backend `Install deps` step. The raw log provided for this milestone confirms:

```text
Ubuntu 24.04
Python 3.11.16
pip 26.2.1
ERROR: Constraints cannot have extras
```

Offending entry:

```text
eth-hash[pycryptodome]==0.7.1
```

This was a constraints-file defect, not a NumPy failure. Baseline run `CI #41` (`32565868064`) failed at the same backend install step before NumPy was added, confirming the failure predates the NumPy repair.

The extra remains required in `backend/requirements.txt`:

```text
eth-hash[pycryptodome]==0.7.1
```

The dev requirements include `-r requirements.txt`, while CI invokes:

```bash
pip install -c backend/constraints.txt -r backend/requirements-dev.txt
```

## EXISTING PYTHON 3.11 / LINUX VALIDATION PATH

`.github/workflows/ci.yml` uses `ubuntu-latest`, currently Ubuntu 24.04, and `actions/setup-python@v5` with Python `3.11`. It installs the dev requirements under the constraints file, then runs Ruff, Black, Mypy, and full backend pytest. No tox, nox, or new CI system was introduced.

Additional existing paths:

- root `Dockerfile`: `python:3.11-slim`, installs `backend/requirements.txt`;
- `backend/Dockerfile`: `python:3.11-slim`, installs production requirements;
- `make verify-backend` -> `scripts/verify_boot.sh`;
- `scripts/verify_boot.sh`: server import, generated-file checks, full backend pytest, RPC sanity.

## VALIDATION STATUS

No post-repair local execution is claimed by this workspace. The sandbox cannot provide the repository checkout, internet package installation, Docker, or target Python 3.11 runtime.

Required commands after this commit, under Python 3.11/Linux:

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

The recovered Termux evidence remains separate and pre-repair:

```text
PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py
21 passed
```

## CI GATE

- Repair branch: `codex/numpy-production-dependency-repair`
- Prior CI #43: **FAILED** at dependency installation due to constraints extra
- Current post-repair CI: **PENDING**
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

## BLOCKERS / NEXT EXACT MILESTONE

1. Inspect the new GitHub Actions run for this progress commit.
2. If CI fails, retrieve the raw backend log and stop without changing versions blindly.
3. If CI is green, record exact run/job evidence and perform the merge/push gate to `architecture-c-contract-tests`.
4. Only then allow Render auto-deploy, inspect build/runtime logs, verify startup, and smoke-test the configured endpoint `/api/system/services`.
5. Keep live trading disabled throughout.

## IMPORTANT DURABLE DOCUMENTS

- `docs/AUTHORITY_DECISION_PACKET.md`
- `docs/AUTHORITY_SOURCE_MAP.md`
- `docs/ECONOMIC_IDENTITY_DESIGN.md`
- `docs/AUTHORITY_TEST_EXECUTION.md`
- `docs/PHASE5A_ADAPTER_READINESS.md`
- `backend/victor_ai_bot/authority_contracts.py`
- `backend/tests/test_authority_contracts.py`
- `backend/tests/test_authority_snapshot_contracts.py`
