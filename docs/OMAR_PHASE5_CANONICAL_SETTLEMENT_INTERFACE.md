# OMAR Phase 5 — Canonical Settlement Interface

Phase 5 exposes the Phase 2 receipt-settlement ledger through one stable runtime read surface and makes the Phase 4 OMAR lifecycle bridge consume that surface.

## Contract

`RuntimeReceiptFacade.canonical_settled_outcome(...)` is the stable runtime interface.

It reads the existing `LedgerRepository` transaction journal and accepts only transactions with:

- `tx_type == "receipt_settlement"`
- a matching transaction lineage (`tx_hash`, canonical decision ID, correlation ID, or opportunity ID)

PnL rows, RPC receipts, runtime caches, and inferred settlement state are not substitutes for the canonical ledger transaction.

## Data flow

```text
real execution
    -> receipt finalization
    -> ReceiptService.synchronize_settlement_accounting()
    -> LedgerRepository treasury_ledger_transactions
    -> RuntimeReceiptFacade.canonical_settled_outcome()
    -> OMAR Phase 4 lifecycle bridge
    -> settled-outcome learning
```

## Safety properties

1. A receipt alone does not authorize learning.
2. A PnL row alone does not authorize learning.
3. Missing canonical settlement produces `None` and therefore no OMAR policy update.
4. The Phase 2 ledger remains the source of truth; Phase 5 is read-only.
5. OMAR does not gain execution, signing, governance, or capital-write authority.
6. Decision and correlation identifiers remain lineage metadata rather than learning-state features.

## Normalized learning surface

The interface normalizes the canonical transaction into a stable shape containing settlement identity, decision/correlation lineage, opportunity/route identity, expected and realized economics, gas, slippage, latency, truth verification, terminal profitability metadata, capital admission metadata, and the original ledger transaction.

## Rollout

Phase 5 is intentionally additive. Existing execution and accounting flows remain responsible for writing the canonical settlement transaction. OMAR only reads it after settlement is present.
