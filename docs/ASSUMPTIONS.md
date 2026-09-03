# Assumptions (explicit, safe defaults)

## Multi-chain mode

- Multi-chain operation is opt-in via `VICTOR_MULTI_CONFIGS` (comma-separated YAML paths).
- Default maximum chains is 4 (`VICTOR_MULTI_MAX_CHAINS=4`) to avoid runaway resource usage.
- `/api/state` and `/ws` reflect the active chain (the first config by default). This preserves existing REST/WS contracts.
- `/api/multichain/state` and `/ws/multichain` are additive, and include a top-level `chain` field.
- Snapshots for `/api/multichain/state` use a per-chain timeout of 2s (`VICTOR_MULTI_SNAPSHOT_TIMEOUT_S=2.0`) so one stalled chain does not hang the API.

## Multi-chain auto-trading safety

- **Safety default:** only the **active** chain may auto-trade. On startup and on active-chain switches, non-active chains are forced `auto_trading=false`.
- If you explicitly want all configured chains to auto-trade concurrently (higher risk), set `VICTOR_MULTI_ALLOW_AUTO_ALL=1`.

## Real executor defaults

- **Safe default:** `execution.dry_run=true`. The bot will still scan, compute `can_execute`, and produce an execution plan, but will not broadcast a transaction.
- Live execution requires:
  - a deployed executor contract address (`execution.executor_address`), and
  - a signing key present in `execution.private_key_env` (default: `VICTOR_PRIVATE_KEY`).

- **Gas & safety gates:**
  - If `safety.require_estimate_gas=true` (default), a failing `estimateGas` aborts execution.
  - Simulation (`eth_call`) is optional (`safety.require_simulation=false` default) to avoid excessive RPC load.

- **Realized PnL unit safety:** `realized_profit_after_gas_wei` is computed only when the executor reports profit in the configured `chain.weth` token.
  - If profit is in another token, the raw token profit is recorded but net-after-gas is left as 0 (safe default; avoids wrong unit conversions).

- **Per-block `can_execute`:** populated for top opportunities using safety rails only (no simulation). This avoids per-opportunity RPC storms.

## DecisionEngine + RL defaults

- `execution.brain_mode` defaults to `off` (no behavior change unless enabled).
- Brain modes:
  - `shadow`: compute and log recommendations; never auto-trade.
  - `suggest`: compute and annotate opportunities; never auto-trade.
  - `auto`: decision engine selects trade/skip and can override gas mode per attempt.
- RL is a tabular contextual bandit stored under `data/rl/` and updated only on finalized receipts.
- **Sizing is downscale-only** (<= 1.0) by design; upsizing requires re-quoting and is intentionally disabled as a safety default.
- Default probability floor for unknown routes is 0.75 with Laplace smoothing; this prevents overfitting to low-sample noise.
- Auto-trading is additionally protected by:
  - one in-flight execution task at a time
  - pending-tx cap (`execution.max_pending_txs`, default 1)
  - per-route cooldown (`execution.trade_cooldown_blocks`, default 1)

## Capital-demand composition

- Capital demand is a **decision input**, not execution authority. It composes the amount that can be funded after hard constraints are applied.
- Wealth-goal posture, bounded `aggression_mode`, and AI recommendation context may modify a valid demand; none may bypass governance, risk, exposure, conversion, execution-plan, latency/freshness, treasury, provider, or prime limits.
- Treasury amounts carry both human denomination/decimals and exact integer base units for downstream accounting.
- `v1_external_prime` is the canonical V1 posture: V1 may request external/internal-prime capital while the treasury is still being accumulated. A zero treasury balance therefore does not disable a valid V1 demand when prime/provider capacity is available.
- `own_capital` is the post-accumulation posture: demand is funded from treasury allocatable capital and never silently falls back to prime.
- `hybrid` is explicit and uses treasury first, then internal prime for residual demand.
- The operator may select V1-only operation; the system must not silently promote to another strategy version or capital posture.
- Prime/provider fees reduce economic capacity; they do not create permission to exceed hard limits.
- Internal-prime authority is represented separately from treasury ownership so borrowed capital cannot be mistaken for owned fund capital.

## AQE / SMMAE defaults (Phases 1–4)

- AQE is **opt-in** via `execution.brain_mode`:
  - `smmae_shadow`: AQE annotates opportunities and updates metrics, but **never** trades.
  - `smmae_suggest`: AQE annotates opportunities for UI, but **never** trades.
  - `smmae_auto`: AQE may influence execution knobs (gas/size/borrow multipliers) **only** when the core decision engine already selected a trade candidate.

