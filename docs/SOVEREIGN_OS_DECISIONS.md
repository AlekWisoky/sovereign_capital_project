# Sovereign Capital OS Architectural Decisions

Append-only. Do not rewrite a prior decision silently. Supersede with a new ADR referencing the old one.

## ADR-001
- DATE: 2026-08-13
- DECISION: Architecture C is the approved capital-demand architecture.
- STATUS: ACCEPTED; CONTRACT READY, RUNTIME UNWIRED
- RATIONALE: DecisionEngine needs capital semantics before portfolio selection; the selector's fail-closed behavior is correct and the missing piece is authoritative composition.
- ALTERNATIVES REJECTED: Selector inference, removing capital gates, route notional as treasury capital.
- DO NOT REGRESS: Do not wire ambiguous scalar demand or bypass the selector contract.
- DEPENDENCIES: Treasury denomination, conversion, capacity, exposure, provenance, freshness, plan identity, and focused tests.
- EVIDENCE: `capital_demand.py`, Architecture C contract tests, `decision_engine.py`, `portfolio_optimizer.py`; branch `architecture-c-contract-tests`, commit `314382c`.

## ADR-002
- DATE: 2026-08-13
- DECISION: Flash-loan arbitrage is the only initial live-eligible strategy.
- STATUS: ACCEPTED; CONTRACT-LEVEL POLICY ONLY
- RATIONALE: Limit live unknowns while evidence accumulates.
- ALTERNATIVES REJECTED: Launch every implemented family or let AI activate any available family.
- DO NOT REGRESS: Code existence, recommendation, or source reachability is not readiness.
- DEPENDENCIES: Realized sample, risk-adjusted performance, execution stability, capacity, capital truth, recovery, replay, governance, rollout readiness.
- EVIDENCE: `live_eligible_family()` and policy tests at `314382c`.

## ADR-003
- DATE: 2026-08-13
- DECISION: Borrowed principal is not internal treasury capital.
- STATUS: ACCEPTED
- RATIONALE: Flashloan notional, internal commitment, gas, provider capacity, worst-case exposure, and strategy budget are distinct.
- ALTERNATIVES REJECTED: `capital_required_wei` from borrow amount; treating all quantities as wei.
- DO NOT REGRESS: Preserve typed dimensions and explicit denomination.
- DEPENDENCIES: CapitalDemand composition and treasury authority.
- EVIDENCE: CapitalDemand seven-dimension contract tests at `314382c`.

## ADR-004
- DATE: 2026-08-13
- DECISION: Selector scalar means strategy-budget consumption in explicit treasury denomination.
- STATUS: ACCEPTED; UNWIRED
- RATIONALE: A scalar is safe only when its meaning and denomination are declared.
- ALTERNATIVES REJECTED: Route amount, borrowed principal, raw wei, USD x `10^18`, internal commitment.
- DO NOT REGRESS: Invalid, stale, conflicting, zero, or mismatched demand must fail closed.
- DEPENDENCIES: Valid CapitalDemand and final-plan synchronization.
- EVIDENCE: `selector_scalar()`, projection/composition tests at `314382c`.

## ADR-005
- DATE: 2026-08-13
- DECISION: Wealth Goals constrain pacing, allocation, sizing, compounding, and risk posture but never authorize a trade.
- STATUS: ACCEPTED; PARTIALLY PROVEN
- RATIONALE: A target cannot establish profitability, capital truth, risk, governance, or readiness.
- ALTERNATIVES REJECTED: Goal urgency as a gate bypass or automatic risk escalation.
- DO NOT REGRESS: Goals and aggressiveness may modify only valid, safety-approved demand.
- DEPENDENCIES: Treasury, drawdown, capacity, correlation, governance, rollout, and execution quality.
- EVIDENCE: Wealth Goal docs/service and Architecture C policy tests at `314382c`.

## ADR-006
- DATE: 2026-08-13
- DECISION: AI recommendations cannot bypass governance/readiness.
- STATUS: ACCEPTED; CONTRACT-LEVEL ONLY
- RATIONALE: Ranking confidence is not operational authority.
- ALTERNATIVES REJECTED: Silent AI activation or bypass of Phase A policy.
- DO NOT REGRESS: AI may rank/recommend only.
- DEPENDENCIES: Explicit user mode, readiness, governance, and rollout authority.
- EVIDENCE: AI-managed policy test at `314382c`.

## ADR-007
- DATE: 2026-08-13
- DECISION: Latency is an economic decision variable, not merely telemetry.
- STATUS: ACCEPTED; NOT IMPLEMENTED
- RATIONALE: Opportunity freshness and execution delay change realized economics.
- ALTERNATIVES REJECTED: Dashboard-only timing or ignoring quote age.
- DO NOT REGRESS: Preserve current instrumentation while adding decision authority safely.
- DEPENDENCIES: Freshness horizon, remaining-latency model, deterioration model, empirical budgets, durable trace.
- EVIDENCE: `latency_profiler.py` and documented gaps; latest state branch `314382c`.

## ADR-008
- DATE: 2026-08-13
- DECISION: Settlement consumes authoritative PnL, not caller-controlled realized values.
- STATUS: ACCEPTED; UNWIRED
- RATIONALE: Receipt/event truth must control accounting, treasury, learning, and compounding.
- ALTERNATIVES REJECTED: Trust supplied `realized_after` or contradictory fixture values.
- DO NOT REGRESS: Reconcile `gasUsed * effectiveGasPrice`, denomination, and decoded profit before settlement.
- DEPENDENCIES: Persisted PnL authority and settlement integration tests.
- EVIDENCE: Authority invariant tests and current ReceiptService seam at `314382c`.

## ADR-009
- DATE: 2026-08-13
- DECISION: Missing, stale, contradictory, ambiguous, non-authoritative, or unreconciled capital truth fails closed.
- STATUS: ACCEPTED
- RATIONALE: Capital safety and accounting integrity outrank throughput.
- ALTERNATIVES REJECTED: Best-effort inference, zero defaults, or continue under conflict.
- DO NOT REGRESS: Ambiguity means no trade.
- DEPENDENCIES: Every capital, risk, governance, rollout, and execution boundary.
- EVIDENCE: CapitalDemand validation and selector behavior at `314382c`.

## ADR-010
- DATE: 2026-08-13
- DECISION: Durable project memory is version-controlled documentation, never runtime authorization.
- STATUS: ACCEPTED; DOCUMENTATION COMMIT
- RATIONALE: Workspace loss must not erase architectural context, proof status, blockers, or resume point.
- ALTERNATIVES REJECTED: External workspace memory as source of truth.
- DO NOT REGRESS: Update state/changelog after meaningful authorized milestones; never claim documentation authorizes trading.
- DEPENDENCIES: Repository review discipline and actual test records.
- EVIDENCE: This four-file memory layer, branch `architecture-c-contract-tests`, source baseline `314382c`.
