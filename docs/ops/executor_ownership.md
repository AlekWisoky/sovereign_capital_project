# Executor Ownership + Upgrade Plan (Live Ops)

## Recommended Ownership
Use a **multisig** (e.g., Safe) as the executor owner.

Why:
- prevents single-key compromise from draining funds
- forces deliberate approvals for withdraw/upgrade

## Day-1 Steps
1) Deploy executor
2) Immediately `transferOwnership(multisig)` (or equivalent)
3) Set backend `execution.executor_address` and confirm ABI version checks

## Upgrade Strategy

### If non-upgradeable executor (most conservative)
1) Deploy new executor
2) Update backend config to point to the new executor
3) Migrate balances:
   - withdraw to multisig
   - deposit to new executor

### If upgradeable proxy is used (advanced)
1) Use multisig as proxy admin / owner
2) Add a time-lock and on-chain upgrade delay
3) Require:
   - audit review of changes
   - ABI version bump (backend refuses drift)

## Withdrawal Controls
- Require a reason + audit event (already enforced in Command Center)
- Use multisig approval thresholds for large withdrawals