- Intrinsic curiosity (Phase 2) is enabled inside AQE by default, but **does not affect trading** unless an `smmae_*` mode is selected.
  - Intrinsic reward combines RND novelty, visitation counts, and outcome surprise.
  - Combined reward: `R = R_team + β * R_intrinsic` with a conservative default `β=0.15`.

- Adaptive exploration controller (Phase 3) adjusts per-agent `α_i` within `[min_alpha, max_alpha]` based on:
  - joint policy KL drift,
  - joint entropy collapse,
  - coordination collapse proxy (JS divergence across agent policies),
  - TD-error variance.
  This only changes the mixture between `π_i^self` and `π_i^team`.

- Harmony layer (Phase 4) adds:
  - budgeted exploration caps to prevent simultaneous over-exploration,
  - curiosity de-duplication via compressed state embeddings,
  - cooperative credit assignment proxies for analytics.
  These outputs are **observability-first** and are not used to force trades.

## Alpha layer assumptions (2026-02-21)

- **Triangle scanning bounds:** 3-hop scanning is strictly bounded by time budgets and adjacency capping (`VICTOR_MAX_EDGES_PER_TOKEN`, default 10). This is chosen to prevent combinatorial explosion and RPC storms.

- **Bounded discovery is opt-in:** Discovery is disabled by default (`flags.enable_discovery=false`). When enabled, it runs infrequently (`chain.discovery_interval_blocks`, default 50 on mainnet template) and is hard-capped by `chain.discovery_max_calls` (default 24). Discovery only targets UniV3 via `univ3_factory.getPool(...)`.

- **Conflict definition for portfolios:** A "non-conflicting" trade set is defined as disjoint **pool-level keys** derived from route legs:
  - UniV3: `univ3:<token0>:<token1>:<fee>`
  - Curve: `curve:<pool>:<i>:<j>:<underlying>`
  - Balancer: `bal:<poolId>`
  This avoids over-conflating UniV3 swaps (we do not treat SwapRouter as the pool).

- **Borrow upsizing safety gate:** RL may pick `borrow_mult > 1.0` only when:
  - `p_success >= 0.85` and `margin_ratio >= 0.0010`
  - and borrow is clamped by `safety.max_borrow_amount` if provided.
  Upsizing triggers **re-quoting only on attempted trades** (no scan-time load increase).

- **Portfolio optimizer:** Uses a greedy EV-per-gas heuristic. This is not exact knapsack, but is stable, fast, and works well in production constraints.


## Phase 6 — MEV module assumptions
- Many RPC providers do not support mempool subscriptions (`eth_subscribe` for `newPendingTransactions`). The module is best-effort and will report `no_ws_url` or reconnect errors if unsupported.
- Risk scores are heuristics (calldata selector + gas tip + value). They are used only to **block unsafe public sends** when configured.
- Private routing is supported via `eth_sendPrivateTransaction` when the configured send RPC implements it.
- Hard policy: the system includes sandwich detection/avoidance, but does not implement sandwich attack execution.


## Proposal-only RFT / replay defaults

- `execution.rft.enabled=false` by default.
- Episode export is OFF by default and must be enabled in config or command-center controls.
- Replay bundles are additive and never grant execution authority.
- Graders use conservative integer-only scoring (`usd_micro`, `bps`, `ppm`).
- If a live capital-engine decision cannot be reconstructed perfectly offline, the capital grader prefers deny/penalty over optimistic approval.

## Wealth goal defaults

- Wealth goals are advisory to treasury/capital posture and do not override execution safety gates.
- Goal stepping is conservative: on success, the next suggested target increases modestly rather than exponentially.

## Mobile operator-key protection defaults

- Admin keys are stored encrypted via Expo SecureStore.
- When biometric lock is enabled, the app keeps the key out of process memory until the operator explicitly unlocks the session.
- Locking the session clears the in-memory key and disarms execution controls.

## Execution capture / aggression defaults

- Execution capture is **additive** and sits between discovery and submission; it does not rewrite core calldata or executor semantics.
- `aggression_mode` is deterministic and only changes scoring/sizing posture through bounded treasury/runtime overlays.
- `full_system_enabled=false` by default. Enabling it unlocks evolution/governance observability controls, but risk gates, policy gates, and lane restrictions still apply.
- In public deployments, high copy-risk opportunities are biased toward `PRIVATE` / `PROTECTED` lanes or dropped.
- Stress evaluation endpoints are advisory and deterministic; they do not execute trades or mutate live positions directly.
