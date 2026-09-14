# End-to-end wiring matrix

This document is the authoritative engineering contract for the controlled integration. `wired` means an executable production-path connection exists; `gap` means the responsibility is not yet executable end to end.

## Canonical lifecycle

| Responsibility | Canonical owner | Downstream consumer | Status |
|---|---|---|---|
| Market observation / opportunity discovery | scanner + opportunity services | decision engine | **wired** |
| Canonical decision / correlation identity | decision identity + decision facade | OMAR, governance, execution, settlement, learning | **wired / verify** |
| Operator-intent snapshot | operator-intent service | decision + OMAR context | **wired / verify** |
| Wealth-goal snapshot | wealth-goal service | intent / capital context | **wired / verify** |
| Capital decision snapshot | capital facade + decision facade | admission / learning integrity | **wired / verify** |
| OMAR recommendation | OMAR runtime + learner | governance/admission | **wired / verify** |
| OMAR identity authority | none | canonical decision layer | **correctly absent** |
| Governance/admission | governance + admission services | sizing / execution | **wired / verify** |
| Adaptive risk-budget sizing | capital/risk sizing services | execution | **wired / verify** |
| Execution identity | execution lifecycle | receipt / settlement | **wired / verify** |
| Receipt verification | receipt facade | canonical settlement | **wired / verify** |
| Physical canonical settlement ledger | canonical settlement/accounting | outcome learning | **wired / verify** |
| Exact OMAR settlement attribution | receipt facade + lifecycle adapter + integrity gate | real learner | **wired / verify** |
| OMAR learning | bounded contextual learner | future recommendations | **wired / verify** |
| Policy update / OOS evidence / promotion | existing learning/evolution systems | future admission | **must remain gated by settled evidence** |

## Operator and capital movement surfaces

| Responsibility | Backend | Mobile | Status |
|---|---|---|---|
| Command-center controls | command/control APIs | control center | **wired / verify parity** |
| Safety controls / pause / allocation freeze | canonical control state | operator controls | **wired** |
| OMAR state/start/stop API | existing OMAR API | client helper | **wired / UI gap** |
| Withdrawal config | withdraw routes | OffRamp | **wired** |
| Withdrawal prepare | backend-produced transaction intent | OffRamp Prepare | **wired** |
| External-wallet signing | WalletConnect EIP-1193 session bridge exists | OffRamp must invoke it with prepared tx | **GAP — Issue #150** |
| External-wallet sender proof | backend supports `from_address` taxonomy | client must verify connected address before send | **GAP — Issue #150** |
| Chain-id / tx-field verification before send | backend produces canonical tx | client must verify prepared tx against connected chain/address | **GAP — Issue #150** |
| Submitted/pending/reconciliation status | backend has tx-status/read-RPC surfaces | OffRamp must display submitted/pending until canonical proof | **GAP — Issue #150** |
| Backend hot-wallet withdrawal | privileged backend mode | not used by public/staging UI | **restricted / verify** |
| Withdraw-all | canonical control + preview + execution lifecycle | operator control surface | **wired / verify** |

## External-wallet canonical flow

The required OffRamp lifecycle is:

`prepare -> verify connected wallet address/chain + exact prepared tx fields -> user signs via WalletConnect eth_sendTransaction -> capture tx hash as submitted/pending -> read backend/RPC status -> accept completion only from canonical receipt/settlement truth`

The mobile WalletConnect bridge exposes `sendWalletConnectTransaction()`, which calls `eth_sendTransaction` and validates the returned transaction hash. The current `OffRampScreen` does not invoke it, so the external-wallet path is not yet end-to-end. A returned transaction hash is submission evidence, not economic settlement.

## Runtime / deployment synchronization

| Item | Current verified state |
|---|---|
| Authoritative `main` | `e6ec3306dd0e70ff21d51abdf64662aae07c61b8` |
| Exact-main economic-unit CI | green |
| Canonical post-settlement learning-order repair | merged and CI green (#149) |
| Authoritative staging service | Render `sovereign-capital` (`srv-daej2f1t0dsc73aeg430`) |
| Staging branch | `integration/canonical-omar-controlled` |
| Staging URL | `https://sovereign-capital-rsxs.onrender.com` |
| Last runtime deployment verified | commit `77eacc6e85fe6a1869f8e0cd43799ca0ae6c0783` |
| Staging safety posture | non-live; public broadcast disabled; executor not enforced in verified runtime |
| Secondary Render service | `sovereign_capital_project` (`srv-da4k8a3tqb8s73859ft0`) |
| Secondary service branch | `architecture-c-contract-tests` |
| Secondary service role | **non-authoritative / stale**; recent deployments fail |
| Secondary service disposition | **do not delete or disable until owner confirms it is no longer needed** |
| Environment reconciliation | Issue #146 |
| External-wallet OffRamp completion | Issue #150 |
| Live-authority review | Issue #89 remains open and blocking |

The two Render services point to the same repository but different branches and environments. The verified staging authority is `sovereign-capital` because it is the service used for controlled staging verification and has the known non-live safety posture. The `sovereign_capital_project` service tracks an older architecture branch and is not a production authority. Its existence alone is not sufficient evidence that it may be deleted, so it remains untouched pending explicit confirmation.

## Economic invariants

- Expected/gross profit is not settled net profit.
- Gas and slippage are execution economics and must be accounted for in after-cost truth.
- No stale or optimistic profitability projection can authorize execution.
- A pending/submitted transaction is not a settled outcome.
- OMAR learns only from a physically persisted, truth-verified canonical settlement.
- Learning requires the canonical lineage identifiers and action context.
- Decision-time capital state is part of immutable learning context.
- Withdrawal amount must derive from canonical available/settled capital, not optimistic UI state.
- External wallet signing must sign only backend-produced, policy-validated transaction intent.
- Staging must not possess live broadcast or automatic-trading authority.

## Completion order

1. Economic-unit boundary — **complete** (#148).
2. Canonical post-settlement learning order — **complete** (#149).
3. OffRamp external-wallet final action and reconciliation — **open** (#150).
4. Render environment reconciliation — **open** (#146); authoritative staging is established, stale service remains untouched pending confirmation.
5. Reconcile remaining engineering-truth documentation against actual GitHub/Render state.
6. Return to Issue #89 for a fresh live-authority review only after the remaining blockers are resolved.

No step in this document authorizes live signing, broadcast, automatic trading, or capital mutation.
