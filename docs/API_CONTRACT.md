# x∆v API Contract (Step 8)

This file documents the **strict mobile↔backend contract**.

## REST
### GET /api/state
Returns the runtime state object (no wrapper):

```json
{
  "chain": "ethereum",
  "opportunities": [
    {
      "id": "…",
      "chain": "ethereum",
      "strategy": "two-leg:univ3->curve",
      "expected_profit_raw": "123456789",
      "expected_profit_usd": "0",
      "route": { "legs": [ { "dex":"univ3", "venue":"…", "token_in":"…", "token_out":"…", "amount_in":"…", "min_out":"…", "data":"0x" } ] },
      "min_outs": ["…"],
      "can_execute": false,
      "created_at_ms": 0,
      "meta": {}
    }
  ],
  "metrics": {
    "flashLoans": 0,
    "attempted": 0,
    "succeeded": 0,
    "failed": 0,
    "last_block": 0,
    "scan_ms": 0,
    "last_error": "",
    "last_submitted_block": 0,
    "gas_mode": "standard",
    "send_mode": "public",
    "realized_profit_raw": "0",
    "efficiency_pct": 0.0,
    "success_rate_pct": 0.0
  },
  "rpc": {
    "read": [ { "url":"…", "ok":true, "latency_ms":12, "failures":0, "score":1.0 } ],
    "send": [ { "url":"…", "ok":true, "latency_ms":12, "failures":0, "score":1.0 } ]
  }
}
```

## WebSocket
### WS /ws
Each message mirrors REST `/api/state` inside `data`:

```json
{ "type": "state", "data": <same as /api/state> }
```

## Bigint safety (hard rule)
All potentially-large numeric quantities are serialized as **strings**:
- all `*_wei`, `amount_*`, `reserve*`, `profit*`, `gas*`, `fee*`, `min_out*`, `liquidity*`, `sqrt*`, etc.

Counters / latencies remain numbers (safe ints).

## Admin key header

If the backend environment sets `VICTOR_ADMIN_KEY`, all mutating endpoints require:

- Header: `X-Admin-Key: <value>`

## Decision / Brain observability

### GET /api/brain/state

Returns a stable summary of the DecisionEngine state. This endpoint is **additive** and does not change
the core execution contract.

```json
{
  "ok": true,
  "chain": "ethereum",
  "brain_mode": "off|shadow|suggest|auto|smmae_shadow|smmae_suggest|smmae_auto",
  "rl": {
    "epsilon": 0.08,
    "states": 123,
    "actions": 12
  },
  "last_portfolio": ["opp_id_0"],
  "aqe": {
    "enabled": false,
    "mixer": "vdn",
    "last_info": {},
    "last_reward": {},
    "last_observed": {}
  },
  "route_stats": { "routes": 42 }
}
```

Notes:
- `aqe.enabled=false` when SMMAE is not active.
- When active, `aqe.last_info` includes joint entropy + exploration flags + per-agent α/confidence.

## Withdraw

### GET /api/withdraw/config

```json
{
  "ok": true,
  "chain": "ethereum",
  "chain_id": 1,
  "executor_address": "0x...",
  "withdraw_mode": "txdata",
  "allowlist": ["0x..."],
  "tokens": ["0x..."],
  "profit_to": "0x..."
}
```

### POST /api/withdraw/prepare  (admin)

Request:

```json
{ "token": "0x...", "to": "0x...", "amount": "1000000", "from_address": "0x..." }
```

Response:

```json
{
  "ok": true,
  "to": "0xDESTINATION",
  "executor": "0xEXECUTOR",
  "from_address": "0xESTIMATION_SENDER_OR_NULL",
  "requested_from_address": "0xCALLER_SUPPLIED_SENDER_OR_NULL",
  "execution_from_address": "0xBACKEND_SIGNER_OR_NULL",
  "token": "0xTOKEN",
  "amount": "1000000",
  "tx": { "to": "0xEXECUTOR", "data": "0x...", "value": "0x0", "chainId": 1 },
  "suggested": {
    "gas_limit": 220000,
    "max_fee_wei": "25000000000",
    "priority_fee_wei": "2000000000",
    "nonce": 12
  }
}
```

Mobile uses this response to call WalletConnect `eth_sendTransaction`.

Withdraw preparation and execution routes now expose canonical failure semantics on blocked, unavailable, invalid, and degraded outcomes. Invalid numeric payloads return `status=invalid` with stable `reason_code` values like `invalid_amount` or `invalid_numeric`; allowlist and execution-mode denials return `status=blocked`; missing executor/RPC/private-key dependencies return `status=unavailable`; and send/quote failures return `status=degraded`. These routes also no longer leak raw parse or RPC exception text in their API payloads.

