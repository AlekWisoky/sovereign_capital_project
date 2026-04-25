# ADR-0001: v1 Scope Locked to Flash-loan Atomic Arbitrage

**Status:** Accepted (v1 baseline)

## Context
The project supports many strategy families (CEX/DEX arb, funding capture, MEV, meta-evolution). Shipping all of them in one production release increases operator cognitive load and reduces auditability.

## Decision
For v1 production, we hard-lock scope to **flash-loan atomic arbitrage**.

## Consequences
- ✅ Clear explainability: every live trade belongs to the same strategy family.
- ✅ Faster hardening: latency optimization, slippage, and RPC reliability are solved once.
- ✅ Safer ops: fewer moving parts and fewer paths to silent drift.
- ❌ Other modules remain “experimental overlays” and must be explicitly enabled.

## Notes
The mobile UI still exposes Sandbox/Lab concepts, but mutation/evolution is expected to remain OFF until alpha is proven.
