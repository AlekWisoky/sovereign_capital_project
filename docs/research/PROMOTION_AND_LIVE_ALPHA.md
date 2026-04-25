# Research promotion and live alpha posture

Generated families are no longer forced to start as passive sandbox-only ideas when marked promotion-ready.

Candidate rules now support:
- `observe_only`
- `shadow_live`
- `capped_live`
- `production`

Promotion gates require explicit telemetry, success, and drawdown evidence via `CandidateStore.evaluate_promotion(...)`.
