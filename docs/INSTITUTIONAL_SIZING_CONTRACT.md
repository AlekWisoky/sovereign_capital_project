# Institutional sizing contract — Issue #94 Phase 1

This slice creates the canonical input boundary for institutional sizing. It intentionally does **not** change the existing trade-size calculation or enable live authority.

## Authority map

| Domain | Existing source | Contract role | Authority |
|---|---|---|---|
| Requested/base notional | `CapitalAdmissionService` + opportunity/unit economics | requested economic value | sizing input |
| Liquidity/depth | `execution_capture` envelope/route plan/flashloan resilience | executable capacity constraints | execution observation |
| Economics | execution-capture scoring + profitability contract | expected net economics | decision/sizing input |
| Latency | endpoint-quality pressure + pipeline latency + envelope half-life | edge-decay/execution constraint | advisory/decision input |
| Treasury | `capital_engine_state()` / capital-truth summary | deployable/reserve/capital context | capital authority |
| Internal Prime | `internal_prime_state()` | capacity, utilization, reserved collateral, family exposure | capital authority |
| Wealth goal | `wealth_goal_state()` | commitment %, aggressiveness cap, drawdown/time horizon | bounded policy input |
| Governance | capital admission / hard stops / live authority | permission boundary | governance authority |
| Settlement | canonical settled outcome | realized economics/calibration evidence only | economic truth |

## Unit boundary

`InstitutionalSizingContract` accepts USD values only where a USD economic value is explicitly available. Raw `wei` borrow controls remain separate integer fields. The contract deliberately refuses to infer USD from a raw wei value.

The later quote-time sizing slice must convert a USD target to raw asset units using the final quote. That conversion is execution-time economics, not a contract-level guess.

## V1 authority

The contract does not grant execution permission. `live_authority`, governance admission, and hard safety controls remain separate. V1 real-capital authority remains `flash_arb` only and Issue #89 remains the live-authority gate.

## Candidate institutional tiers

These are design targets only and remain disabled until governance/live-authority explicitly activates them:

- controlled_250k — $250,000
- controlled_500k — $500,000
- institutional_1m — $1,000,000
- institutional_2_5m — $2,500,000
- institutional_5m — $5,000,000

These tier values are metadata/design targets. They are **not** a global ceiling on provider-backed flash-loan principal. Actual executable size remains the intersection of provider/asset availability, route and pool depth, slippage/requote economics, governance, risk, and capital-authority constraints.

No existing configured borrow amount is replaced by these values.

## Provider capacity boundary

When an authoritative provider/asset capacity observation is available, it enters sizing as `liquidity.provider_capacity_usd` and is an ordinary hard constraint. It does not create a new capital authority, and missing provider capacity must not be replaced with a guessed fixed dollar ceiling.

## Settlement rule

Canonical settlement is not an input that authorizes a trade. It supplies verified realized economics and lineage for later calibration/learning. A settlement record can therefore be carried by the contract without becoming a competing execution authority.

## Next slice

After this contract is reviewed and tested, the existing V1 sizing kernel consumes it downstream of governance/admission, preserving hard caps, liquidity/depth and Internal Prime constraints, while keeping `flash_arb` as the only real-capital family. Final quote/requote remains the execution-time economics boundary.
