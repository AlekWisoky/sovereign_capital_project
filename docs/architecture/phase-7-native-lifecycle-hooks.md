# Phase 7 — Native OMAR lifecycle hooks

Phase 7 replaces the Phase 6 production monkey-patching bridge with explicit native lifecycle calls at the canonical runtime boundaries.

## Native boundaries

1. **Decision** — after candidate selection and before execution, the runtime calls the native decision hook. The hook establishes/preserves canonical decision ID + correlation ID. This identity exists whether OMAR is enabled or disabled.
2. **Execution** — after canonical execution capture/bookkeeping, the execution service calls the native execution hook. The exact decision/opportunity/result lineage is carried into the execution record without creating a second execution authority.
3. **Settlement** — after the canonical settled-outcome interface resolves a settled ledger record, the receipt lifecycle calls the native settlement hook. OMAR learns only from a settled canonical ledger outcome whose decision/correlation lineage matches the originating opportunity.

## Authority and safety

OMAR remains a learning/meta-decision subsystem. GMAO/risk governance, capital authority, signing and transaction execution remain authoritative. Native hooks are observational/learning hooks and cannot approve capital, sign transactions, or bypass governance.

## Phase 6 regression coverage

The Phase 6 production-method-chain tests remain in place as regression guards. Phase 7 adds native-hook tests that exercise the same boundaries without calling `install_production_lineage_bridge()` or mutating runtime classes.

## Migration rule

`production_lineage_bridge.py` is retained for historical compatibility and Phase 6 regression coverage, but production startup must not install it. The canonical production path is explicit method calls into `omar.native_hooks`.
