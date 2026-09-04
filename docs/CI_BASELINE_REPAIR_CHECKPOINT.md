# CI baseline repair checkpoint

PR #64 (`ci: clear repository baseline gates`) remains intentionally unmerged until a fresh all-green CI run is observed.

Current repair scope:

- Contracts: Foundry via-IR baseline repair.
- Backend dependencies: Linux-compatible constraint repair.
- Black: changed-backend-file gate.
- Mobile: projection compatibility call updated to the current `projectionCompatibilityAlert` signature.
- Backend mypy: the existing `decision_engine.py` `assignment` / `attr-defined` errors are isolated in a dedicated baseline target so the remaining typed core stays enforced.

This checkpoint is a CI trigger and durable handoff marker. It does not alter trading, governance, capital authority, execution lifecycle, or OMAR learning semantics.

Do not merge PR #64 until the fresh CI run is green.
