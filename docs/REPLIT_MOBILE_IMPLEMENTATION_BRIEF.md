# Replit Mobile Implementation Brief

## Product
Sovereign Capital mobile operator application.

The frontend is an operator/control surface for the backend capital operating system. Replit is responsible for visual implementation and frontend polish; it must not redefine backend authority, economics, decision identity, or execution policy.

## Primary navigation

1. **Home** — system health, capital truth, current goal, high-level execution state.
2. **Capital** — treasury, Internal Prime, bankroll, settled P&L, wealth goal, wallet, off-ramp.
3. **Opportunities** — market opportunities and canonical admission; V1 execution family is `flash_arb` only.
4. **OMAR / AI** — recommendation, explanation, learning state, expectation error; no independent execution authority.
5. **Risk** — governance, launch mode, family authority, safety, drawdown, readiness.
6. **Activity** — live/pending/submitted/mined/settled transactions, receipts, ledger history, decision lineage.

Settings/setup is a secondary surface, not a primary capital tab.

## Canonical lifecycle UI

Every trade detail must present one identity:

`decision_id → opportunity → admission → sizing → execution → receipt → settlement → realized net → expectation error → OMAR learning`

Do not create a frontend trade ID that competes with `decision_id`.

## Transaction UI

Activity must distinguish:

- opportunity/decision created;
- admitted/blocked;
- execution requested;
- submitted;
- pending/private submission;
- mined/receipt found;
- receipt verified;
- canonical settlement verified;
- realized net recorded;
- learning recorded.

Display provider, venue, chain, lane, route, tx hash, receipt ID, decision ID, gas cost, borrow cost, realized net, timestamp, and backend reason codes when available.

Never call a transaction "profitable" because it was submitted. Profitability comes from canonical settlement.

## Capital screen

Show separate cards for:

- Treasury balance and realized/reinvestable profit.
- Deployable vs locked capital.
- Internal Prime capacity, borrowed amount, utilization, family exposure, open loans.
- Bankroll/base notional and next approved size.
- Wealth goal progress, target, deadline/horizon, required velocity, drawdown and risk posture.

Do not conflate Treasury balance, Internal Prime capacity, and flash-loan liquidity.

## Opportunities

The screen may show market opportunities from canonical backend snapshots. It must display expected net, expected ROI, required capital, proposed/requested notional, approved size, provider/route, confidence, admission state and reason codes.

The action button hierarchy is:

`Inspect → Simulate → Request/Admit → Execute`

Execute is not a normal convenience button. It is hidden/disabled unless backend capability, V1 family, governance, profitability, capital truth, sizing and live-authority conditions all permit it.

## OMAR

Show:

- current recommendation;
- canonical decision context;
- expected net;
- realized net;
- expectation error;
- learning status;
- settlement verification;
- reason codes.

Do not expose a UI control that gives OMAR execution authority.

## Risk / governance

Show:

- V1 mode;
- active family (`flash_arb` only for live V1);
- future family state (`observe_only` / shadow);
- global execution block;
- governance state;
- drawdown;
- reliability/staleness;
- kill/pause state;
- last audit events.

Control mutations require operator unlock, local ARM state, explicit confirmation, a reason, and backend capability authorization.

## Realtime

Use websocket summaries for acceleration/deltas. Always reconcile against canonical snapshots after reconnect, stale state, app resume, or material control changes.

Every data surface needs:

- loading;
- last-known-good time;
- stale/degraded badge;
- backend reason code;
- retry/reconcile action.

## Demo mode

Backend is the production default.

Demo/mock data is an explicit user-selected mode and must carry a persistent `DEMO` label. Never silently fall back from backend to demo.

## Security

- Never persist admin keys in ordinary AsyncStorage.
- Never expose private keys or signer secrets to screen components.
- Treat mobile state as untrusted intent/cache.
- Backend capability checks remain authoritative.
- Do not add a mobile-only route that bypasses canonical admission or settlement.

## Institutional capital scale UX

The backend roadmap uses USD-denominated institutional targets rather than hard-coded token raw amounts:

- $250k baseline target;
- $500k operating target;
- $1M scale tier;
- $2.5M scale tier;
- $5M scale tier;
- $10M Internal Prime capacity target.

These are policy targets, not automatic permission to force a trade to that size. Final approved size is constrained by provider/pool liquidity, slippage, profitability after costs, governance/admission, Internal Prime capacity, treasury deployable capital, drawdown, freshness and execution realism.

Mobile must display **requested notional** and **approved notional** separately.

## Replit acceptance test

Before a visual build is accepted:

1. Backend mode is the default.
2. Demo mode is explicit and visually labeled.
3. Six-tab IA matches this brief.
4. Transaction history shows providers/venues and canonical IDs.
5. Decision detail shows the complete lifecycle.
6. Stale/degraded state is visible.
7. No screen invents capital truth.
8. No screen grants live authority.
9. Future families remain visibly observe-only/shadow.
10. Flash-arb is the only V1 capital family.
11. Dangerous mutations require confirmation/reason and backend authorization.
12. Requested vs approved institutional sizing is visible.
