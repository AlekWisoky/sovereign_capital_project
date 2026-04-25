# ADR-0008: Multi-grader Design

## Status
Accepted

## Decision
Use multiple conservative graders (schema, policy, capital, profit, risk, latency) combined by weighted sum.

## Rationale
A single scalar reward is too easy to game. Multi-grader scoring keeps safety and policy compliance load-bearing.

## Consequences
- integer-only scoring
- explicit pass/fail reasons
- weights configurable but defaults conservative
