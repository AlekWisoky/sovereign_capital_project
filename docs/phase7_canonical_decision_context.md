# Phase 7 — Canonical Decision Context & Intent Propagation

## Contract

```text
human intent
   + wealth objective
   + aggressiveness
   + AI recommendation
   + capital authority
   + latency context
          |
          v
canonical decision context
          |
          +--> decision_id + correlation_id
          |
          v
actual execution
          |
          v
settled canonical outcome
          |
          v
OMAR learning / policy update
```

## Invariants

1. `decision_id` identifies the decision instance. `correlation_id` groups the complete lifecycle across services/events.
2. The same lineage is copied to execution, settled-outcome, and learning records.
3. Human intent, wealth objective, aggressiveness, AI recommendation, capital authority, and latency are recorded as decision context; they do not bypass governance.
4. Capital authority is normalized from the existing `capital_engine_state()` contract. Internal prime, deployable bankroll, external borrow capacity, and family allocations remain separate facts.
5. Monetary values are serialized as exact decimal strings so large institutional-sized notional values do not pass through binary floating point.
6. External borrowing capacity is a decision input, not permission to borrow. Governance, route safety, provider liquidity, execution constraints, and configured caps remain authoritative.
7. A wealth goal is an objective for optimization/learning, not a promise to achieve a target or a reason to violate risk limits.
8. Latency is both an execution constraint and a learning feature: stale market data, decision latency, and deadline pressure must remain attributable to the decision.
9. OMAR learns from settled outcomes rather than simulated rewards being treated as production truth.

## Institutional capital model

The original V1 design remains compatible with this context model: a flash-loan strategy can use external capital atomically, while realized profit can accumulate in Treasury and later become internal prime capital for other strategy families.

The architecture therefore distinguishes:

- `internal_prime_wei`: capital actually controlled by the system/Treasury for owned-capital strategies.
- `deployable_bankroll_wei`: capital currently deployable under the capital engine.
- `external_borrow_capacity_wei`: capacity that may be available from external providers; it is not owned capital.
- `family_allocations_wei`: strategy-family-specific authority/caps.

The context supports very large amounts without imposing a software-level "small trade" assumption. Actual execution must still be bounded by governance, configured limits, provider liquidity, route liquidity, gas economics, and the atomic strategy's ability to settle profitably.

## Current implementation in this phase

- `canonical_decision_context.py` defines the immutable transport contract.
- `decision_context_bridge.py` creates the context at the decision boundary and provides stable execution/outcome/learning record envelopes.
- Tests verify exact monetary serialization, required IDs, actual capital-engine normalization, and identity propagation.

The next integration step is to call `build_decision_context()` from the canonical production decision path, persist the resulting context/lineage into the existing execution record, and require the settled-outcome adapter to resolve the same context before invoking OMAR learning. This phase intentionally does not grant OMAR independent execution authority.
