# RPC endpoints

This repo uses an **RPC manager with scoring**.

You should provide at least:

- `chain.rpc_read`: 1+ endpoints for reads (`eth_call`, `feeHistory`, logs)
- `chain.rpc_send`: 1+ endpoints for sending signed transactions
- `chain.rpc_private` (optional): 0+ endpoints for private/protected submission

## Included defaults

The sample configs under `backend/config/` include **working public RPC defaults** (intended to get you running quickly).

Important:
- public RPCs can be rate-limited
- for production, replace with premium provider URLs (Alchemy/Infura/QuickNode, etc.)

## Runtime verification

Use the verifier to sanity check latency, chainId, and blockNumber:

```bash
PYTHONPATH=backend python scripts/verify_rpcs.py --config backend/config/ethereum.yaml
```

Multi-chain verification:

```bash
PYTHONPATH=backend python scripts/verify_rpcs.py --configs backend/config/ethereum.yaml,backend/config/arbitrum.yaml,backend/config/base.yaml
```

The script exits non-zero if there is **no usable read endpoint** or **no usable send endpoint**.

## Provider templates

These are templates (not hardcoded). Set environment variables in your deployment system:

- Alchemy: `https://eth-mainnet.g.alchemy.com/v2/${ALCHEMY_API_KEY}`
- Infura: `https://mainnet.infura.io/v3/${INFURA_API_KEY}`
- QuickNode: provider-specific URL

Recommended production practice:

- Put at least 2 read endpoints to reduce outliers.
- Use a dedicated send endpoint (or protected RPC) for tx submission.
- Use `rpc_private` when you have an actual private/protected relay endpoint.
