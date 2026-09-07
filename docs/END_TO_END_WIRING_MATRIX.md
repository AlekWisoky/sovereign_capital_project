# End-to-end wiring matrix

This document is the authoritative checklist for the controlled OMAR integration. `wired` means there is an executable production-path connection, not merely a type, route, or test fixture.

| Responsibility | Backend | Mobile | Production/main synchronization | Status |
|---|---|---|---|---|
| Canonical decision identity | `runtime_decision_facade` | consumes decision/read models | controlled branch only until PR #88 merges | **wired / pending merge** |
| Correlation identity | decision facade + settlement lineage | read-only display/read models | controlled branch only | **wired / pending merge** |
| Operator-intent snapshot | canonical operator-intent module | settings/control inputs exist | controlled branch only | **wired / pending merge** |
| `capital_engine_state()` decision snapshot | decision facade | read-only state surface | controlled branch only | **wired / pending merge** |
| OMAR recommendation/action | OMAR runtime | OMAR API client added | not yet merged to `main` | **backend wired / mobile API wired** |
| OMAR operator UI controls | OMAR API | no dedicated OMAR control screen yet | not merged | **GAP: UI** |
| Governance/admission | admission services | command-center controls | controlled branch only | **wired / pending merge** |
| Adaptive risk-budget sizing | sizing/execution path | read-only | controlled branch only | **wired / pending merge** |
| Physical execution identity | execution services | read-only | controlled branch only | **wired / pending merge** |
| Canonical receipt/settlement | receipt + settlement services | read-only | controlled branch only | **wired / pending merge** |
| Exact OMAR settlement attribution | lifecycle bridge + integrity gate | n/a | controlled branch only | **wired / pending merge** |
| OMAR learning | bounded learner + gate | read-only | controlled branch only | **wired / pending merge** |
| Sentry initialization | app boot + `sentry_config` | n/a | controlled branch only | **wired / pending merge** |
| WalletConnect provider session | EIP-1193 session bridge | global mount/session | controlled branch only | **wired / pending merge** |
| Withdrawal transaction preparation | backend withdraw routes | off-ramp prepare flow | existing production branch may differ | **wired / verify** |
| External-wallet withdrawal signing | backend prepares; mobile provider now exposed | WalletConnect provider exists | not merged | **GAP: final OffRamp button/action wiring** |
| Backend hot-wallet withdrawal | privileged backend mode | must not be used by public staging | production policy must be separately verified | **restricted / verify** |
| Mobile settings → backend runtime settings | settings client/routes | settings screen | controlled branch only | **wired / audit remaining settings fields** |
| Mobile AI/command-center read models | backend routes | command-center/mind screens | controlled branch only | **wired / audit endpoint parity** |
| Live broadcast authority in staging | deployment-mode guards | no direct live authority | Render currently points at old branch | **BLOCKED until staging realignment** |
| Auto-trading authority in staging | deployment-mode guards | controls cannot bypass backend | Render currently points at old branch | **BLOCKED until staging realignment** |

## Required completion order

1. Green complete Linux pytest matrix.
2. Green backend quality, mobile, and contracts.
3. Exact verified commit SHA recorded.
4. Merge only the controlled integration PR into `main` after review.
5. Align Render staging to that exact merged commit/branch.
6. Verify health, deployment identity, runtime state, and safety controls only.
7. Verify staging has no live broadcast/auto-trading authority.
8. Finish the Mobile OffRamp WalletConnect signing action and add an integration test before enabling external-wallet withdrawals for users.

## Economic invariants

- Expected/gross profit is not settled net profit.
- Gas and slippage are execution economics, not optional display fields.
- A pending or optimistic receipt cannot teach OMAR.
- A settled outcome without exact canonical lineage cannot teach OMAR.
- Withdrawal amount must come from canonical available/settled capital, not an optimistic UI balance.
- External wallet signing must sign only backend-produced, policy-validated transaction intent.
