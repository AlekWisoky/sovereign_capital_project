# Authoritative implementation sequence

This sequence is the current engineering gate order for the Capital operating system. A later phase does not receive implementation authority merely because its design is complete; the preceding phase must be green.

## Phase A — Mobile/backend control and truth boundary

```text
PR #93 — canonical mobile/backend foundation
  ↓
PR #99 — guarded mutations / explicit confirmation / fail-closed client boundary
  ↓
PR #100 — stale/realtime reconciliation kernel
  ↓
PR #100 G — narrow `/ws/summary` adapter
  ↓
F4/I — mobile security, backend contract, and lifecycle gate
```

### G realtime boundary

- Backend `/ws/summary` is an existing read-only dashboard contract.
- Mobile requests complete `summary` messages for the reconciliation path. Delta mode remains available to legacy callers but is not used by the canonical reconciliation path because merging deltas in a screen would create a second state arbiter.
- `VictorSummaryWS` owns transport lifecycle only: connect, reconnect, timeout, malformed-message rejection, and cleanup.
- `Reconciler` is the only arbiter of accepted realtime state.
- WebSocket observations are advisory and never replace canonical polling truth.
- Polling remains the source of `CommandCenterSnapshot` truth and its freshness state.
- Realtime cannot authorize mutations, execution, governance/admission, capital state, or live trading.
- WebSocket disconnects/errors preserve last-known-good canonical polling state.

## Phase B — Institutional economic sizing

```text
Issue #94
  ↓
Institutional sizing / capital-scale validation
```

Do not begin Phase B until Phase A's security/contracts/lifecycle gate is green.

## Phase C — OMAR context + attribution

```text
Issue #97
  ↓
Progressive OMAR context
  ↓
Exact agent/strategy attribution foundation
```

## Phase D — Agent Intelligence v2

Upgrade the existing AgentHub, agent contracts, Portfolio Manager, Risk Manager, calibration, and attribution surfaces. Do not introduce a second agent framework.

## Phase E — AI Alpha Marketplace

```text
Issue #95
  ↓
Existing AQE strategy factory
```

## Phase F — deterministic MEV / blockspace intelligence

```text
Issue #96
  ↓
Deterministic blockspace/MEV observation and execution-intelligence layer
```

## Phase G — Research / Evolution Engine

Research, evaluation, promotion, retirement, and out-of-sample evidence remain subordinate to canonical decision identity, governance, settlement truth, and attribution.

## Phase H — Replit visual layer

Only after backend contracts and mobile lifecycle/security boundaries are frozen enough to prevent visual work from creating competing state or mutation paths.

## Phase I — Integrated mobile/backend validation

Run the complete integrated contract, security, lifecycle, reconciliation, and operator-flow validation across the canonical six-tab mobile IA and backend.

## Phase J — Live-authority activation review

```text
Issue #89
  ↓
Dry-run / auto-trading authority review
  ↓
Private/protected submission lane
  ↓
Wallet/executor configuration
  ↓
Deliberately capped flash-arb transaction test plan
```

No real capital execution is authorized before this gate passes.

## Phase K — capped real flash-arb

Only the V1 `flash_arb` family may receive real capital authority. Future strategy families remain observe-only/paper/shadow until separately admitted.

## Phase L — institutional scaling

Scale only after settled economics, expectation error, attribution, governance, sizing, and execution evidence support the increase.

## Non-negotiable architecture rules

1. `decision_id` remains the single canonical decision identity through execution, receipt, settlement, and learning.
2. Canonical settlement remains the authoritative source of realized economics.
3. Governance/admission answers **whether** capital may be used; adaptive sizing answers **how much**.
4. OMAR recommends and learns; it does not receive unrestricted execution authority.
5. Human cognitive control is a decision-hygiene sidecar, not a capital authority layer.
6. Realtime mobile data is advisory latency information; it is never canonical execution/governance truth.
7. No phase may introduce a parallel state store, duplicate agent framework, duplicate decision identity, or alternate capital authority path.
