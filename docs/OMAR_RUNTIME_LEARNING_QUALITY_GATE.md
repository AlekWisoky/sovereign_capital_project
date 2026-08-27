# OMAR Runtime Learning-Quality Gate — Phase 11

Phase 11 exposes the Phase 10 dataset-quality gate through the live OMAR runtime and makes that gate a prerequisite for learned live influence.

## Runtime contract

`OmarRuntime.learning_quality()` evaluates the durable `omar_real_outcome` event stream. The runtime-facing payload reports:

- observation count and unique-state coverage
- six-action coverage
- settlement-truth verification rate
- missing decision/correlation lineage
- duplicate learning identity
- invalid/non-finite rewards
- `live_influence_allowed`

`GET /api/omar/learning-quality` exposes the same contract for operators and monitoring.

## Influence rule

A recommendation that is already marked `trained=True` is converted to a neutral `UNTRAINED` recommendation unless the runtime quality gate is ready. This prevents an apparently trained policy from influencing live decisions when the accumulated evidence fails the structural quality requirements.

The gate does not authorize trades. Governance/admission, capital authority, and execution remain authoritative.

## Evidence boundary

Only the real-learning event stream emitted after canonical settled-outcome attribution is evaluated. A raw receipt, inferred PnL, or synthetic self-play episode cannot satisfy this production quality gate.

## Performance boundary

Passing the quality gate means the dataset is structurally usable. It does **not** prove profitability or superiority over the incumbent policy. Out-of-sample baseline evaluation remains a separate promotion gate.
