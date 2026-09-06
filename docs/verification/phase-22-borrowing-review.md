# Phase 22 borrowing / capital-demand review

This verification note records the reviewed production contracts for borrow sizing and capital demand.

- `capital_demand.py` is the canonical structured demand contract: denomination/decimals, capacity freshness, provenance, expiry, worst-case exposure, strategy budget consumption, and family-target resolution are validated before demand is considered valid.
- `rl_policy.py` exposes `borrow_mult` as a learned execution knob alongside `size_mult` and `gas_mode`; the policy action space is persisted and backward-compatible.
- `flashloan_sizing.py` consumes treasury governance, wealth-goal state, drawdown/kill-switch state, provider limits, family targets, route viability, slippage, latency decay, and adversarial fragility before selecting a size/borrow multiplier.
- `execution.py` applies the sizing decision at the real execution boundary and re-quotes before attempted execution when borrow/size scaling changes the route.
- Treasury and internal-prime borrow-cost modules account for borrowing economics rather than treating borrowed capital as free.

The Linux CI gate remains authoritative for final verification; this file intentionally does not claim a green gate by itself.
