# Authority Contract Test Execution

## Canonical environment

The repository's canonical backend test environment is defined by:

- Python `3.11` in `.github/workflows/ci.yml`.
- `backend/requirements-dev.txt` for development/test dependencies.
- `backend/constraints.txt` for pinned versions, including `pytest==9.0.2`.
- CI installs with:

```bash
python -m pip install --upgrade pip
pip install -c backend/constraints.txt -r backend/requirements-dev.txt
```

No second dependency system was introduced. `pyproject.toml` contains formatter, linter, and type-checker configuration, but not the dependency lock.

## Canonical focused command

From the repository root, after dependency installation:

```bash
PYTHONPATH=backend pytest -q backend/tests/test_authority_contracts.py backend/tests/test_authority_snapshot_contracts.py
```

The repository CI currently runs the full backend suite from `backend` with `pytest -q`; this document intentionally defines the smaller authority-contract command for Phase 4 validation.

## Phase 4B validation target

The focused suite must explicitly cover:

- nested dictionary mutation;
- nested list and sequence mutation;
- caller-alias mutation;
- unsupported mutable evidence rejection;
- same material plan content producing the same ID;
- each material plan mutation changing the ID;
- mismatched supplied plan ID rejection;
- source-specific revision compatibility;
- explicit-now freshness and stale detection;
- unresolved freshness policy;
- conflict representation;
- unit and missing-decimal rejection;
- correlation identity distinctness;
- pure validation without hidden I/O.

## Execution status at checkpoint creation

The available validation environment had Python `3.12.13`, no writable repository checkout, and no `pytest` executable. Therefore the focused suites were **NOT EXECUTED** and no pass/fail/count result is claimed.

A future workspace must clone the exact checkpoint HEAD, install the pinned backend development dependencies, run the canonical command above, record exact collected/passed/failed/skipped/error counts and duration, then update `docs/WORKSPACE_CHECKPOINT.md`.

## Safety boundary

This command exercises contract tests only. It does not wire authority contracts into runtime, create adapters, create reservations, modify settlement/PnL, alter Solidity/ABI, change configuration, sign, submit, or enable live trading.
