# x∆v — Sovereign Capital Threat Model

## Scope
This threat model covers the v1 flash-loan atomic arbitrage stack, mobile operator app, control-plane APIs, and the new replay/RFT export overlays.

## Primary assets
- operator admin key
- backend signer / txdata builder
- executor ownership and withdrawal allowlists
- trade opportunity data
- reward traces and replay bundles
- governance / command-center controls

## Main trust boundaries
1. Mobile app ↔ FastAPI backend
2. Backend ↔ RPC / private relay / mempool infrastructure
3. Backend ↔ on-chain executor contract
4. Control plane ↔ execution plane
5. Replay/RFT exports ↔ offline analysis

## Key threats
- stolen operator credential or unlocked mobile session
- malformed admin requests to control/withdraw endpoints
- replay-bundle tampering or audit-log truncation
- RPC degradation producing stale quotes or failed execution
- incorrect flashloan callback sender / spender misuse
- over-permissive autonomous execution in defensive or sandbox regimes
- accidental drift where training/scoring logic gains execution authority

## Implemented mitigations in this export
- admin-gated mutating endpoints
- hash-chained command-center audit log
- allowlisted spender / withdrawal model in the executor
- proposal-only RFT overlay; execution authority unchanged
- deterministic replay bundles for post-trade verification
- safe defaults OFF for export/scoring features
- mobile secure operator-key storage with optional device-auth gating
- control modes (View Only / Assist / Auto) and explicit pause reasons

## Residual risks
- smart-contract risk remains material until external audit
- latency-sensitive execution can still fail under degraded RPC/relay conditions
- operator misconfiguration can still increase exposure if safety toggles are relaxed
- mobile device compromise defeats local UX hardening

## Recommended next controls before meaningful capital
- external contract audit
- Slither/static-analysis pass in CI
- venue-specific shadow deployment / dry-run validation
- production secrets hardening on the VPS
- monitoring/alerting for replay export and audit-log anomalies
