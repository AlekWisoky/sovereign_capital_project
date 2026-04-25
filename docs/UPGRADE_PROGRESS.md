# Upgrade progress (append-only)

## 2026-01-31 — Multi-chain targeting (mainnet + L2)

Completed:

- Added **multi-chain runtime mode** (optional) controlled via `VICTOR_MULTI_CONFIGS`.
- Existing `/api/state` and `/ws` remain compatible and continue to represent the **active** chain.
- Added additive endpoints:
  - `GET /api/multichain/chains`
  - `POST /api/multichain/select`
  - `GET /api/multichain/state`
  - `WS /ws/multichain`

How to run (multi-chain):

```bash
export VICTOR_MULTI_CONFIGS="backend/config/ethereum.yaml,backend/config/arbitrum.yaml,backend/config/base.yaml"
uvicorn victor_ai_bot.server:app --reload --port 8000
```

Known limitations:

- Only the **active** chain supports trade-by-id and receipts endpoints.
- Default cap: 4 chains at once (`VICTOR_MULTI_MAX_CHAINS`).

Next steps:

- Add per-chain admin auth and per-chain execution toggles.
- Add a mobile chain selector (optional) mapped to `/api/multichain/select`.

## 2026-02-01 — Multi-chain mobile UI + per-chain dashboard

Completed:

- Mobile: added **Chains** tab (dashboard) and chain pill selector in **Opportunities** and **Metrics**.
- Mobile WS: connects to `/ws/multichain` and filters by the selected chain.
- Backend: fixed legacy `/ws` to remain **active-chain only** (no top-level `chain` injection).
- Backend: added additive endpoint `GET /api/multichain/summary` for lightweight per-chain dashboards.

How to run:

- Backend: same as multi-chain mode above.
- Mobile: start Expo as usual; point the base URL to the backend.

Known limitations:

- Chains dashboard updates every ~4s (poll) for stability.
- Manual trade + withdraw actions remain **active-chain scoped**.

Next steps:

- Add per-chain admin auth and per-chain execution toggles (if you want controlling each chain independently).

## 2026-02-20 — Layer 10: real arb executor (contract + calldata + hard gates)

Completed:

- Added a production-grade **flash-loan executor contract** under `contracts/` (`VictorArbExecutor.sol`).
  - Providers: Aave v3 (default) with Balancer flash-loan fallback.
  - DEX legs: Uniswap V3 SwapRouter, Curve pools, Balancer Vault swap.
  - Enforces per-leg `minOut`, global `minProfit`, and `deadline` on-chain.
  - Emits `ArbExecuted(routeId, token, amountBorrowed, profit, provider)` for receipt parsing.

- Backend execution is now **real** (no placeholder `data="0x"`):
  - Deterministic `route_id` computed from canonical route encoding.
  - Calldata builder produces real `execute(...)` payload.
  - Strict gates:
    - `estimateGas` can be required and runs before safety where possible.
    - optional same-block `eth_call` simulation with revert decoding.
  - Canonical `send_mode` aligned everywhere: `public | private | protected_rpc`.

- Runtime correctness + safety:
  - Per-block cache reset is called on new blocks (`PerBlockCache.reset_if_new_block`).
  - `Opportunity.can_execute` is populated for top-N opportunities per block (safety-only; no simulation storms).
  - Receipt watcher (bounded queue) updates realized PnL and bankroll from executor events.
  - Safety rejects are not counted as failures; only meaningful attempts affect metrics/bankroll.

How to run (executor-enabled dry-run):

```bash
export VICTOR_CONFIG=backend/config/ethereum.yaml
uvicorn victor_ai_bot.server:app --reload --port 8000
```

How to run live (requires deployed executor + key):

```bash
export VICTOR_PRIVATE_KEY=0x...  # signing key (owner of executor)
export VICTOR_CONFIG=backend/config/ethereum.yaml
uvicorn victor_ai_bot.server:app --port 8000
```

Known limitations:

- Contract deployment is not automated in this repo; see `contracts/README.md`.
- Realized `profit_after_gas_wei` is computed only when profit token matches configured `chain.weth`.

Next steps:

- Add 3-hop/triangle scanning and pool discovery (bounded) to feed the executor higher-quality routes.
- Expand receipt parsing to support profit tokens beyond WETH (token->ETH pricing if needed).

## 2026-02-20 — Layer 11: Auto-trading optimizer + Online RL (efficient)

Completed:

- Added an **EV-based DecisionEngine** that annotates opportunities under `Opportunity.meta["brain"]` (additive; no schema break).
- Added an efficient **tabular contextual bandit** (Q-learning with `gamma=0`) for online learning.
- Auto-trading stability and performance improvements:
  - Only **one in-flight execution** task at a time (scanner stays responsive).
  - Route cooldown and pending-tx limits to avoid tx spam.
  - In `brain_mode=off`, auto-trading now selects the first `can_execute` opportunity (prevents repeated failed attempts).
