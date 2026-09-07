# OMAR Phase 7 — Human control and wealth-goal contract

Human input is a first-class **decision context**, not a second authority system.

## Contract

`human intent -> canonical decision context -> OMAR recommendation -> governance -> execution`

The context may include:

- aggressiveness mode (`conservative`, `balanced`, `aggressive`)
- desired wealth goal amount
- desired wealth goal timeframe
- AI recommendation provenance

These values can influence policy features and decision interpretation, but they do not authorize capital movement, signing, governance bypass, or execution.

## Learning boundary

Stable identity remains separate from features:

- `decision_id`, `correlation_id`, execution identity, and outcome identity are lineage fields.
- Human intent is normalized into bounded learning features.
- AI recommendation identifiers are provenance/lineage metadata, not learning-state keys.

## Latency boundary

Human-context enrichment is optional and must be cheap/non-blocking. Missing or malformed values normalize to safe defaults rather than delaying execution.

## Wealth goal

The wealth goal is an optimization context, not a promise of return. Goal progress is bounded to `[-1, 1]` before entering learning features. Governance/risk constraints remain authoritative over any goal-driven preference.

## Safety

OMAR remains advisory/meta-decision authority only. GMAO/risk admission and the existing execution authority remain unchanged.
