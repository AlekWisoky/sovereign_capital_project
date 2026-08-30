# Phase 24 — Canonical adaptive flash-loan sizing integration

The canonical production entrypoint is now `execution_capture.flashloan_sizing.choose_flashloan_size`.

Its ordering is:

1. Existing flash-loan hardening and route/provider checks run first.
2. The Phase 23 adaptive risk-budget controller is invoked from the same sizing entrypoint.
3. Canonical decision/correlation identity is propagated into the sizing result.
4. `capital_engine_state` / the existing treasury capital state supplies the adaptive risk-budget ceiling.
5. Wealth/aggressiveness/goal-gap signals affect preference only inside the bounded budget.
6. Governance, capital-authority freshness, drawdown, max-borrow, max-loss, net-profit and net-ROI constraints remain hard gates.
7. `sizing_id` is deterministic and is metadata for attribution; it does not replace canonical decision identity.
8. The existing on-chain executor remains authoritative for atomic repayment and minimum-profit enforcement.

The adapter is intentionally non-authoritative: it cannot sign, execute, approve capital, or bypass governance. When the canonical identity is absent, the legacy path remains available for backward-compatible non-production/unit callers; production decisions must carry the canonical identity for adaptive sizing to participate.