- Added `GET /api/brain/state` for observability.

How to use:

- Set `execution.brain_mode` to one of: `off | shadow | suggest | auto`.
- Recommended rollout:
  1) `shadow` to collect data and update RL without trading
  2) `suggest` to review recommendations
  3) `auto` to let the engine execute (with strict safety + gates)

Known limitations:

- RL sizing is **downscale-only** (<= 1.0) and does not re-quote (conservative and safe).
- Reward uses realized `profit_after_gas_wei` only when profit token matches configured `chain.weth`.


## 2026-02-21 — Layer 12: Alpha scanning + portfolio optimizer + borrow-scaling RL

Completed:

- Added **3-hop / triangle scanning** (A→B→C→A) with strict performance bounds:
  - Hard time budgets per scan phase (2-leg + 3-leg).
  - Adjacency capping per token (`VICTOR_MAX_EDGES_PER_TOKEN`, default 10).
  - Per-block cache reuse so repeated quotes within a block are cheap.

- Added **bounded discovery** (optional) for Uniswap V3 pools:
  - Uses `chain.univ3_factory` + `chain.token_universe` to discover pools via `getPool(...)`.
  - Runs every `chain.discovery_interval_blocks` with a strict call cap (`chain.discovery_max_calls`).
  - Persists to `data/discovery/<chain>.json`.
  - Disabled by default (`flags.enable_discovery=false`).

- Added a **route portfolio optimizer**:
  - Greedy EV-per-gas selection under daily gas budget.
  - Enforces non-conflicting routes using pool-level conflict keys (`meta.pool_keys`).
  - Produces a portfolio order; runtime executes at most one trade at a time (bounded) but uses the portfolio to pick the next best route when needed.

- Upgraded RL to a **richer action space** without extra RPC load:
  - Action now includes `{gas_mode, size_mult, borrow_mult}`.
  - **Borrow scaling** (borrow_mult > 1) is only applied for attempted trades, and triggers a **re-quote** of the route (no scan-time RPC increase).
  - Borrow upsizing is gated by strong `p_success` and margin thresholds and hard-capped by `safety.max_borrow_amount`.

How to enable alpha scanning:

- In config YAML:
  - `flags.enable_three_leg_loops: true`
  - (optional) `flags.enable_discovery: true` + fill `chain.univ3_factory` and `chain.token_universe`

Notes:

- `/api/state` and legacy `/ws` remain unchanged; all new data is additive (under `Opportunity.meta`).
- Portfolio selections are surfaced in `Opportunity.meta["brain"].in_portfolio` and `portfolio_rank`.


## 2026-02-21 — Patch 0 hardening + Withdraw + WalletConnect (x∆v)

Completed:

- Correctness:
  - Fixed Curve `underlying` mismatch by encoding Curve legs from quote metadata (`meta.used_underlying`) instead of config flags.
  - Fixed opportunity ID collisions by deriving `Opportunity.id` from `route_id + amount_in + block_number`.

- Operator safety:
  - Implemented real `VICTOR_ADMIN_KEY` enforcement (mutating endpoints require `X-Admin-Key`).
  - Implemented `chain.rpc_private` end-to-end (config schema + RpcManager probing + runtime send selection).
  - Added `VICTOR_AUTOSTART=1` to start scanning on FastAPI startup.

- Withdraw profits:
  - Added `withdraw_mode` (default `txdata`) and destination/token allowlists in config.
  - Added endpoints:
    - `GET /api/withdraw/config`
    - `POST /api/withdraw/prepare` (admin)
    - `POST /api/withdraw/execute` (admin, optional hot signer)

- Mobile:
  - Premium dark UI theme + brand mark `x∆v`.
  - WalletConnect v2 integration using `@walletconnect/modal-react-native`.
  - Address book persistence (multiple wallet destinations) + default destination selection.
  - Withdraw screen wired to backend `prepare` and WalletConnect `eth_sendTransaction`.
  - Added a display-only token decimals helper:
    - fetches decimals/symbol via WalletConnect eth_call (best-effort)
    - allows manual override/save per token address
    - lets user enter Human amount and shows Raw units sent to backend




## Patch: Display-only decimals helpers across app

- Mobile:
  - Added shared `TokenAmountInput` component (display-only) for safe Human↔Raw entry.
  - **Borrow sizing**: Settings screen now supports editing base borrow amount (`/api/settings base_borrow_amount`) and max borrow cap (`/api/safety max_borrow_amount`) with decimals helper.
  - **Safety thresholds**: Setup Risk screen now supports decimals helper for `minProfitAbs` and `max_borrow_amount`.
  - **Manual trade sizing**: Trade Confirm screen supports an optional `amount_in_override` with decimals helper.