Direct withdraw and convert mutation routes also now reject unknown request fields with `reason_code=unknown_request_fields` so typoed capital-movement payloads cannot appear successful while silently narrowing operator intent.

Those same direct withdraw and convert prepare/execute routes now also enforce required token proof, destination proof, address-shape proof, and positive amounts on their capital-movement paths. Missing `token` / `token_in` values fail explicitly with `reason_code=missing_token`, malformed input token addresses fail with `reason_code=invalid_token`, missing `to` destinations fail with `reason_code=missing_destination`, malformed destination addresses fail with `reason_code=invalid_destination`, malformed optional `from_address` values on prepare routes fail with `reason_code=invalid_from_address`, and empty or zero `amount` / `amount_in` inputs fail explicitly with `reason_code=invalid_amount`, all before calldata preparation or backend send logic runs. Direct convert routes now also reject negative `min_out` with `reason_code=invalid_min_out`, non-positive explicit `fee` with `reason_code=invalid_fee`, out-of-range explicit `fee` values that do not fit the contract's `uint24` domain with `reason_code=invalid_fee`, and explicit non-positive `deadline` with `reason_code=invalid_deadline` instead of silently normalizing or deferring those failures to calldata encoding. They also distinguish malformed explicit `token_out` values from unresolved configured stable output: malformed explicit output tokens fail with `reason_code=invalid_token`, unresolved default stable output fails with `reason_code=stable_not_configured`, and `POST /api/withdraw/convert/quote` now rejects malformed `token_in` with `reason_code=invalid_token`, malformed `fee_tiers` with `reason_code=invalid_fee_tiers`, out-of-range `fee_tiers` entries that do not fit `uint24` with `reason_code=invalid_fee_tiers`, and malformed or out-of-range `slippage_bps` with `reason_code=invalid_slippage_bps` before any quote attempt. Non-integral numeric JSON values for `fee_tiers` (for example `500.5`) and `slippage_bps` (for example `1.5`) are also rejected explicitly instead of being silently narrowed. Direct backend send routes now also require a usable transaction hash from the upstream send result; if the send layer reports success without a hash or returns a malformed non-hash string, `POST /api/withdraw/execute` and `POST /api/withdraw/convert/execute` fail with canonical `reason_code=send_failed` instead of reporting a false successful execution. Those execute routes now also reject malformed configured private keys explicitly with `reason_code=invalid_private_key_env` instead of raising during account construction. After a usable transaction hash is returned, those same execute routes no longer treat submission alone as completion: they now immediately classify backend execution as `status=mined_success`, `status=pending`, `status=sent`, or `status=receipt_unavailable`, and they fail canonically with `reason_code=receipt_reverted` when an immediate receipt proves on-chain revert. Successful direct execute responses now also expose `tx_proof_reason` so operator surfaces can distinguish visible pending public transactions (`tx_visible`), private sends with no public receipt yet (`private_no_public_receipt`), degraded receipt lookup on the read RPC (`receipt_lookup_degraded`), and public submissions that the read RPC cannot yet prove visible (`tx_not_visible`). Those same direct withdraw and convert prepare/execute responses now use a consistent destination/executor taxonomy across the direct off-ramp family: top-level `to` refers to the requested withdrawal destination, while `executor` refers to the on-chain executor contract actually called and `tx.to` remains the executor contract for signing/broadcast purposes. They now also use a tighter sender taxonomy: direct prepare responses echo the effective estimation sender under `from_address`, preserve any caller-supplied sender separately under `requested_from_address`, expose the configured backend execution signer under `execution_from_address` when one is available, and in backend mode anchor nonce/gas suggestions to that execution signer even when a different explicit `from_address` is supplied. Direct execute success responses expose both legacy `from` and canonical `from_address`, and direct execute immediate-revert payloads now expose both fields as well, so operator/reporting code does not need to special-case sender context by outcome. Direct backend execute routes now also accept an optional `reason` field, preserve it under `action_reason` on canonical invalid, blocked, unavailable, degraded `send_failed`, successful, and immediate-revert payloads when the operator supplied one, and append operator audit entries for those same direct execute outcomes instead of rejecting the request as `unknown_request_fields` or dropping human intent from pre-send failures. Convert-withdraw prepare and execute success/immediate-revert payloads now also carry `token_in`, `token_out_requested`, normalized `token_out`, `amount_in`, `min_out`, `fee`, and `deadline`, and direct withdraw prepare success now also carries `token` and `amount`, so operator surfaces do not need to infer execution shape from an earlier request body. `token_out_requested` is now the normalized requested token string (trimmed and defaulted) across convert quote, prepare, and execute responses instead of echoing raw request whitespace back to operator/reporting code. `POST /api/withdraw/convert/quote` now follows that same quote/prepare/execute taxonomy more closely by surfacing `token_in`, `amount_in`, `token_out_requested`, normalized `token_out`, and the canonical `fee_tiers` considered alongside `expected_out`, `min_out`, and selected `fee`, so operator/reporting code does not need to reconstruct quote context from the original request body alone.

