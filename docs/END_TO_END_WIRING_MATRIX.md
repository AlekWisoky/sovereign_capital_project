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
| External-wallet signing | WalletConnect EIP-1193 session bridge + guarded mutation path | OffRamp | **wired / acceptance verified in PR #158; main post-merge CI pending** |
| External-wallet sender proof | canonical sender validation | OffRamp | **wired / verified** |
| Chain-id / tx-field verification before send | guarded mutation + prepared transaction validation | OffRamp | **wired / verified** |
| Submitted/pending/reconciliation status | backend canonical external-withdraw reconciliation | OffRamp | **wired / verified** |
| Backend hot-wallet withdrawal | privileged backend mode | not used by public/staging UI | **restricted / verify** |
| Withdraw-all | canonical control + preview + execution lifecycle | operator control surface | **wired / verify** |

## External-wallet canonical flow

The required OffRamp lifecycle is:

`prepare -> verify connected wallet address/chain + exact prepared tx fields -> user signs via WalletConnect eth_sendTransaction -> capture tx hash as submitted/pending -> read backend/RPC status -> accept completion only from canonical receipt/settlement truth`

The current mainline implementation routes the guarded OffRamp mutations through the WalletConnect EIP-1193 provider, validates the connected sender/chain and prepared transaction, captures the returned transaction hash, and reconciles through the canonical backend external-withdraw route. The exact bound transaction is retained for reconciliation independent of later wallet-session state. PR #158 added focused acceptance coverage for wrong chain, missing wallet, invalid transaction hash, and successful submission transition with exact bound transaction fields/status. The PR was merged as `b8fbaab1d868a193d1aba670fdd72f1132d4591b`; the post-merge main CI gate is still running. A returned transaction hash remains submission evidence, not economic settlement.

## Runtime / deployment synchronization

| Item | Current verified state |
|---|---|
| Authoritative `main` | `b8fbaab1d868a193d1aba670fdd72f1132d4591b` (post-#158 main CI run `34957291390` pending) |
| PR #156 external-wallet settlement | merged as `0e4851ec2cd7c984bfb7a0054ff92a30befba6db`; main CI `34927326375` green |
| PR #157 explicit-USD settlement boundary | merged as `21fd5ecb8b1bc0037e8ee530b205e981160c3bcd`; main CI `34954100000` green |
| PR #158 OffRamp acceptance coverage | merged as `b8fbaab1d868a193d1aba670fdd72f1132d4591b`; PR CI `34956357733` green; post-merge main CI pending |
| Authoritative staging service | Render `sovereign-capital` (`srv-daej2f1t0dsc73aeg430`) |
| Staging branch | `main` |
| Staging URL | `https://sovereign-capital-rsxs.onrender.com` |
| Latest staging deployment | Render `dep-dakhn4psrm7s73c27nlg` for `b8fbaab1d868a193d1aba670fdd72f1132d4591b`, currently `update_in_progress` |
| Last completed verified runtime deployment | `dep-dakh6iqjnfac73cl6b0g` for `21fd5ecb8b1bc0037e8ee530b205e981160c3bcd`, live before #158 auto-deploy |
| Staging safety posture | non-live; `public_allow_broadcast=false`; no live-authority activation |
| Secondary Render service | `sovereign_capital_project` (`srv-da4k8a3tqb8s73859ft0`) |
| Secondary service branch | `architecture-c-contract-tests` |
| Secondary service role | **non-authoritative / stale** |
| Secondary service disposition | **retire only after confirming it is no longer needed** |
| Environment reconciliation | Issue #146 |
| Documentation reconciliation | Issue #147 |
| Live-authority review | Issue #89 remains open and blocking |

The authoritative staging service is `sovereign-capital` on `main`. The older `sovereign_capital_project` service remains a separate stale environment and is not a production authority. No live signing, broadcast, automatic trading, or capital mutation is authorized by this matrix.

## Economic invariants

- Expected/gross profit is not settled net profit.
- Explicit USD economics are required for USD-dependent receipt persistence/learning; raw wei is never inferred as USD.
- Gas and slippage are execution economics and must be accounted for in after-cost truth when authoritative data exists.
- No stale or optimistic profitability projection can authorize execution.
- A pending/submitted transaction is not a settled outcome.
- OMAR learns only from a physically persisted, truth-verified canonical settlement.
- Learning requires the canonical lineage identifiers and action context.
- Decision-time capital state is part of immutable learning context.
- Withdrawal amount must derive from canonical available/settled capital, not optimistic UI state.
- External wallet signing must sign only backend-produced, policy-validated transaction intent.
- Staging must not possess live broadcast or automatic-trading authority.

## Completion order

1. External-wallet OffRamp acceptance coverage — **merged** (#158); post-merge main CI must complete green before final acceptance closure.
2. Documentation truth reconciliation — **this Issue #147 branch**; requires CI and review before merge.
3. Render environment reconciliation — **open** (#146); authoritative staging is established, stale service remains untouched pending retirement confirmation.
4. Return to Issue #89 for a fresh live-authority review only after remaining environment/documentation blockers and production/VPS identity are resolved.

Issue #145's legacy raw-wei-to-USD defect is no longer an open blocker: the explicit-USD boundary was repaired and merged in PR #157. Issue #153's canonical external-wallet settlement gap was repaired and merged in PR #156.
