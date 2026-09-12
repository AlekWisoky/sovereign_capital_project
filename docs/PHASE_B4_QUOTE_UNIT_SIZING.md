# Phase B.4 — raw-unit / quote-time sizing enforcement

Phase B.4 closes the economic-to-execution unit boundary left by the institutional sizing contract and Phase B.2 kernel.

## Contract

1. Institutional sizing remains expressed in USD economic notional.
2. The final quote supplies the asset USD price and token decimals.
3. The approved USD notional is converted to raw units using the final quote.
4. Conversion floors raw units so the execution amount cannot exceed the approved economic notional at that quote.
5. A configured raw-unit hard cap is enforced after conversion; the economic notional is re-valued from the capped raw amount.
6. Missing, zero, negative, non-finite, or malformed quote inputs fail closed.
7. Without a final quote, the Phase B.2 kernel continues to return no raw amount; this preserves the existing deferral until execution-time quoting is available.

## Authority boundary

The quote-unit converter is pure. It does not fetch market data, mutate governance, admission, capital, execution, settlement, or live-authority state. It does not create a new sizing identity. `sizing_id` remains the deterministic identity for the sizing decision.

## Production integration requirement

The execution path must supply the actual final/requote quote to this boundary before calldata construction. The converter must never be fed a stale pre-sizing quote merely to satisfy the interface. The next integration gate is an end-to-end test proving:

`approved_notional_usd -> final quote -> raw amount -> calldata/execution amount`

while preserving the canonical decision/execution lineage and existing hard safety gates.