`POST /api/withdraw/all/config` now follows the same proof standard for withdraw-all control changes. It rejects unknown request fields with `reason_code=unknown_request_fields`, uses canonical boolean parsing for `enabled` and `activate_destination`, rejects activation without a destination as `reason_code=missing_destination`, and treats explicit invalid destinations as canonical invalid payloads instead of silently ignoring them. Withdraw-all destination proof now also requires address-shaped hex input, so malformed non-hex addresses are rejected as `reason_code=invalid_destination` and no longer appear valid on config or state-gating paths. No-op config payloads now remain true no-ops and do not persist or audit a synthetic configuration change.

`POST /api/withdraw/all/execute` now follows the same proof standard for withdraw-all execution controls. It rejects unknown request fields with `reason_code=unknown_request_fields` and uses canonical boolean parsing for `dry_run`, so typoed keys or values like `"definitely"` fail explicitly before any execute-state mutation. When an upstream send fails during backend execution, or reports success without a valid transaction hash, the service now records `last_status=execute_failed` / `last_reason_code=send_failed` instead of incorrectly reporting completion. Replay of a prior failed or blocked execute now preserves the original top-level outcome instead of forcing `ok=true`. Withdraw-all execute now also rejects malformed configured private keys explicitly with `reason_code=invalid_private_key_env` instead of raising during account construction. When a withdraw-all execution or preparation result exists but state persistence fails afterward, the response now stays top-level degraded while explicitly surfacing `attempted_status`, `attempted_reason_code`, `attempted_preview_id`, `result_available`, and `result_persisted=false`. When backend sends do succeed, withdraw-all now records item-level `tx_status` proof and only marks the flow `completed` on immediate mined success across all items; otherwise it records `status=submitted` with `submission_state` instead of falsely reporting a completed off-ramp. Execute responses now also include `result.lifecycle_summary`, which normalizes attempted, confirmed, outstanding, reverted, and failed item counts for operator-safe post-submit tracking.

`GET /api/withdraw/all/state` now surfaces persistence-load degradation explicitly. If withdraw-all control state cannot be loaded from disk, the endpoint remains operator-safe but reports `status=degraded` and `reason_code=state_load_failed` while preserving the current control eligibility under `control_reason_code`. State responses now also include `last_result_summary`, a canonical lifecycle snapshot derived from the persisted withdraw-all result so operator surfaces do not have to infer item-level progress from raw execution items. When the persisted wipe state is still `submitted`, the state endpoint now opportunistically refreshes outstanding tx hashes against the read RPC, promotes item-level proof monotonically, and persists a stronger canonical result when it can prove later completion or later reversion. State responses now also expose `last_result_refresh` metadata plus additive `last_result_refresh_ts_ms`, `last_result_refresh_status`, and `last_result_refresh_reason_code` fields so operator surfaces can tell whether the wipe result was freshly revalidated, skipped because a short backend cooldown is active, or had no refreshable transactions left. The state payload now also persists refresh-failure memory under `last_result_refresh_failure`, `last_result_refresh_failure_ts_ms`, `last_result_refresh_failure_reason_code`, and `last_result_refresh_failure_count` so repeated read-RPC degradation does not get flattened into a generic “no stronger proof yet” operator view. State responses now also expose canonical refresh-failure severity (`last_result_refresh.failure_severity`, `last_result_refresh_failure.severity`) so operator surfaces do not have to infer seriousness from raw counts alone. Refresh-failure reasons are also normalized canonically: `refresh_read_rpc_missing` means no read RPC is configured for wipe-state revalidation, while `refresh_receipt_lookup_degraded` means receipt lookup on the configured read RPC degraded during revalidation. Refresh-failure memory now decays automatically over time when no new degraded revalidation occurs, and state responses expose additive decay metadata (`last_result_refresh.failure_decay_interval_ms`, `last_result_refresh.failure_next_decay_ts_ms`, `last_result_refresh_failure.decay_interval_ms`, `last_result_refresh_failure.next_decay_ts_ms`) so operator surfaces can distinguish fresh degradation from stale degradation that is aging out.

`POST /api/withdraw/all/preview` is now treated as a strict no-input control surface. Empty bodies and `{}` remain accepted for compatibility, but stray request fields now fail explicitly with `reason_code=unknown_request_fields`, and malformed non-object bodies fail with `reason_code=unexpected_request_body` before preview-side state or audit activity.

`WithdrawAllService` now also hardens persistence write failure at the service boundary. If config, preview, or execute outcome state cannot be saved to disk, the caller receives a deterministic degraded payload with `reason_code=state_save_failed` instead of a raw filesystem exception, and valid runtime behavior outside persistence remains unchanged.

