# OMAR adaptive flash-loan risk budget

## Objective

This phase defines a bounded sizing controller for the autonomous learning loop:

`canonical decision → risk budget → flash-loan candidate sizes → profit-after-costs gate → governance/capital → execution → settled outcome → exact OMAR attribution`

OMAR may learn that a larger trade was superior, but only from **settled net economics** and only when the larger size remained inside authoritative risk/capital ceilings. This is an optimization objective, not a guarantee of profitability.

## Profit-after-costs authority

The learning objective must not use gross opportunity P&L as the final reward. The pre-trade economic model subtracts:

- flash-loan provider fee/premium
- gas
- slippage
- execution/relay fees
- internal-prime financing cost when applicable
- safety reserve

A trade that is gross-positive but net-negative after these costs is not a profitable learning example.

The existing Solidity executor remains the atomic repayment and token-denominated `minProfit` authority. Off-chain sizing must conservatively account for provider fees and gas; the contract must independently enforce repayment, deadline, spender/initiator constraints, and route-leg minimum outputs.

## Large profitable trades

The sizing objective is **largest eligible net profit**, not maximum leverage:

1. generate multiple size candidates from the existing safe-size curve/route analysis;
2. reject candidates above the configured maximum borrow;
3. reject candidates outside fresh `capital_engine_state()` availability/deployable/family authority;
4. reject candidates outside the loss budget or drawdown/kill-switch policy;
5. reject candidates that fail minimum net profit or net ROI;
6. among survivors, prefer the candidate with the best expected net profit after costs, using size as a secondary preference.

This creates a path for OMAR to learn when scaling is economically beneficial while preventing a wealth goal or aggressiveness setting from becoming an unbounded leverage instruction.

## Preference vs authority

Confidence, aggressiveness, and wealth-goal gap are contextual preference signals. They may shape a bounded risk budget, but cannot raise:

- governance ceilings;
- capital-engine authority;
- family allocation;
- configured maximum borrow;
- maximum loss;
- drawdown/kill-switch limits;
- provider/route safety constraints.

## Identity

Accepted sizing decisions require both `canonical_decision_id` and `correlation_id`. A deterministic `sizing_id` is derived from decision identity, correlation identity, route, provider, and selected size. `sizing_id` is attribution metadata; it never replaces canonical decision identity.

When the trade settles, the same canonical decision/correlation identity must be carried through execution and the canonical settled ledger into the exact OMAR learning observation.

## Learning reward

`learning_reward_from_settled_outcome()` rewards only truth-verified settled outcomes and uses realized net USD relative to expected net USD. An unverified outcome contributes zero learning reward.

The next integration gate should replace any generic/gross reward path for flash-loan sizing with this settled net-profit objective and prove the selected size and sizing identity survive the real production method chain.

## Rollout safety

This phase is a pure sizing/risk contract plus unit tests. It does not enable live trading, change the Solidity executor, or grant OMAR signing/capital/governance authority. Production integration remains gated by the existing runtime, governance, capital, execution, and settlement controls.
