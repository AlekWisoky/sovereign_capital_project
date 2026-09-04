# Phase 7 — Native OMAR lifecycle hooks

Phase 7 replaces the Phase 6 production monkey-patching bridge with explicit lifecycle hook calls at the canonical runtime boundaries.

1. Decision boundary: establish canonical decision/correlation identity and notify OMAR.
2. Execution boundary: after canonical execution capture, invoke the native execution hook with the same opportunity, decision and result.
3. Settlement boundary: after the canonical settled-outcome interface resolves a settled ledger record, invoke the native settlement hook. OMAR learns only from canonical settled outcomes.

The hooks are non-authoritative: GMAO/risk, capital authority, signing and execution remain outside OMAR.

Phase 6 integration tests remain regression guards for the production method chain. Phase 7 tests additionally assert native hook calls without installing a production monkey patch.

The Phase 6 production_lineage_bridge.py remains available for historical/regression compatibility, but production runtime integration uses explicit hook calls instead of mutating runtime classes.
