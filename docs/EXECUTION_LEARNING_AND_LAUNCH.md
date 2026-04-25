# Execution Learning Engine + V1-First Launch

This upgrade adds two institutional launch systems:

1. An **Execution Learning Engine** that estimates live execution success, competition pressure, route/venue/path reliability, and freshness survival.
2. A **V1-first staged rollout** controller that starts the fund in `flash_arb` and only enables additional families when telemetry and readiness justify it.

## Execution Learning Engine

The learning engine lives under `backend/victor_ai_bot/execution_capture/` and is intentionally lightweight and interpretable.

It persists:
- feature keys
- route/family/venue/lane/regime priors
- predictions
- realized outcomes
- quarantine state

It directly affects:
- admission
- drop policy
- confidence-to-size scaling
- competition suppression
- route quarantine

## Launch Modes

Supported launch modes:
- `V1_ONLY`
- `V1_PLUS_STABLE_ALPHA`
- `STAGED_MULTI_STRATEGY`
- `FULL_MULTI_STRATEGY`

Default rollout order:
1. `flash_arb`
2. `funding_arb`
3. `cex_cex_arb`
4. `liquidation_capture`
5. `mev_search`
6. `stat_arb`
7. `volatility_market_making`
8. `treasury_yield`

## Readiness gating

Families are only recommended or enabled when the system sees enough evidence from:
- telemetry sufficiency
- recent execution success
- route calibration quality
- degraded-state checks
- stage restrictions
- private-routing readiness where required

## Mobile/operator flow

The mobile operator surface now supports:
- launch mode selection in Setup
- a Launch Rollout card in Home
- explicit next-family recommendation
- blocked reasons
- enable-next-family and pause-family actions

## Compatibility

This remains additive:
- `execution_capture` stays the execution brain
- `fund_os` stays the controller
- treasury/risk/lifecycle/governance stay in force
- V1 remains protected by default
