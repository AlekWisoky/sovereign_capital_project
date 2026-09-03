# Phase 9 — Phase 7 Context → Canonical Execution → Settled Learning

Phase 9 makes the Phase 7 decision context a first-class attribution payload across the production learning loop.

## Contract

`decision boundary`
→ Phase 7 context snapshot
→ canonical execution identity
→ execution record
→ real fill / P&L / gas / slippage / latency
→ canonical settled ledger
→ exact decision + correlation + execution + settlement + action lineage
→ OMAR attribution
→ policy update

Phase 7 context includes:

- operator control mode and aggressiveness
- brain mode and risk multiplier
- desired wealth goal
- AI recommendation / selected action
- runtime capital, drawdown, kill-switch, and treasury state
- chain/regime and delivery mode
- realized execution latency

## Authority boundary

Phase 7 context is observational and attributional. It does not authorize capital or execution.

The existing authority ordering remains:

`AI proposes → Capital validates → Execution executes`

GMAO/governance and internal-prime/capital authority remain authoritative.

## Learning fail-closed rule

OMAR may update policy only when the settled record resolves all of:

- `decision_id`
- `correlation_id`
- `execution_id`
- `settlement_id`
- exact `action`

A missing action is now explicitly `missing_action`; no policy update is permitted.

## Latency rule

Latency is a realized delivery feature for learning and attribution. The Phase 7 snapshot is captured once, execution identity is attached before bookkeeping, and context persistence occurs after canonical execution bookkeeping. This avoids adding a second database write to the transaction-submission critical path.
