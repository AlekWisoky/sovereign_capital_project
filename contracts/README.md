# VictorArbExecutor

This repo now includes a real flash-loan arb executor contract.

## Safe defaults

- **Owner-only** execution (the owner is the signing address used by the backend).
- **Allowlists** for spenders (routers/vaults) and withdrawal destinations.
- **Profit enforcement on-chain**: requires profit in the borrowed asset to be `>= minProfit`.

## Deploy

This repo does not assume Foundry/Hardhat are installed in the backend runtime.
Use your preferred Solidity toolchain to deploy.

Constructor arguments:
- `address weth`
- `address aavePool`
- `address balancerVault`
- `address univ3SwapRouter`

After deploy:
- set spender allowlist via `setSpenderAllowed(spender,true)` for:
  - Uniswap V3 SwapRouter
  - Curve pools
  - Balancer Vault
- set withdrawal allowlist via `setWithdrawalAllowed(dest,true)`

Backend config:
- `execution.executor_address`: deployed executor address
- `execution.profit_to`: allowed destination

## Notes

The backend uses `eth_call` + `estimateGas` gates with the **same calldata** it
will submit live.


## Validate

Use the repository helper to validate contracts from the repo root:

```bash
./scripts/verify_contracts.sh
```

If `forge` is installed this runs `cd contracts && forge test -q`.