- Backend (additive):
  - `/api/settings` now accepts optional `base_borrow_amount` (raw units) and updates runtime + bankroll sizing live.
  - `/api/opportunities/trade` accepts optional `amount_in_override` (raw units) and requotes the opportunity before execution.


## 2026-02-21 — Premium UX pass: decimals helpers on dashboards + opportunity rows

- Mobile (additive, no backend contract changes):
  - Added `TokenAmountDisplay` (compact + modal) to surface **human + raw** amounts everywhere.
  - **Profit dashboards** (Metrics):
    - Realized profit, expected-after-costs, realized-after-gas shown in human units when token metadata is known.
    - Recent trades list shows realized profit token amounts (uses decoded `realized_profit_token` when available).
  - **Reinvest previews**:
    - Metrics + Settings show bankroll-based preview of reinvest growth (pulled from `/api/admin/state`).
    - UI controls added to Settings to configure `auto_reinvest_enabled` + `reinvest_rate`.
  - **Opportunity list rows + details**:
    - Borrow amount and estimated profit displayed with decimals helper (tap to open modal to refresh/edit metadata).
    - Opportunity detail shows per-leg `amount_in` and `min_out` in human units.
  - Premium design updates:
    - Added `ScreenScroll` for consistent padding/background across screens.
    - Refreshed theme accents + button elevation for a more modern premium feel.


## 2026-02-21 — Public/Private deployment mode + ChainIDE hosting

- Backend:
  - Added `VICTOR_DEPLOYMENT_MODE` with `public` vs `private` behavior.
  - Public mode forces `dry_run=true`, `withdraw_mode=txdata`, disables auto-trading, and disables tx-broadcast endpoints by default.
  - Added `GET /api/deploy/info`.
  - Added `POST /api/opportunities/simulate` (always dry-run; never broadcasts).
  - `/api/settings` and `/api/multichain/settings` accept additive `dry_run` toggle.

- Mobile:
  - Setup now saves multiple backend URLs (easy switching from ChainIDE → VPS later).
  - Setup includes **ChainIDE URL Preset** to normalize port-forward URLs (force https, strip paths, trim slashes).
  - Trade confirm supports “Simulate only” and auto-defaults to simulate when backend reports public mode.

- Docs:
  - Added `docs/DEPLOYMENT_CHAINIDE.md`.
  - Added `docs/DEPLOYMENT_VPS_CADDY.md`.


## Patch: Efficiency + Build Strength (2026-02-21)

### Efficiency upgrades (highest ROI)
- Implemented JSON-RPC batching (`JsonRpcClient.batch` + `eth_call_batch`) to reduce quote RTTs.
- Batch-quote edge sets in `arb_engine.py`:
  - First-leg quoting is pre-batched per block
  - Second/third leg candidate sets are batch-quoted per hop
- Added per-route gas estimate (ranking-only):
  - Uses UniV3 QuoterV2 gas estimates when available
  - Falls back to conservative per-DEX heuristics
  - Runtime sorts by `profit_after_gas_estimate_wei` for better net-EV ranking
- Added `/ws/summary` websocket (summary or delta mode) for lightweight dashboards.

### Build-strength upgrades
- Added config schema validation:
  - `VICTOR_VALIDATE_CONFIG=1` enforces startup validation
  - otherwise logs warnings/errors but continues
- Implemented unused flags behavior:
  - `enable_curve_autogen` and `enable_balancer_autogen` now gate curve/balancer edge inclusion
- Added Foundry tests (no forge-std dependency):
  - owner-only, withdrawal allowlists, profitTo allowlist gate
- Added CI workflow:
  - ruff, black, mypy (non-fatal), pytest
  - forge tests
- Mobile: admin key stored in SecureStore (expo-secure-store); AsyncStorage persists non-sensitive settings only.


## 2026-03-07 — Execution capture + regime-aware evolution + mobile/backend completion

Completed:

- Added `backend/victor_ai_bot/execution_capture/` as the new execution-first decision layer.
- Wired execution scoring, lane routing, safe sizing, telemetry feedback, and route-template caching into runtime/execution without changing the core executor semantics.
- Added deterministic market regime classification and regime-aware strategy enablement.
- Extended meta evolution with structural mutation metadata, crossover hooks, robustness testing, lifecycle staging, diversity pressure, genealogy, and memory overlays.
- Completed mobile/backend wiring for:
  - sandbox/meta candidate fetch + apply
  - live stress evaluation
  - richer analytics series (lane success / venue quality)
  - deterministic aggression mode and full-system controls
