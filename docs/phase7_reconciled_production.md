# Phase 7 — Reconciled production architecture

The production path is now treated as one lifecycle:

`market data -> strategy/signal -> canonical decision -> OMAR bounded recommendation -> governance/capital authority -> execution -> settled ledger outcome -> exact action attribution -> learning update -> next decision`

## Invariants

- Auto execution requires a canonical `TradeDecision` with matching canonical decision ID and correlation ID.
- OMAR is a learning/recommendation layer, not a capital, signing, governance, or execution authority.
- `capital_engine_state()` remains the authoritative capital input; sizing is constrained by the existing capital, treasury, family-allocation, drawdown, provider, gas, and net-edge controls.
- Applied sizing carries a first-class `sizing_id` through execution and settlement.
- Learning is gated on canonical settled ledger evidence and duplicate-proof identity/quality checks.
- Operator, wealth-goal, and AI intent are captured as immutable decision-time attribution rather than mutable global state.
- Sentry is optional observability only and carries safe lifecycle IDs, including sizing identity; it cannot block trading when absent.

## Rollout rule

The branch is not a live-trading authorization. The complete Linux CI gate must be green on the final head SHA before merge/staging. Live execution remains subject to existing deployment-mode, governance, admission, and capital controls.
