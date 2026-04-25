# Migration notes — institutional remediation layer

## Backward compatibility

- Legacy core routes remain intact (`/api/state`, `/api/commandcenter/snapshot`, execution routes).
- New domain routes are additive.
- Existing execution semantics remain bounded by the current executor, safety gates, and command-center controls.

## New persisted state

The upgrade adds new persisted JSON/JSONL state under the backend data directory for:
- agent weighting
- agent attribution
- telemetry events
- execution calibration
- no-trade analytics
- strategy family scorecards
- evolution genealogy

## Recommended rollout

1. Enable the new telemetry + summary endpoints first.
2. Observe calibration / agent attribution / family scorecards in assist mode.
3. Keep full-system mode off until telemetry baselines are populated.
4. Enable capital-engine influence and evolution promotions gradually.
5. Review false-admission / false-drop and realization-ratio summaries before widening capital caps.

## Operational note

`fullSystemEnabled` is still bounded. It increases visibility and coordinated overlays, but does not bypass the executor, capital gates, or governance controls.

## 9.5 hardening pass

This pass adds:
- SQLite-backed queryable persistence for telemetry, agent attribution, family scorecards, and execution calibration.
- Thin domain routes for system/admin summaries and security audit access.
- Capability-based authorization checks with security audit logging.
- Additional runtime services for agent, treasury, analytics, execution gating, and lifecycle state.
- Deeper regime-aware calibration and lane priors in the execution-capture decision engine.

Compatibility notes:
- Existing JSON/JSONL files are still written for local portability.
- New SQLite state lives at `data/state/xdv_runtime_state.sqlite3` and is safe to delete in local dev to rebuild from fresh state.
- Legacy API routes remain available.

## Engine operationalization pass

This pass adds new engine state and telemetry for:
- `cross_cex_dex`
- `funding_arb`
- `cross_chain_arb`
- `mev_search`
- `auto_strategy_generator`

New additive route:
- `GET /api/engines/state`

Compatibility notes:
- existing execution routes and capture policy remain unchanged
- engines do not create direct execution side paths
- low-confidence engines are automatically restricted to observe-only / capped-live behavior by the admission governor