## Settings / Safety / Manual Trade (mutating)

### POST /api/settings  (admin)

Patch live runtime settings. Request fields are optional.

```json
{
  "auto_trading": true,
  "gas_mode": "fast",
  "send_mode": "private",
  "auto_reinvest_enabled": true,
  "reinvest_rate": 25,
  "brain_mode": "shadow",
  "base_borrow_amount": "100000000000000000"
}
```

Notes:
- `base_borrow_amount` is a **raw integer string** (wei-like). Mobile may provide a display-only decimals helper to safely derive this number.

Additive fields:
- `dry_run` (boolean): toggle dry-run at runtime. In public deployments, the server may clamp this back to `true`.

Runtime settings mutation routes (`/api/settings` and `/api/multichain/settings`) now validate and normalize payloads before calling `set_settings`. Boolean-like fields use canonical parsing (`true/false`, `1/0`, `yes/no`, `on/off`), integer-like fields such as `reinvest_rate` reject ambiguous values with `reason_code=invalid_integer_value`, and mode fields (`gas_mode`, `send_mode`, `brain_mode`) reject unsupported values with explicit invalid reason codes. These routes also reject unknown request fields with `reason_code=unknown_request_fields` so typoed settings patches cannot appear successful while silently drifting operator intent. Empty settings bodies now fail explicitly with `reason_code=empty_settings_patch` instead of succeeding as no-op mutations. `/api/multichain/settings` also now rejects unknown or mismatched `chain` targets with `reason_code=unknown_chain` rather than applying the patch to the wrong active runtime.

### POST /api/safety  (admin)

```json
{
  "minProfitAbs": "1000000000000000",
  "minProfitBps": 25,
  "slippage_bps": 50,
  "max_borrow_amount": "2000000000000000000",
  "require_estimate_gas": true,
  "require_simulation": false
}
```

All raw-unit amounts remain integer strings.

All boolean-like control fields on `/api/safety`, `/api/presets/apply`, and `/api/fioa/safe_mode` now use canonical boolean parsing (`true/false`, `1/0`, `yes/no`, `on/off`) and reject ambiguous values with `ok=false`, `status=invalid`, and `reason_code=invalid_boolean_value`.

Safety numeric fields on `/api/safety` are now staged and validated before mutation. Integer-valued thresholds (`minProfitBps`, `slippage_bps`) and raw-unit string amounts (`minProfitAbs`, `max_borrow_amount`) must be non-negative integer values; invalid payloads return `ok=false`, `status=invalid`, and `reason_code=invalid_integer_value` without partially mutating live safety state. If bankroll cap synchronization fails, the route fails closed with `status=unavailable` and leaves prior safety settings intact.

Overlay mutation routes now reject unknown request fields on `/api/fioa/agent/restrict`, `/api/fioa/agent/resume`, `/api/fioa/safe_mode`, and `/api/narrative/explanation_level` with `reason_code=unknown_request_fields` so typoed control payloads cannot appear successful while silently dropping intent. `/api/fioa/agent/restrict` and `/api/fioa/agent/resume` now require a non-empty `agent_id`; missing IDs fail with `reason_code=missing_agent_id`, and blank IDs fail with `reason_code=invalid_string_value`. `/api/narrative/explanation_level` now requires an explicit non-empty `level` instead of defaulting missing payloads back to `STANDARD`. `/api/fioa/safe_mode` now requires an explicit `on` toggle with `reason_code=missing_safe_mode_toggle`, rejects blank explicit `reason` values with `reason_code=invalid_string_value`, validates `ttl_s` as a non-negative float with `reason_code=invalid_float_value`, and preserves explicit `ttl_s=0` instead of coercing it back to the default window.

Superstructure mutation routes on `/api/org/agent/pause` and `/api/org/agent/resume` now reject unknown fields with `reason_code=unknown_request_fields`, require a non-empty `agent_id`, and fail with canonical invalid payloads instead of loose string errors when no agent target is supplied.

### POST /api/command/directive  (admin)
### POST /api/command/risk_multiplier  (admin)
### POST /api/command/exploration_cap  (admin)
### POST /api/command/approve  (admin)
### POST /api/command/force_safe_mode  (admin)

Operator-command mutation routes now validate payloads before calling the runtime overlay. Non-negative float fields such as `ttl_s`, `risk_multiplier`, and `exploration_cap` reject ambiguous or negative values with `ok=false`, `status=invalid`, and `reason_code=invalid_float_value` instead of throwing or partially mutating operator controls. `/api/command/directive` also validates that the `directive`/`payload` value is a mapping and rejects other shapes with `reason_code=invalid_mapping_value`.

These routes now reject unknown request fields with `reason_code=unknown_request_fields` so typoed operator-control payloads cannot appear successful while silently dropping intent.

