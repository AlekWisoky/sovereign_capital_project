# x∆v — Sovereign Capital Fund OS

This pass formalizes the platform as a lightweight hedge-fund operating system with six explicit layers:

- Research Layer
- Strategy Layer
- Execution Layer
- Capital Layer
- Risk Layer
- Operator Layer

## Research layer

The research pipeline lives in `backend/victor_ai_bot/research_pipeline/` and persists candidate ideas through:

`sandbox -> paper -> shadow_live -> capped_live -> production -> degraded -> retired`

Candidates carry origin metadata (`human`, `ai`, `hybrid`, `marketplace`), owner/reviewer information, thesis text, review history, and promotion history.

## Alpha platform

The alpha platform registry in `backend/victor_ai_bot/alpha_platform/` classifies families by alpha type, holding horizon, liquidity sensitivity, execution sensitivity, and regime preference.

This metadata is consumed by fund summaries and future allocation/risk logic.

## Risk + capital

The fund service combines:

- treasury capital state
- family scorecards
- family covariance penalties
- engine state
- research throughput

into a single fund health summary exposed by `/api/fund/summary`.

The risk layer uses explicit, interpretable components:

- drawdown
- family concentration
- covariance concentration
- utilization

and maps them into contraction controls.

## Fund stage model

`backend/victor_ai_bot/fund_os/fund_stage.py` defines safe defaults for:

- `internal_capital`
- `pilot_capital`
- `friends_family`
- `private_fund`
- `institutional_scale`

Each stage sets deployable-capital ceilings, experimental-capital share, family/engine concentration constraints, and operator scope.

## Governance and proprietary controls

The fund transformation introduces lightweight proprietary-asset controls:

- provenance helpers
- confidentiality classes
- governance audit log for fund actions
- optional internal alpha marketplace scaffolding, disabled by default

## Compatibility

This layer is additive.

It does not bypass:

- execution capture
- engine governance
- treasury/capital policy
- strategy lifecycle controls
- fail-closed safety

It adds an institutional architecture and summary layer on top of the existing money loop.