- Added regression coverage for the execution-capture layer.

Validation performed:

- backend `pytest`
- backend `compileall`
- FastAPI route smoke checks for core + advanced endpoints
- mobile TypeScript syntax transpile check for modified screens/components
- mobile deterministic amount helper tests

Notes:

- The architecture remains additive and auditable.
- Execution capture is fail-closed: low-value or unsafe opportunities are dropped before broadcast.
- Mobile controls expose more system power, but do not bypass capital/risk/governance gates.

## 2026-03-07 — institutional remediation layer

Added:
- `agents/` package for mandates, health, attribution, regime-aware weighting
- `telemetry/` package for rich event persistence and feedback summaries
- `treasury/` capital buckets, allocation engine, reinvestment policy, capital metrics
- `evolution/` genealogy, diversity, validation, lifecycle, retirement modules
- `strategies/` family metadata, scorecards, regime binding, interactions
- `runtime_services/` bounded service wrappers for opportunities, decisions, receipts, telemetry
- domain APIs for agents / treasury / strategies / evolution / telemetry / execution calibration

Integrated into runtime:
- weighted agent state tracking
- strategy-family annotation of opportunities
- capital-engine-aware sizing/veto hooks
- telemetry event recording for decisions and outcomes
- family scorecard updates on outcome
- execution calibration updates and no-trade analytics updates

## 9.5 hardening pass

Completed:
- finished another decomposition step for runtime/API using bounded services and thin domain routes
- added capability-scoped auth with audit records for privileged actions
- upgraded telemetry/attribution/scorecards/calibration persistence to dual-write into SQLite for queryability
- deepened lane/regime-aware empirical priors in execution capture
- expanded regression tests for persistence, admin controls, and system routes


## 2026-03-08 — Engine operationalization pass

Completed:

- Added a new engine-control layer with capability registry, admission governor, degradation policy, interference controls, and per-engine budgets.
- Upgraded cross-CEX + DEX arbitrage into an inventory-aware, settlement-aware engine compatible with execution capture.
- Upgraded funding arbitrage into a carry-aware, liquidation-aware engine with normalized outputs.
- Replaced the placeholder cross-chain engine with a conservative bridge/finality/inventory-aware planner.
- Upgraded MEV search into a protected/private candidate-construction and bundle-evaluation subsystem while preserving defensive policy.
- Upgraded the bounded strategy generator with family-aware generation, success prediction, and overlap controls.
- Added `GET /api/engines/state` and `runtime_services/engine_service.py` for bounded engine integration.

Validation:

- backend `pytest -q` passed
- backend `compileall` passed
- `/api/engines/state` smoke-check passed

Known limitations:

- engine opportunities are still admitted conservatively and rely on the current capture adapter rather than native per-engine execution paths
- cross-chain remains planner/intention oriented; it does not assume atomic bridging/execution
- engine history is additive and will become more valuable as telemetry accumulates

## 2026-03-08 — Execution / capital / portfolio targeted improvement pass

Completed:

- Added execution-side venue reliability profiles, short-horizon execution risk memory, family-aware opportunity aging, and path-diversity penalties.
- Extended empirical calibration to persist projected gross edge, projected realized edge, actual realized edge, realization ratio, and calibration factor.
- Added dynamic family allocation, drawdown-aware contraction, crowding controls, and treasury metrics persistence.
- Added family covariance tracking, richer interaction risk scoring, and strategy lifecycle memory.
- Added backend + mobile support for future premium RPC preferences via `/api/system/rpc/preferences` and the mobile Setup screen.

Validation:

- backend `pytest -q` passed
- backend `compileall` passed
- system + command-center + RPC preference route smoke checks passed

## Empirical realism / meta-learning / regime pass
- execution capture now applies a simulation realism overlay (`execution_capture/simulation_realism.py`) before final lane/size decisions
- generated strategies now use an interpretable meta-success profile (`aqe/meta/success_model.py`)
- regime classification now exports family biases and preferred lanes (`regime_engine.py`) that shape capture decisions


## 2026-03-08 — fund operating system layer

- Added a lightweight fund-OS registry, stage policy, and layer manifest.
- Added alpha-platform registry/classification/scorecard summary helpers.
- Added research pipeline candidate store and promotion flow with hybrid human+AI origin support.
- Added portfolio-risk and concentration summary helpers plus fund health summary aggregation.
- Added `/api/fund/summary` and research candidate routes.
- Added optional alpha marketplace scaffolding, disabled by default.

## Execution learning + staged launch
- Added a real-time execution learning engine with route/venue/path priors, quarantine, and confidence-to-size scaling.
- Added governed launch modes and family readiness gating for V1-first rollout.
- Added backend launch APIs and mobile setup/home rollout controls.
