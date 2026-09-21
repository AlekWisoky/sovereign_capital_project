# Issue #40 — Reachability and mobile control-plane audit

## Audit basis

- Main baseline: `7ae9128d29e9fcba471249a788c51129c4aa335f` (PR #187 squash merge).
- Audit branch: `feat/issue-40-90-typed-surfaces-audit`.
- Generated system truth at the baseline reported 165 app routes, 161 HTTP routes excluding HEAD/OPTIONS, 340 backend test files, and 15 mobile test files.
- No runtime authority, signer, broadcast, or capital-mutation behavior is introduced by this audit branch.

## Production backend reachability

The current production runtime is **not yet independent of `runtime_legacy.py`**:

```text
server.py
  -> runtime_core.bootstrap.make_runtime_lifespan/build_runtime
  -> runtime_core.coordinator.RuntimeBundle / MultiRuntimeBundle
  -> runtime_legacy.py RuntimeBundle / MultiRuntimeBundle
  -> Runtime*Facade mixin hierarchy
```

Concrete source evidence:

- `backend/victor_ai_bot/runtime.py` re-exports `RuntimeBundle` and `MultiRuntimeBundle` from `runtime_core`.
- `backend/victor_ai_bot/runtime_core/bootstrap.py` imports those classes from `runtime_core.coordinator` and constructs them for the live app.
- `backend/victor_ai_bot/runtime_core/coordinator.py` currently imports the public runtime classes from `runtime_legacy.py`.
- `runtime_legacy.py` is therefore production-reachable through the normal boot path.
- The runtime facade modules are also production-reachable because `RuntimeBundle` is assembled from the facade mixins in `runtime_legacy.py`.

**Decision:** do not delete `runtime_legacy.py` or its facade mixins in this gate. Deleting them now would remove live runtime implementation, not dead code. The safe retirement gate is a future migration of `runtime_core.coordinator` to an independently constructed canonical runtime composition followed by a fresh reachability proof.

## API legacy reachability

`backend/victor_ai_bot/api.py` is a compatibility shell. It imports `api_legacy.get_runtime`, but the server no longer mounts `api_router`. Existing maintenance tests explicitly assert that:

- `api_router` owns no routes;
- `api_legacy.router` owns no routes;
- `server.py` does not include `api_router`;
- the public app has no routes whose endpoint module is `victor_ai_bot.api`.

**Decision:** `api_legacy.py` is not public route ownership and is not safe to delete solely from route inventory. Its remaining use is compatibility import surface. Retirement requires an import-consumer audit and removal/migration of those compatibility consumers first.

## Mobile control-plane wiring

The operator-facing mobile path is now explicitly layered:

```text
MainTabs
  -> canonical operator screens
  -> useCanonicalFeed / CommandCenterProvider
  -> api/canonical.ts + commandCenter/provider.ts
  -> api/canonicalContracts.ts
  -> typed endpoint + summaryContract identity
  -> backend canonical projection
```

The typed contract registry now covers:

### Canonical reads

- command-center snapshot, audit tail, explain
- engine state
- fund summary
- spread opportunities
- launch state and family detail
- XAI latest and decision detail
- reliability and KDS state
- risk live state
- execution quality
- service health
- capital explanation
- wealth goal

Each read records HTTP method, endpoint path, backend capability class, truth family, and read-model identity. Existing `SummaryReadContract` is reused; no duplicate summary envelope is introduced.

### Mutations

The registry explicitly records backend capability plus mobile authority class for:

- command-center control
- runtime start/stop
- settings and safety
- opportunity execution and simulation
- withdrawals / convert-withdraw / withdraw-all
- RPC preferences
- preset and chain selection
- meta apply
- wealth goal
- launch mode / enable / pause / revert / quarantine

Execution and capital-write mutations are marked as requiring backend live authority in addition to operator confirmation. This does not grant authority; it makes the client-side guard requirement explicit.

## Compatibility-only surfaces

- `/api/state` remains a compatibility read path used by older v2 screens/provider fallback.
- `mobile/src/api/ws.ts` remains reachable from v2 `DashScreen` and `TrackerScreen`; it is not dead solely because `wsSummary.ts` is the preferred command-center transport.
- `mobile/src/api/canonical.ts` remains the domain normalization layer, but its canonical operator reads now delegate to the typed contract adapters rather than bypassing them.
- `commandCenter/provider.ts` now routes command-center, engine, fund, execution-quality, risk, service-health, and control calls through `canonicalContracts.ts`. The legacy `/api/state` fallback remains explicitly isolated.

## Gate conclusion

This audit proves the current reachability boundary rather than pretending the remaining legacy runtime is dead.

- **#40 legacy deletion:** blocked by verified production reachability of `runtime_legacy.py` and facade mixins.
- **#40 API shell retirement:** route ownership is retired; compatibility import remains.
- **#90 typed mobile surface:** canonical reads and command-center control are now wired through the typed contract registry, with tests covering endpoint identity, method, truth-family/read-model identity, and mutation capability/authority metadata.
- **Next safe gate:** run the full CI gate on this branch, then perform the remaining endpoint inventory against the actual mobile screens and close only the compatibility paths that have a verified zero-consumer graph.
