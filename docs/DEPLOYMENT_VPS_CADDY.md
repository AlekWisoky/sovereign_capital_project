# VPS deployment (HTTPS + WSS with Caddy)

This is the recommended path for stable production hosting.

## 1) Host layout

Use:

```text
/opt/sovereign_capital/
  repo/
  env/
    backend.env
    caddy.env
  backend-data/
  backups/
  logs/
```

The runtime data directory is deliberately outside the Git working tree. The Compose bind mount maps `/opt/sovereign_capital/backend-data` to `/app/backend/data`.

## 2) Environment files

Copy the tracked examples and edit the real files on the server:

```bash
mkdir -p /opt/sovereign_capital/env /opt/sovereign_capital/backend-data
cp /opt/sovereign_capital/repo/env/backend.env.example /opt/sovereign_capital/env/backend.env
cp /opt/sovereign_capital/repo/env/caddy.env.example /opt/sovereign_capital/env/caddy.env
chmod 600 /opt/sovereign_capital/env/backend.env /opt/sovereign_capital/env/caddy.env
```

`backend.env` contains the privileged `VICTOR_ADMIN_KEY` and exact frontend CORS origin. Never commit the real files.

## 3) Backend

The production Compose file binds the backend to `127.0.0.1:8000` and exposes it only through Caddy. Public port 8000 must remain closed.

## 4) Caddy / TLS

Set `API_HOST` in `env/caddy.env` to the real API hostname, for example `api.example.com`. Point the DNS A/AAAA records at the UpCloud server before starting Caddy.

Caddy reads `API_HOST` from the environment and provisions HTTPS for the hostname.

## 5) Firewall

Allow only:

- SSH (22), preferably restricted to trusted administration sources
- HTTP (80)
- HTTPS (443)

Do not publish 8000. The application already binds that port to loopback.

If using both UpCloud L3 firewall and UFW, configure and verify both before enabling restrictive defaults so SSH access is not lost.

## 6) Deployment identity

Stamp the exact checked-out Git SHA into the backend container, then verify the running API reports the same identity before proceeding:

```bash
SHA="$(git rev-parse HEAD)"
test "${#SHA}" -eq 40
VICTOR_GIT_SHA="$SHA" docker compose -f deploy/docker-compose.prod.yml up -d --build --force-recreate victor-backend
docker compose -f deploy/docker-compose.prod.yml ps victor-backend
DEPLOYED_SHA="$(curl -fsS https://YOUR_API_HOST/api/deploy/info | python3 -c 'import json,sys; print(json.load(sys.stdin).get("git_sha", "unknown"))')"
printf 'EXPECTED_SHA=%s\nDEPLOYED_SHA=%s\n' "$SHA" "$DEPLOYED_SHA"
test "$DEPLOYED_SHA" = "$SHA"
```

The `/api/deploy/info` endpoint reports `git_sha` from `VICTOR_GIT_SHA` and reports `unknown` when a build was not stamped. Do not treat `unknown` or a mismatch as a verified deployment.

## Route discovery budget

Route evaluation uses one shared bounded budget so the two-leg and three-leg stages cannot each claim an independent unbounded deadline.

- `VICTOR_ROUTE_EVALUATION_BUDGET_MS`: total route-family evaluation budget per scan; default `9000` ms, clamped to `2000–10000` ms. The default is split into `4000` ms for two-leg and `5000` ms for three-leg evaluation.
- `VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_TIMEOUT_S`: timeout per selected-provider graph chunk; default `12` s, clamped to `3–15` s.
- `VICTOR_SELECTED_PROVIDER_FULL_SCAN_BUDGET_S`: shared selected-provider rescue budget; graph-size scaling is retained and the per-tick cap remains `12` s.
- `VICTOR_SELECTED_PROVIDER_FULL_SCAN_CHUNK_SIZE` and `VICTOR_SELECTED_PROVIDER_FULL_SCAN_PARALLELISM`: tune graph coverage and concurrency. The implementation clamps parallelism to at most three concurrent chunks.

Set these only in the server's untracked `env/backend.env`; never commit secrets or production environment files. Bigger evaluation budgets trade latency and per-tick graph-slice coverage for more route groups examined per slice. Review `route_evaluation` telemetry—especially the resolved budgets, stop reason, route groups, chunk completion, and edges covered—before increasing them further. Never weaken flash-loan repayment, revalidation, after-cost profitability, or execution-authority gates to improve candidate counts.

## Gas-adjusted split-route economics

The market pipeline exposes `gas_adjusted_split_routing` as a bounded, read-only economic frontier over route/amount evidence. It considers independent circular routes that can divide one total notional, rejects reused normalized pool identities, ranks routes by signed net value, and uses protocol/pool identity only to preserve alternatives within 50 basis points of the best single-route net estimate. It models shared L2 execution overhead plus per-route gas, subtracts sampled flash-loan premiums, converts native gas into the borrow-token unit, and includes Base L1 data-fee estimates only when exact-calldata evidence exists for every component route.

**Pricing caveat:** the extra-route gas allowance is a planning heuristic, not a proven upper bound. Base L1 fees are summed from individual ABI-v2 route calldata as a conservative proxy, not an exact estimate of the future split-plan calldata. Telemetry explicitly marks these as non-authoritative; ABI-v3 calldata must be priced from its exact encoded bytes and gas must be re-estimated/simulated.

**Important execution boundary:** the deployed `VictorArbExecutor` ABI v2 accepts one sequential `Leg[]`; it cannot execute multiple independent arbitrage cycles funded by portions of one flash loan. All split-frontier results therefore carry `execution_supported=false`, `execution_authority_granted=false`, and require executor ABI v3 plus target-state transaction simulation before they could become executable. A positive split estimate is research evidence only, not an opportunity to submit.

The model fails closed when quote evidence, gas conversion, gas-unit estimates, or required Base L1 data-fee evidence is missing. Do not loosen repayment, after-cost profitability, authority, or simulation gates to increase candidate counts. Treat `eligible_route_amount_evidence`, `split_combinations_evaluated`, `positive_after_cost_estimates`, `search_truncated_targets`, and each plan's `improvement_over_best_single_wei` as diagnostic telemetry only.

## 7) Safe mode

Keep the current Ethereum configuration non-live:

- `dry_run=true`
- `auto_trading=false`
- no `VICTOR_PRIVATE_KEY`
- no live signer configuration
- no live-authority activation

Infrastructure readiness does not authorize live trading. Issue #89 remains the explicit live-authority gate.