They also reject structurally empty mutation bodies with `reason_code=empty_command_payload` instead of defaulting into live control changes. `/api/command/approve` now fails with `reason_code=missing_proposal_id` when no proposal ID is supplied, and both `/api/command/approve` and `/api/command/force_safe_mode` reject blank string identifiers/reasons with `reason_code=invalid_string_value`.

Launch mutation routes now validate operator intent before mutating rollout state. `POST /api/launch/mode` rejects missing or blank `mode` values with `reason_code=missing_mode` / `invalid_string_value` and rejects unsupported modes with `reason_code=invalid_launch_mode` instead of silently resetting the launch profile to `V1_ONLY`. `POST /api/launch/pause-family`, `/api/launch/revert-family`, and `/api/launch/quarantine-family` now require a non-empty `family` field. `POST /api/launch/enable-next` still allows the family field to be omitted so the runtime can use its recommended next family, but an explicitly blank `family` is now rejected with `reason_code=invalid_string_value`. All launch mutation routes now reject unknown request fields with `reason_code=unknown_request_fields`, and `/api/launch/quarantine-family` rejects a blank explicit `reason_code` instead of silently normalizing it.

Fund research mutation routes now validate explicit promotion intent before mutating research lifecycle state. `POST /api/fund/research/candidates` rejects missing `thesis` with `reason_code=missing_thesis`, rejects blank explicit string fields with `reason_code=invalid_string_value`, and rejects malformed `metadata` values with `reason_code=invalid_mapping_value` instead of raising during candidate creation. `POST /api/fund/research/promote` now requires a non-empty `candidateId`, rejects malformed `telemetryCount` / `score` / `riskScore` values with canonical integer/float invalid reason codes, rejects unsupported explicit `stage` values with `reason_code=invalid_stage`, and returns `reason_code=candidate_not_found` instead of surfacing raw `KeyError` when the requested candidate does not exist. Both routes now also reject unknown request fields with `reason_code=unknown_request_fields` so typoed research-governance payloads cannot silently narrow or misapply operator intent. When the research candidate store is unavailable, both mutation routes now return canonical `status=unavailable` / `reason_code=candidate_store_unavailable` payloads instead of loose unstructured failures. Promotion denials caused by insufficient telemetry, low success rate, or excessive drawdown now return explicit `status=blocked` payloads with a top-level `reason_code` synchronized to the embedded promotion decision so operator governance surfaces can distinguish blocked promotions from invalid requests or unavailable runtime state. When the candidate store exists but `create`, `evaluate_promotion`, or `transition` fails because of bounded persistence/runtime corruption, both routes now also degrade to the same canonical `candidate_store_unavailable` payload instead of surfacing route-level runtime errors.

### POST /api/opportunities/trade  (admin)

Manual execution of the currently-visible opportunity by ID.

Request:

```json
{ "id": "opp_...", "amount_in_override": "250000000000000000" }
```

- `amount_in_override` is optional. If provided, the backend will **requote the opportunity** for the requested notional (keeping min_outs/slippage consistent) before attempting execution.
- Raw-unit contract remains unchanged; this is a safe additive feature.

### POST /api/opportunities/simulate  (admin)

Always-dry-run simulation endpoint (never broadcasts).

This is the preferred endpoint for **public deployments** (e.g., port-forwarded sandboxes), where tx-broadcasting endpoints are disabled.

Request:

```json
{ "id": "opp_...", "amount_in_override": "250000000000000000" }
```

Response matches the `trade` shape but always returns `dry_run=true`.

### GET /api/deploy/info

Returns deployment mode and whether an explicit broadcast override is enabled:

```json
{ "ok": true, "mode": "public" | "private", "public_allow_broadcast": false }
```


### WebSocket: /ws/summary (additive)
Lightweight dashboard websocket.

- Path: `/ws/summary`
- Query params:
  - `mode=summary|delta` (default: summary)
  - `full_every=N` (delta mode; send full summary every N messages)

Message shapes:
- Full summary:
```json
{ "type": "summary", "data": { "chain": "...", "block": 0, "opp_count": 0, "metrics": {...}, "top_opportunity": {...} } }
```
- Delta:
```json
{ "type": "delta", "data": { "block": 0, "metrics": {...} } }
```

This is backward-compatible and does not replace `/ws` or `/ws/multichain`.

---

## Phase 5 — Arbitrage Engine (additive)

### GET /api/arbitrage/state
Returns screener + adapter state (observe-only by default).

### POST /api/arbitrage/start (admin)
Starts the arbitrage runtime loop if enabled.

### POST /api/arbitrage/stop (admin)
Stops the arbitrage runtime loop.

---

## Phase 6 — MEV Module (additive, defensive-first)

### GET /api/mev/state
Returns best-effort mempool/MEV telemetry:
- ws connectivity
- bounded pending tx sample
- risk percentiles (heuristic)

