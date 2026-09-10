# Mobile ↔ Backend Contract V1

Status: implementation contract for the operator mobile surface.

## Authority rules

- Backend read models are authoritative. Mobile state is cache/UI preference only.
- A mobile screen must not calculate or invent capital truth.
- Mutations are capability-checked backend commands.
- Live-authority changes are never convenience toggles.
- V1 capital execution is `flash_arb` only; future families remain observe-only/shadow.
- `decision_id` is the only authoritative trade-decision identity and must remain visible through execution, receipt, settlement, and learning.
- OMAR is recommendation/learning only and cannot independently grant execution authority.

## Read contracts

| Surface | Method | Endpoint | Mobile role |
|---|---|---|---|
| Health | GET | `/health` | service health |
| Deployment | GET | `/api/deploy/info` | version/branch/mode evidence |
| Command Center | GET | `/api/commandcenter/snapshot` | canonical system/capital projection |
| Command audit | GET | `/api/commandcenter/audit/tail` | operator history |
| Fund ledger | GET | `/api/fund/ledger` | settled transaction history |
| Fund summary | GET | `/api/fund/summary` | capital/fund truth |
| Wealth goal | GET | `/api/wealth/goal` | goal/trajectory |
| XAI latest | GET | `/api/xai/latest` | current explanation |
| XAI decision | GET | `/api/xai/decision/{decision_id}` | canonical decision detail |
| Launch | GET | `/api/launch/state` | V1/family authority |
| Family | GET | `/api/launch/family/{family}` | family readiness |
| Reliability | GET | `/api/reliability/state` | system reliability |
| KDS | GET | `/api/kds/state` | decision/reliability evidence |
| Receipt | POST | `/api/tx/receipt` | explicit transaction/receipt lookup |

## Command contracts

| Surface | Method | Endpoint | Guard |
|---|---|---|---|
| Command Center controls | POST | `/api/commandcenter/control` | capability + reason |
| Launch mode | POST | `/api/launch/mode` | governance/capability |
| Enable next family | POST | `/api/launch/enable-next` | governance/capability + V1 policy |
| Pause family | POST | `/api/launch/pause-family` | governance/capability |
| Revert family | POST | `/api/launch/revert-family` | governance/capability |
| Quarantine family | POST | `/api/launch/quarantine-family` | governance/capability |
| Simulate opportunity | POST | `/api/opportunities/simulate` | admin; always dry-run |
| Trade opportunity | POST | `/api/opportunities/trade` | admin + broadcast; future live-authority gate |

## Mobile transaction history

The primary activity/history source is `/api/fund/ledger`. The mobile must render transaction provider, venue/lane, chain, transaction/receipt IDs, decision ID when present, status, realized net, gas, borrow cost, and timestamps from backend evidence. It must never infer settlement from a submitted transaction alone.

## Realtime contract

Existing websocket summary support remains the realtime channel. The mobile must treat websocket data as deltas/acceleration, not a replacement for canonical snapshots. After reconnect or stale detection, fetch the canonical snapshot again.

## Stale/degraded contract

Every canonical read surface must expose:

- loading state;
- last-known-good timestamp;
- stale/degraded state;
- backend reason code when available;
- retry/recovery action;
- clear indication when the app is showing cached data.

## Live-authority contract

Before any real-capital activation, a separate operational review must verify `dry_run`, `auto_trading`, private/protected submission lane, wallet/executor configuration, signer, chain, withdrawal destination, V1 family authority, receipt/settlement lineage, and a deliberately capped flash-arb transaction. Mobile may expose this workflow but must not silently perform it.
