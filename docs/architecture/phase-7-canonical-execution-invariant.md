# Phase 7 — Canonical Execution Invariant

## Purpose

Phase 7 makes decision/execution identity a hard production invariant rather than an optional OMAR feature.

The production auto-trading path is now required to follow:

```text
_tick
  -> scan
  -> canonical decision
  -> canonical decision ID + correlation ID
  -> capital/admission + governance
  -> execution wrapper
  -> execution record carrying lineage
  -> Phase 2 canonical settled outcome
  -> exact lineage resolution
  -> OMAR learning input
```

## The critical change

The historical `brain_mode=off` auto-dispatch path could select the highest-profit executable opportunity directly and call execution with `decision=None`.

That path is no longer allowed.

`RuntimeAutoQueueFacade._maybe_dispatch_auto_trade()` now requires:

1. a decision object;
2. `decision.action == "trade"`;
3. the selected opportunity must come from the canonical decision portfolio/opportunity ID;
4. `require_canonical_execution_context()` must resolve and validate both canonical decision ID and correlation ID;
5. only then can the execution task be created.

`brain_mode=off` therefore still means the existing DecisionEngine remains the decision authority; it does **not** mean "skip the decision object".

## OMAR relationship

OMAR remains optional for execution authority. When OMAR is disabled, the canonical DecisionEngine decision still creates the required identity and can proceed through governance and execution.

When OMAR is enabled, it can modify/veto the already-selected decision within its bounded policy authority, after which the same invariant is re-checked.

OMAR therefore remains a learning subsystem, not a hidden execution prerequisite.

## Settlement and learning

A receipt is not itself considered a learning outcome. The learning boundary consumes the Phase 2 `receipt_settlement` transaction through the stable canonical settlement interface.

The settled row must resolve the same:

- `decision_id`
- `correlation_id`
- `opportunity_id`

before it can become an OMAR learning input.

## Regression coverage

`backend/tests/test_runtime_canonical_execution_lifecycle.py` walks the production runtime orchestration through the scan, decision, capital/admission, governance, execution wrapper, execution identity, canonical ledger settlement, lineage resolution, and OMAR outcome-learning boundary.

`backend/tests/test_runtime_production_method_chain.py` additionally asserts that `brain_mode=off` cannot silently fall back to the legacy best-candidate execution path.
