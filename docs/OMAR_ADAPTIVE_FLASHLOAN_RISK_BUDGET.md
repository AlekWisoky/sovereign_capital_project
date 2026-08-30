# OMAR adaptive flash-loan risk budget

## Purpose

Phase 8 establishes the sizing contract for a learning autonomous trading system without giving OMAR authority to approve capital, sign transactions, or bypass governance.

The sizing decision is:

`canonical decision -> bounded risk budget -> candidate flash-loan sizes -> net-profit-after-costs filter -> execution -> canonical settlement -> exact attribution -> OMAR learning`

## Profit objective

OMAR must learn against **settled net economics**, not headline/gross P&L.

The canonical pre-trade profitability model subtracts:

- flash-loan provider fee/premium
- gas
- slippage
- execution/relay fees
- internal-prime financing cost when applicable
- an explicit safety reserve

A candidate that is gross-profitable but not positive after these costs is not a profitable learning example and must not be promoted as one.

## Large-trade behavior

The target is not "always borrow more." The target is:

> choose the largest candidate that remains inside the hard capital/risk ceilings and still clears the net-profit and net-ROI floors.

This lets OMAR learn that larger size can be better **when marginal net economics remain favorable**, while preventing wealth goals or aggressiveness preferences from creating an uncapped leverage path.

Hard ceilings include governance permission, fresh `capital_engine_state()` authority, deployable/family capital, configured maximum borrow, maximum loss budget, drawdown/kill-switch state, and the provider/route constraints already enforced by execution capture.

Preference inputs (confidence, aggressiveness, wealth-goal gap) may alter the preferred risk budget only inside those ceilings. They cannot raise a hard ceiling.

## Canonical identity

Every accepted sizing decision requires both:

- `canonical_decision_id`
- `correlation_id`

The sizing layer derives a deterministic `sizing_id` from decision identity, correlation identity, route, provider, and selected size. Execution and settlement must preserve the canonical decision/correlation identity; the sizing ID is attribution metadata, not a replacement decision identity.

## Flash-loan contract boundary

The Solidity executor remains the final atomic repayment authority. The existing executor checks provider/initiator/in-flight context, route leg minimums, and repayment plus minimum profit before releasing profit. Off-chain sizing therefore cannot assume that a quote is executable merely because its expected P&L is positive.

The off-chain gate must use conservative provider fee/route-cost estimates, while the contract must continue to enforce the actual provider repayment amount and per-leg minimum outputs atomically.

Gas is an off-chain economic cost because the contract cannot know the final USD gas cost at decision time. It is therefore included in the profitability/risk budget before execution, while the contract's `minProfit` remains a token-denominated execution floor.

## Learning rule

`learning_reward_from_settled_outcome()` gives OMAR reward only from a truth-verified canonical settled outcome and uses realized net USD relative to expected net USD. Gross profit alone is intentionally insufficient.

This prevents the learner from reinforcing trades that looked profitable before gas, slippage, financing, or execution costs but were not actually profitable after settlement.

## Rollout boundary

This phase adds the sizing/risk contract and focused unit tests. It does **not** enable live trading, change the flash-loan executor, or grant OMAR execution authority. The next integration gate should connect this pure sizing contract to the existing `flashloan_sizing` path and prove that the selected size, sizing identity, actual execution record, settled outcome, and OMAR observation remain identical end-to-end.
