# ADR-0004: Alpha Validation Gate + Probation Capital Staging

**Status:** Accepted (default posture)

## Context
Meta evolution (mutating strategies) before a proven edge leads to overfitting and capital churn.

## Decision
Mutation/evolution should be blocked until alpha is proven via conservative statistics:
- minimum number of trades
- win-rate and/or expected value above thresholds
- bounded drawdown behavior

Any new variant must enter **probation**:
- probation capital cap
- fixed number of probation trades
- graduation only after success thresholds

## Consequences
- ✅ Safe compounding and controlled exploration
- ✅ Operator can understand why capital moved
- ❌ Slower “innovation”, but vastly safer
