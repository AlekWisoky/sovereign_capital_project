# ADR-0006: Executor Ownership via Multisig + Upgrade Plan

**Status:** Accepted (recommended for live ops)

## Context
The on-chain executor holds operational authority (flashloan callback, router calls, withdrawals). Single-key ownership is brittle.

## Decision
Adopt:
- **Multisig ownership** (e.g., Safe / Gnosis Safe) as the executor owner
- **Explicit upgrade plan**
  - if executor is non-upgradeable: redeploy + update backend config + migrate balances
  - if upgradeable proxy: multisig-controlled upgrades with time-lock and audit log entries

## Consequences
- ✅ Reduces key compromise risk
- ✅ Forces deliberate changes and better governance
- ❌ Slightly slower change management

## Operational Notes
1) Set the executor owner to multisig immediately after deployment.
2) For withdrawals/conversions, require multi-sig approval for large amounts.
3) Maintain ABI version pinning to prevent silent drift.