### POST /api/mev/start (admin)
Starts MEV monitoring (only if `execution.mev.enabled=true`).

### POST /api/mev/stop (admin)
Stops MEV monitoring.

Notes:
- The MEV module is **defensive-first** and used as a safety rail.
- This repo does not implement predatory MEV execution (no sandwich attacks).


## Command Center additions

### GET /api/commandcenter/snapshot

Unified mobile snapshot used by the 7-tab command center.

Additive fields in this export include:
- `controlMode`
- `pausedReason`
- `rpcDegraded`
- `dataSource`
- `wealthGoal`
- `governance.rftEpisodeExportEnabled`

### POST /api/commandcenter/control  (admin)

Mutates command-center controls. The route accepts either the documented top-level control shape or the mobile/provider envelope with a nested `patch` object. Equivalent examples:

```json
{
  "controlMode": "view_only|assist|auto",
  "rewardTraceEnabled": true,
  "latencyProfilingEnabled": true,
  "rftEpisodeExportEnabled": false,
  "reason": "operator change"
}
```

```json
{
  "patch": {
    "controlMode": "view_only|assist|auto",
    "rewardTraceEnabled": true,
    "latencyProfilingEnabled": true,
    "rftEpisodeExportEnabled": false
  },
  "reason": "operator change"
}
```

Notes:
- Empty control payloads are rejected with `ok=false` and `reason_code=empty_control_patch` instead of silently producing a no-op governance event.
- Conflicting nested and top-level control mutations are rejected with `reason_code=ambiguous_control_patch`.
- Unknown control fields are rejected with `ok=false` and `reason_code=invalid_control_patch`.
- Invalid enum/boolean payloads are rejected rather than silently ignored.
- Control mutations fail closed if control-state persistence fails.

## Fund read-surface semantics

### GET /api/fund/capital-truth
### GET /api/fund/family-hardening
### GET /api/fund/doctrine
### GET /api/fund/ledger  (admin)
### GET /api/fund/internal-prime  (admin)

Notes:
- Successful responses preserve the existing nested compatibility keys (`capitalTruth`, `familyHardening`, `doctrine`, `ledger`, `internalPrime`).
- When the underlying component is unavailable, the route now surfaces a top-level canonical unavailable payload (`ok=false`, `status`, `reason_code`, `reason`) while still preserving the nested compatibility key.

### Auxiliary operator read surfaces

The direct auxiliary operator read routes now use canonical unavailable semantics when the underlying subsystem is missing or disabled.

Affected direct read endpoints include command, superstructure, MEV/meta, FIOA, and narrative state/report surfaces.

Canonical unavailable shape:

```json
{
  "ok": false,
  "status": "unavailable",
  "reason_code": "unavailable",
  "reason": "unavailable",
  "enabled": false
}
```

Notes:
- Aggregated multichain read routes may still return a successful top-level aggregation wrapper, but any missing per-chain subsystem state now uses the canonical unavailable payload inside the `chains` map.
- This removes false-success `ok=true` fallbacks from auxiliary operator read paths while preserving existing compatibility fields like `enabled=false`.
- This keeps older consumers working while preventing false-success control-surface semantics.

## System auxiliary read surfaces

The system-level auxiliary state readers now use canonical unavailable semantics when the runtime does not implement the underlying capability. This removes false-success `ok=true` disabled fallbacks while preserving compatibility keys expected by older consumers.

Affected routes:
- `GET /api/unified/state`
- `GET /api/spread/opportunities`
- `GET /api/orchestrator/state`
- `GET /api/consensus/state`
- `GET /api/behaveagent/state`
- `GET /api/governance/state`
- `GET /api/blockspace/state`
- `GET /api/agenthub/state`

Canonical unavailable examples:

- `/api/unified/state` → `ok=false`, `status=unavailable`, `reason_code=unified_state_unavailable`, `enabled=false`
- `/api/spread/opportunities` → `ok=false`, `status=unavailable`, `reason_code=spread_opportunities_unavailable`, `count=0`, `opps=[]`
- `/api/orchestrator/state` → `ok=false`, `status=unavailable`, `reason_code=orchestrator_state_unavailable`, `enabled=false`
- `/api/consensus/state` → `ok=false`, `status=unavailable`, `reason_code=consensus_state_unavailable`, `last={}`
- `/api/behaveagent/state` → `ok=false`, `status=unavailable`, `reason_code=behaveagent_state_unavailable`, `enabled=false`
- `/api/governance/state` → `ok=false`, `status=unavailable`, `reason_code=governance_layer_unavailable`, `enabled=false`
- `/api/blockspace/state` → `ok=false`, `status=unavailable`, `reason_code=blockspace_state_unavailable`, `enabled=false`
- `/api/agenthub/state` → `ok=false`, `status=unavailable`, `reason_code=agent_hub_state_unavailable`, `state={}`

