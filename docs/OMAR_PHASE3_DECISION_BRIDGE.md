# OMAR Phase 3 — Decision Bridge

Phase 3 establishes the production boundary between learned OMAR recommendations and the existing decision/execution stack.

## Authority flow

`market/signals -> decision engine -> OMAR bounded influence -> GMAO/risk -> execution -> canonical outcome -> OMAR learning`

OMAR does not sign transactions, choose a governance bypass, or directly execute trades.

## Learning context

The OMAR state is built from stable economic and operational features:

- margin and gas conditions
- decision success estimate
- drawdown and wealth-goal gap
- execution realism and stability
- volatility and route complexity
- internal-prime economics when supplied by the capital layer

Prime identifiers and correlation identifiers are not learning features.

## Internal prime semantics

The internal prime/capital source can change the economics of a decision through availability, deployable capacity, and financing cost. Those economic dimensions may influence learning state buckets. A raw prime identifier must remain lineage metadata so the policy generalizes across prime instances.

The current repository does not expose a canonical `internal_prime` field/source by that exact name. Phase 3 therefore recognizes the semantic contract (`capital_source`, `prime_source`, availability, capacity ratio, and cost) without inventing a fake upstream authority. The actual capital subsystem remains the source of truth.

## Correlation semantics

A correlation/decision identifier links:

`decision -> execution attempt -> transaction/fill -> canonical outcome -> learning update`

It must be retained in audit and outcome metadata but excluded from the policy state key. This prevents every trade from becoming a unique learning state.

## Safety boundary

OMAR can:

- veto a candidate through its learned defensive action
- reduce position size
- select a bounded gas preference

OMAR cannot:

- bypass GMAO/governance
- increase the decision engine's size beyond its approved amount
- sign or submit transactions
- treat a transaction receipt alone as proof of economic success
