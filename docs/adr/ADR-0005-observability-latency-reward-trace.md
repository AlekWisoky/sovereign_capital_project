# ADR-0005: Observability (Latency p50/p90/p99 + Reward Trace)

**Status:** Accepted

## Context
In DeFi execution, profitability is constrained by latency, MEV competitiveness, and execution reliability. RL systems additionally need reward attribution to be explainable.

## Decision
Add an observability layer that logs:
- loop timing percentiles (p50/p90/p99)
- execution timing percentiles (p50/p90/p99)
- submit→receipt percentiles (p50/p90/p99)
- reward component traces per finalized trade

The observability outputs MUST NOT influence decisions unless explicitly modeled and audited.

## Consequences
- ✅ Better ops: identify RPC bottlenecks, gas spikes, MEV timing issues
- ✅ Better learning: reward attribution visible per decision
- ✅ Better safety: anomaly breakers can enter Defensive Mode
