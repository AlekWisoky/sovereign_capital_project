# Migration notes — Fund OS layer

This pass is additive.

## What changed

- New backend packages:
  - `fund_os/`
  - `alpha_platform/`
  - `research_pipeline/`
  - `risk_engine/`
  - `alpha_marketplace/`
- New route surface:
  - `GET /api/fund/summary`
  - `GET /api/fund/research/candidates`
  - `POST /api/fund/research/candidates`
  - `POST /api/fund/research/promote`

## Compatibility

- Existing execution capture, treasury, strategy, telemetry, and command-center workflows are preserved.
- The new fund layer is summary-and-governance oriented; it does not bypass execution capture or capital policy.
- Alpha marketplace scaffolding is disabled by default.

## State

The new research pipeline and optional marketplace persist under `data/research/` and `data/marketplace/`.
They remain local-dev friendly and easy to inspect.

## Rollout

Recommended rollout:

1. Use `/api/fund/summary` in observe mode first.
2. Create sandbox candidates only.
3. Promote through the research pipeline using explicit review decisions.
4. Keep stage at `internal_capital` until scorecards and risk summaries are stable.
