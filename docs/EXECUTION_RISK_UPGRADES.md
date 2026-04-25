# Execution and Risk Upgrades

This upgrade pass promotes latency, routing, adversarial ordering, drawdown, and kill-switch controls into the live execution and fund-control path.

## Added live execution inputs

- Rolling endpoint quality by lane and relay
- Deterministic smart-order-routing with bounded venue subset search
- Adversarial pending-state gating with relay necessity and post-ordering EV
- Flash-loan race/reserve/provider hardening
- Drawdown hard-stop and family drawdown gating
- Kill-switch suppression by fee burn, stale quotes, slippage drift, and RPC degradation
- Historical simulation VaR/ES and deterministic stress scenarios
- Money-loop-aligned reward shaping persisted into telemetry traces

## Operator-visible state

New API-visible state now includes:

- `/api/system/execution/quality`
  - `endpoint_quality`
  - `venue_scorecards`
  - `drawdown`
  - `kill_switch`
- `/api/risk/live-state`
  - live drawdown
  - live kill switch
  - capital state

## Safety model

- All new runtime-critical logic is deterministic and bounded.
- Missing data degrades to conservative defaults.
- Half-life gating uses measured pipeline latency.
- Drawdown and kill-switch logic fail closed on suppression.
- Private/protected lanes are preferred under adversarial ordering pressure.


## Phase 2 execution-realism closure

This pass closes the remaining institutional-execution gaps by turning prior advisory metadata into execution-grade behavior:

- Smart order routing now produces an execution route plan that can mutate the chosen opportunity before send and apply deterministic fallback trees when the preferred venue subset is no longer executable.
- Route-quality persistence is now fed back into route planning so realized venue-subset outcomes influence future venue-split selection.
- Pending-state/adversarial modeling now uses bounded conflict clustering and scenario replay instead of overlap-only heuristics.
- Endpoint quality is now fed from a unified endpoint universe built from config, RPC manager health, and operator preferences.
- Flash-loan provider redundancy and reserve-distortion outputs are carried through to the execution path instead of remaining advisory only.
- Operator/mobile surfaces now expose endpoint-universe state, live execution routing/adversarial summaries, route-quality, drawdown hard-stop state, and kill-switch reasons.

### Additional operator-visible state

`/api/system/execution/quality` now includes:

- `endpoint_universe`
- `route_quality`
- `live_execution`

`/api/risk/live-state` now includes:

- `endpoint_quality`
- `endpoint_universe`
- `route_quality`
- `live_execution`

These are lightweight summary surfaces intended for mobile/operator inspection rather than heavy client-side assembly.