Successful reads are unchanged and still pass through the runtime payload verbatim.

## Wealth goal API

### GET /api/wealth/goal
Returns the current treasury/wealth target plus a conservative recommendation.

The read surface is now synchronized across service-backed and fallback runtimes:
- successful responses include the canonical wrapper fields `ok=true`, `status=available`, `canonical=true`
- service-backed responses identify `service=wealth_goal_service`
- fallback responses identify `service=wealth_goal_fallback` and now include `state`, `explanation`, and `history` instead of returning only a thin legacy goal snapshot
- if treasury exists but the goal object is missing, the route now fails closed with `ok=false`, `status=unavailable`, and `reason_code=treasury_goal_unavailable` instead of raising or returning a misleading partial payload

### POST /api/wealth/goal  (admin)

```json
{
  "target_return_percentage": 8.0,
  "time_horizon_seconds": 1209600,
  "risk_tolerance": "moderate",
  "max_drawdown_pct": 6.0,
  "capital_commitment_pct": 35.0,
  "reason": "Operator wealth plan update"
}
```

Wealth and treasury goal mutation routes now validate payload shape before mutation. Unknown fields are rejected with `ok=false`, `status=invalid`, and `reason_code=unknown_request_fields`. Numeric goal fields reject malformed values with `reason_code=invalid_float_value` or `reason_code=invalid_integer_value` instead of silently coercing or partially mutating goal state. Structurally empty goal updates are rejected with `reason_code=empty_goal_patch` instead of producing a false-success no-op.

`POST /api/wealth/goal` now preserves omitted goal fields during partial updates instead of resetting them to normalized defaults. This keeps operator intent narrow and prevents accidental horizon, risk, or commitment drift when only a single goal attribute is being updated. Explicit no-op patches now return `ok=true` with `changed=false` and skip unnecessary persistence/audit churn.

### POST /api/treasury/goal  (admin)

Accepts the canonical treasury goal patch fields:
- `target_return_percentage`
- `time_horizon_seconds`
- `risk_tolerance`
- `max_drawdown_pct`
- `capital_commitment_pct`

Like `/api/wealth/goal`, this route now rejects unknown fields, malformed numeric payloads, and empty goal patches before any treasury goal mutation is applied. Explicit no-op patches return `ok=true` with `changed=false` and do not persist a redundant goal write.

### GET /api/treasury/goal
Successful reads now include `ok=true`, `status=available`, `canonical=true`, and `service=treasury_goal_route` while preserving the existing `goal` payload. If treasury exists but the goal object is missing, the route fails closed with `reason_code=treasury_goal_unavailable`.

### GET /api/treasury/state
If the runtime does not implement `treasury_state()`, this route now returns the canonical unavailable payload with `reason_code=treasury_state_unavailable` instead of a false-success `ok=true` fallback.

## RFT / replay API

### GET /api/rft/schema/proposal
Returns the strict proposal JSON schema used for scoring/export.

### GET /api/rft/episodes/sample?limit=10
Returns deterministic sample episodes built from replay bundles.

### POST /api/rft/episodes/export  (admin)
Exports deterministic proposal-only training episodes when export is enabled.

### GET /api/rft/replay/bundle/{event_id}
Returns an immutable replay bundle for a trade lifecycle event.

### POST /api/rft/replay/verify
Verifies the determinism/hash integrity of a replay bundle.

### GET/POST /api/rft/grader/score  (admin)
Scores a proposal against a stored episode using the multi-grader stack.

## Advanced execution / evolution endpoints

### GET /api/meta/candidates
Returns the latest generated strategy candidates for sandbox review and apply flows.

### POST /api/stress/evaluate  (admin)
Evaluates deterministic robustness scenarios such as `liquidity_drop_50`, `gas_5x`, `slippage_3x`, and `noise_injection`.

### GET /api/rft/schema/proposal
Returns the strict proposal-only RFT JSON schema used for offline scoring/export.

### GET /api/rft/episodes/sample
Returns deterministic episode samples for proposal grading/review.

### POST /api/rft/episodes/export  (admin)
Exports deterministic replay/training episodes.

### GET /api/rft/replay/bundle/{event_id}
Returns the immutable replay bundle associated with a captured execution attempt.

### POST /api/rft/replay/verify
Verifies that a replay bundle is internally consistent and deterministic.

## Additional 9.2+ domain routes

- `GET /api/agents/state`
- `GET /api/agents/attribution`
- `GET /api/treasury/capital`
- `GET /api/strategies/scorecards`
- `GET /api/evolution/state`
- `GET /api/telemetry/summary`
- `GET /api/execution/calibration`

These routes are additive and preserve legacy API behavior.

## Analytics read-surface unavailable semantics

