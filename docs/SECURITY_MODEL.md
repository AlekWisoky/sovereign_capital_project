# Security model

This document describes the security assumptions and controls for operating **x∆v** in both **dry-run** and **live execution** modes.

## 1) Backend key handling

- **Default is dry-run** (`execution.dry_run=true`). No signing key is required.
- Live execution requires a signing key in the environment variable configured by `execution.private_key_env` (default `VICTOR_PRIVATE_KEY`).
- The backend never stores private keys on disk.
- Recommended:
  - run the backend on a hardened host (or container runtime)
  - inject keys via a secrets manager / ephemeral environment variables
  - restrict inbound access (firewall/VPN) and outbound access (RPC allowlist)

## 2) Executor contract ownership

The on-chain executor contract (`contracts/src/VictorArbExecutor.sol`) is **owner-only**.

- Only the owner can call `execute(...)`.
- Only the owner can configure allowlists.
- Only the owner can withdraw tokens.

### On-chain allowlists

The executor includes:

1) **Spender allowlist**
   - approvals are only granted to explicitly allowed spenders.

2) **Withdrawal destination allowlist**
   - withdrawals/profit payouts can only go to destinations on an allowlist.

## 3) API surface protections

### Admin key (production-critical)

If `VICTOR_ADMIN_KEY` is set, **all mutating endpoints** require:

- header `X-Admin-Key: <VICTOR_ADMIN_KEY>`

This protects:
- runtime start/stop
- settings & safety patching
- manual trade triggering
- receipt polling
- preset switching / chain selection
- withdrawals (prepare/execute)

### Public vs private deployment mode

This repo is commonly run behind **sandbox port-forwarding** URLs (e.g., ChainIDE), which can make your backend reachable on the public internet.

We support a deployment guardrail:

- `VICTOR_DEPLOYMENT_MODE=private` (default): normal behavior.
- `VICTOR_DEPLOYMENT_MODE=public`: **safe-by-default**
  - forces `execution.dry_run=true`
  - forces `execution.withdraw_mode=txdata`
  - forces `execution.auto_trading=false`
  - disables tx-broadcasting endpoints (manual trade + backend withdrawal execute)

Optional explicit override (NOT recommended):

- set `VICTOR_PUBLIC_ALLOW_BROADCAST=1`
- include header `X-Public-Allow-Broadcast: 1` on the specific request

The recommended approach for going live is: **redeploy in private mode**.

## 4) Withdrawals: txdata vs backend mode

Withdrawals are intentionally designed to be **safe-by-default**.

### Mode A (default): `withdraw_mode: txdata`

- Backend returns tx calldata + suggested gas via:
  - `POST /api/withdraw/prepare`
- Mobile uses WalletConnect to have an **external wallet** sign and broadcast the tx.

**Security posture**:
- backend is NOT a hot signer
- withdraw signing key stays in the external wallet

### Mode B (optional): `withdraw_mode: backend`

- Backend signs and broadcasts withdrawals via:
  - `POST /api/withdraw/execute`

**Security posture**:
- backend becomes a hot signer
- you must treat the backend host as highly sensitive

## 5) Withdrawal destination allowlist (defense-in-depth)

Withdraw endpoints enforce an **off-chain allowlist** (`execution.withdraw_allowlist`) and the executor enforces an **on-chain allowlist**.

Recommended model:
- Keep allowlist small
- Add destinations explicitly
- Use non-custodial txdata mode whenever possible

## 6) Execution safety gates

- Profit/repay safety runs before submission.
- estimateGas gate (`safety.require_estimate_gas=true`) aborts if `estimateGas` fails.
- simulation gate (`safety.require_simulation=true`) runs `eth_call` prior to submission.

## 7) RPC privacy

If you configure `chain.rpc_private` and set `execution.send_mode` to `private` or `protected_rpc`, the backend will prefer `rpc_private` for transaction submission.

This reduces public mempool exposure, but does not guarantee MEV protection.



## Manual trade sizing override (admin)

`POST /api/opportunities/trade` accepts optional `amount_in_override` (raw units). When provided, the backend will requote the opportunity for that notional under the configured slippage before attempting execution. This is **admin-protected** and does not change the raw-unit contract.

For public deployments where tx broadcasting is disabled, use:

- `POST /api/opportunities/simulate` (always dry-run; never broadcasts)
