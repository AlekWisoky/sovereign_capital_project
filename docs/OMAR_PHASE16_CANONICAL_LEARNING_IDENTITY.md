# OMAR Phase 16 — Canonical Learning Identity

## Contract

The canonical decision identity is now the identity consumed by the OMAR real-learning record:

`canonical decision ID -> correlation ID -> execution ID -> canonical settled outcome ID -> exact action -> policy update`

A transaction hash, opportunity ID, route ID, or correlation ID is not allowed to substitute for the originating canonical decision ID.

## Learning behavior

`OmarRealLearner.observe()` fails closed when the settled transition does not carry a canonical decision identity. Accepted learning events persist the canonical decision ID and correlation ID alongside the state key, action, reward, and outcome payload.

The runtime training-log compatibility path also requires a canonical decision ID. Historical rows that contain only a transaction hash are ignored rather than silently re-identifying the trade as a different decision.

## Authority boundaries

- Canonical settled-outcome ledger remains the outcome authority.
- `capital_engine_state()` remains the capital-authority input.
- Governance/admission and ExecutionService remain authoritative for execution.
- OMAR remains a learning/recommendation subsystem and cannot sign, submit, approve capital, or bypass governance.

## Latency boundary

The existing `LatencyProfiler` is an observability engine. It measures execution-stage and end-to-end latency with rolling p50/p90/p99 statistics. It must not become an alternate execution or governance authority.

Latency is nevertheless economically relevant to learning: the canonical OMAR reward already penalizes realized execution latency, alongside slippage, failed execution, and unverified outcome truth. This lets the learner prefer actions/routes that perform well under real delivery conditions without making raw latency a standalone authorization rule.

This separation is intentional:

- **execution path:** latency instrumentation measures and reports delivery speed;
- **learning path:** settled latency contributes to the realized reward signal;
- **authority path:** governance and capital controls remain unchanged;
- **decision identity:** latency never changes or replaces the canonical decision ID.