- `GET /api/analytics/state` now fails closed with canonical unavailable payloads when the analytics runtime is unavailable. Backward-compatible keys such as `enabled` are preserved.
- `GET /api/analytics/datasets/{name}` now returns canonical unavailable payloads when the analytics runtime is unavailable while preserving `dataset` and `rows` compatibility keys.
- `GET /api/analytics/dashboards` now returns canonical unavailable payloads when the analytics runtime is unavailable while preserving the `dashboards` compatibility key.

## Route runtime error-surface synchronization

- `GET /api/agents/state` now surfaces deterministic degraded payloads (`reason_code=agent_hub_state_failed`) instead of leaking raw exception text. Compatibility keys `state`, `attribution`, and `weights` are preserved.
- `GET /api/agents/attribution` now surfaces deterministic degraded payloads (`reason_code=agent_attribution_failed`) instead of leaking raw exception text. The compatibility key `agents` is preserved.
- `GET /api/strategies/scorecards` now surfaces deterministic degraded payloads (`reason_code=strategy_scorecards_failed`) instead of leaking raw exception text while preserving the `families` compatibility key.
- `GET /api/evolution/state` now surfaces deterministic degraded payloads (`reason_code=meta_state_failed`) on runtime failures while preserving `enabled=false` compatibility, and still returns canonical unavailable payloads when the meta runtime is absent.
- `GET /api/meta/candidates` now surfaces deterministic degraded payloads (`reason_code=meta_candidates_failed`) on runtime failures instead of leaking raw exception text while preserving `items` and `candidates` compatibility keys.

## Analytics query-surface proof semantics

- `POST /api/analytics/ask` now rejects empty questions and unknown request fields with canonical invalid payloads before calling the analytics runtime.
- `POST /api/analytics/ask` now returns canonical unavailable payloads when the analytics runtime is unavailable instead of a thin `{"ok": false, "error": "disabled"}` fallback.
- `POST /api/analytics/ask` now surfaces runtime query failures with deterministic degraded payloads (`status=degraded`, `reason_code=quicksight_ask_failed`) instead of leaking raw exception text.
- `POST /api/analytics/scenario` now rejects empty payloads and malformed known numeric knobs with canonical invalid payloads before calling the analytics runtime.
- `POST /api/analytics/scenario` preserves arbitrary scenario params for compatibility while normalizing known numeric knobs to finite floats when present.
- `POST /api/analytics/scenario` now returns canonical unavailable payloads when the analytics runtime is unavailable instead of a thin `{"ok": false, "error": "disabled"}` fallback.
- `POST /api/analytics/scenario` now surfaces runtime scenario failures with deterministic degraded payloads (`status=degraded`, `reason_code=quicksight_scenario_failed`) instead of leaking raw exception text.

## Analytics runtime error semantics

- `GET /api/analytics/state`, `GET /api/analytics/datasets/{name}`, and `GET /api/analytics/dashboards` now surface QuickSight runtime failures with deterministic degraded payloads instead of raw exception text.
- Compatibility keys such as `enabled`, `dataset`, `rows`, and `dashboards` are preserved on these degraded payloads.

## Telemetry route error semantics

- `GET /api/telemetry/summary` now surfaces runtime reporting failures with deterministic degraded payloads (`status=degraded`, `reason_code=telemetry_summary_failed`) instead of leaking raw exception text.
- `GET /api/execution/calibration` now surfaces runtime calibration read failures with deterministic degraded payloads (`status=degraded`, `reason_code=execution_calibration_failed`) instead of leaking raw exception text.
- Compatibility keys such as `realization`, `agents`, and `items` are preserved on these degraded payloads.

- `POST /api/withdraw/convert/quote` now rejects malformed `chain.univ3_quoter_v2` config with canonical `invalid_quoter_address` unavailable semantics before quote attempts.

Fund research read surfaces now stay synchronized with the canonical runtime research-pipeline state. `GET /api/fund/research/candidates` now returns the same `items`, `pipelineCounts`, and `throughput` shape exposed by the runtime research pipeline facade, and both the read route and fund summary degrade to an empty research pipeline snapshot instead of surfacing persistence/workspace corruption through the API.

Fund summary component reads now stay synchronized with the dedicated fund control/read surfaces. `profitDoctrine`, `ledger`, `internalPrime`, `capitalTruth`, and `familyHardening` now degrade to the same structured unavailable payloads used by the dedicated `/api/fund/*` routes instead of surfacing component-read failures or drifting to thin `{}` fallbacks inside `/api/fund/summary`.
Fund summary unavailable fallbacks are now synchronized across `/api/fund/summary`, `StateSummaryService`, and `RuntimeStateFacade`, so missing fund-service wiring still returns a deterministic summary payload with canonical unavailable component states instead of a thin top-level unavailable shell.
