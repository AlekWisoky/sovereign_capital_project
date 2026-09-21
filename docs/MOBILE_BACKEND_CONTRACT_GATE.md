# Mobile ↔ Backend Canonical Contract Gate

Status: **Phase A / contract freeze — in progress**
Baseline: `main` @ `0278b8ba3d89373f2307b28ec1faa26e2308a7e6`
Scope: Issues #40 and #90 only. This document is a contract audit, not a new execution path.

## Authority rules

1. Backend projections are the source of truth. Mobile state is cache/preferences only.
2. A read must consume a canonical backend projection; it must not reconstruct capital/economic truth from UI state.
3. A mutation must call the real backend command and satisfy its backend capability/auth boundary.
4. Execution, withdrawal, and launch-posture changes require the mobile guarded-mutation boundary and backend authorization; UI state alone never grants authority.
5. Live authority remains controlled by Issue #89. This contract gate does not enable signing, broadcast, or capital movement.
6. WebSocket data is supplemental; canonical polling/read models remain authoritative.

## Verified contract inventory

| Surface | Method | Backend auth/capability | Mobile status | Canonical source |
|---|---|---|---|---|
| `/health` | GET | none | wrapper exists, response generic | `backend/victor_ai_bot/api_routes/runtime_routes.py` |
| `/api/deploy/info` | GET | none | wrapper exists, response generic | `backend/victor_ai_bot/api_routes/runtime_routes.py` |
| `/api/commandcenter/snapshot` | GET | none | wrapper exists through generic API layer | `backend/victor_ai_bot/api_routes/command_center_routes.py` |
| `/api/commandcenter/control` | POST | ADMIN_WRITE | guarded command path exists; response generic | `backend/victor_ai_bot/api_routes/command_center_routes.py` |
| `/api/commandcenter/audit/tail` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/command_center_routes.py` |
| `/api/launch/state` | GET | none | wrapper exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/mode` | POST | ADMIN_WRITE | guarded mutation exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/enable-next` | POST | ADMIN_WRITE | guarded mutation exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/pause-family` | POST | ADMIN_WRITE | guarded mutation exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/revert-family` | POST | ADMIN_WRITE | guarded mutation exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/quarantine-family` | POST | ADMIN_WRITE | guarded mutation exists | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/launch/family/{family}` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/launch_routes.py` |
| `/api/fund/summary` | GET | none | wrapper exists; response generic | `backend/victor_ai_bot/api_routes/fund_routes.py` |
| `/api/wealth/goal` | GET | none | wrapper exists; response generic | `backend/victor_ai_bot/api_routes/wealth.py` |
| `/api/wealth/goal` | POST | ADMIN_WRITE | guarded settings path exists | `backend/victor_ai_bot/api_routes/wealth.py` |
| `/api/xai/latest` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/intelligence_routes.py` |
| `/api/xai/decision/{decision_id}` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/intelligence_routes.py` |
| `/api/reliability/state` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/intelligence_routes.py` |
| `/api/kds/state` | GET | none | needs canonical typed adapter | `backend/victor_ai_bot/api_routes/intelligence_routes.py` |
| `/api/risk/live-state` | GET | none | backend exists; mobile contract needs formalization | `backend/victor_ai_bot/api_routes/risk_routes.py` |

## Canonical read-model envelope

The backend already emits `summaryContract` for several operator projections. Its stable contract is defined by:

- `contractVersion`
- `truthFamily`
- `readModel`
- `synthesized`
- `capitalContractVersion`
- `capitalPolicyVersion`
- `stateContract`
- `sourceContracts`

Source: `backend/victor_ai_bot/runtime_services/summary_read_contract.py`.

Mobile should type this envelope once and compose domain-specific payload types around it. Do not create screen-specific copies of the envelope.

## Capability boundary

Backend capabilities are defined in `backend/victor_ai_bot/security/permissions.py`:

- `admin:read`
- `admin:write`
- `execute`
- `governance`
- `treasury:write`
- `evolution:write`

`backend/victor_ai_bot/security/auth.py` enforces the admin-key boundary and separately blocks EXECUTE in public mode unless the explicit public-broadcast override/confirmation is satisfied.

Mobile currently uses `mobile/src/api/mutationGuard.ts` and `mobile/src/api/guardedMutations.ts`. The guard fails closed for operator role, lock state, admin-key presence, backend reachability, explicit confirmation, and backend live-authority state for execution/withdrawal.

**Contract-gap:** `backendLiveAuthority` is currently a coarse mobile-side decision. Phase A must map individual mutations to the backend capability semantics and canonical backend response/state rather than treating the boolean as the complete authority model.

## Typed-contract gap

`mobile/src/api/client.ts` still exposes a large surface through `JsonObject`, `unknown`, and generic `Record<string, unknown>` request bodies. `mobile/src/utils/types.ts` contains only a small runtime/opportunity model.

This is the demonstrated #90 implementation gap. The next code slice should:

1. add one shared typed summary/read-model envelope;
2. add typed adapters for the verified contract inventory above;
3. preserve existing low-level wrappers for compatibility until callers migrate;
4. add contract tests for path, HTTP method, auth header/capability class, and required response identity;
5. only then consolidate screens/providers around those adapters.

No endpoint should be invented to satisfy a UI design.

## Explicitly out of scope for this gate

- live signing/broadcast/capital activation;
- replacing the canonical settlement ledger;
- deleting legacy/facade runtime modules without reachability evidence;
- changing UpCloud/Caddy deployment already verified on `0278b8ba...`;
- rebuilding the mobile visual layer before contracts are stable.

## Gate exit criteria

Phase A is complete only when the contract inventory is backed by focused tests and the typed adapters consume the actual backend projections. Then proceed to #90 phases B–G and the #40 reachability/control-plane audit. Issue #89 remains a separate final authority gate.
