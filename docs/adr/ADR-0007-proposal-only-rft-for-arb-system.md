# ADR-0007: Proposal-only RFT for Arb System

## Status
Accepted

## Decision
Add a deterministic, proposal-only RFT layer that exports episodes and scores candidate proposals, but never executes trades directly.

## Rationale
This improves learning quality and post-trade analysis while preserving the hard boundary that the capital engine and execution path remain authoritative.

## Consequences
- additive modules only
- safe defaults OFF
- auditability for exports/scoring
