# End-to-end wiring matrix

This document is the authoritative engineering contract for the controlled integration. `wired` means an executable production-path connection exists; `pending merge` means it exists only on the controlled branch; `gap` means the responsibility is not yet executable end to end.

## Canonical lifecycle

| Responsibility | Canonical owner | Downstream consumer | Main / production sync | Status |
|---|---|---|---|---|
| Market observation / opportunity discovery | scanner + opportunity services | decision engine | main baseline | **wired** |
| Canonical `decision_id` | `decision_identity.py` + decision facade | OMAR, governance, execution, settlement | controlled branch only | **wired / pending merge** |
| Canonical `correlation_id` | decision identity layer | execution, settlement, learning | controlled branch only | **wired / pending merge** |
| Operator-intent snapshot | `operator_intent.py` | decision + OMAR context | controlled branch only | **wired / pending merge** |
| Wealth-goal snapshot | wealth-goal service | intent / capital context | controlled branch only | **wired / verify** |
| `capital_engine_state()` decision snapshot | capital facade + decision facade | OMAR learning integrity / downstream admission | controlled branch only | **wired / pending merge** |
| OMAR recommendation | `omar/runtime.py` + real learner | governance/admission | controlled branch only | **wired / pending merge** |
| OMAR identity authority | none | canonical decision layer | n/a | **correctly absent** |
| Governance/admission | governance + admission services | sizing / execution | controlled branch only | **wired / pending merge** |
| Adaptive risk-budget sizing | capital/risk sizing services | execution | controlled branch only | **wired / pending merge** |
| `sizing_id` | sizing/settlement lineage | execution + settlement | controlled branch only | **wired / pending merge** |
| Execution identity | execution lifecycle | receipt / settlement | controlled branch only | **wired / pending merge** |
| `execution_id` | execution lifecycle | physical settlement | controlled branch only | **wired / pending merge** |
| Receipt verification | receipt facade | canonical settlement | controlled branch only | **wired / pending merge** |
| Physical canonical settlement ledger | canonical settlement/accounting | outcome learning | PR #48 baseline + controlled bridge | **wired / pending merge** |
| `outcome_id` | canonical settlement | OMAR integrity gate | controlled branch only | **wired / pending merge** |
| Exact OMAR settlement attribution | `OmarReceiptFacade` + lifecycle adapter + integrity gate | real learner | controlled branch only | **wired / pending merge** |
| OMAR learning | bounded contextual learner | future OMAR recommendations | controlled branch only | **wired / pending merge** |
| Policy update / OOS evidence / promotion | existing learning/evolution systems | future admission | **must remain gated by settled evidence** | **wired / verify** |

## Operator and capital movement surfaces

| Responsibility | Backend | Mobile | Status |
|---|---|---|---|
| Command-center controls | command/control APIs | control center | **wired / verify parity** |
| Safety controls / pause / allocation freeze | canonical control state | operator controls | **wired** |
| OMAR state/start/stop API | existing OMAR API | client helper added | **wired / UI gap** |
| OMAR dedicated operator UI | existing API | no dedicated screen | **GAP — not required for backend authority** |
| Withdrawal config | withdraw routes | off-ramp | **wired** |
| Withdrawal prepare | backend-produced tx intent | off-ramp Prepare | **wired** |
| External-wallet signing | WalletConnect EIP-1193 session bridge exists | OffRamp must invoke it with prepared tx | **GAP — final action wiring** |
| External-wallet sender proof | backend supports `from_address` taxonomy | client must verify connected address before send | **GAP — final action wiring** |
| Chain-id / tx-field verification before send | backend produces canonical tx | client helper must verify prepared tx against connected chain/address | **GAP — final action wiring** |
| Submitted/pending/reconciliation status | backend has tx-status/read-RPC surfaces | OffRamp must display submitted/pending until canonical proof | **GAP — final action wiring** |
| Backend hot-wallet withdrawal | privileged backend mode | not used by public/staging UI | **restricted / verify** |
| Withdraw-all | canonical control + preview + execution lifecycle | operator control surface | **wired / verify** |

## Runtime / deployment synchronization

| Item | Current state |
|---|---|
| Single integration PR | **PR #88 against `main`** |
| Integration branch | `integration/canonical-omar-controlled` |
| Base | `main` at `eea8a3fd347074deeb9cac97ae20d28343a433b1` |
| Current branch head | changes continue until final green CI SHA is established |
| Historical OMAR PR chain | frozen/closed; useful contracts extracted selectively |
| Source-mutating CI | **deleted from intended architecture** |
| Runtime monkey-patching | **removed from current constructor/integration path** |
| Render staging | currently points at stale `architecture-c-contract-tests`; must be aligned only after final green SHA |
| Staging authority | must remain non-live: no broadcast and no auto-trading authority |

## Family policy

A strategy family is retained only when it has a declared mandate, explicit lifecycle state, bounded capital/risk policy, and a path into the same canonical decision → admission → sizing → execution → settlement → outcome model. Families that are merely experimental are **not production authority**; they remain observe/paper/shadow only. They should not be deleted solely because they are disabled. What must be deleted is duplicate execution/identity/accounting logic that creates a second architecture.

Current retained mandate families are `flash_arb`, `funding_arb`, `cex_dex_arb`, `cex_cex_arb`, `liquidation_capture`, `mev_search`, `volatility_market_making`, `stat_arb`, and `treasury_yield`. Their lifecycle state determines whether they can progress toward production; the canonical pipeline remains uniform.

## Economic invariants

- Expected/gross profit is not settled net profit.
- Gas and slippage are execution economics and must be accounted for in after-cost truth.
- No stale or optimistic profitability projection can authorize execution.
- A pending/submitted transaction is not a settled outcome.
- OMAR learns only from a physically persisted, truth-verified canonical settlement.
- Learning requires `decision_id`, `correlation_id`, `execution_id`, `outcome_id`, `sizing_id`, `opportunity_id`, `route_id`, and `action`.
- Decision-time `capital_engine_state()` is part of immutable learning context.
- Withdrawal amount must derive from canonical available/settled capital, not optimistic UI state.
- External wallet signing must sign only backend-produced, policy-validated transaction intent.
- Staging must not possess live broadcast or automatic-trading authority.

## Completion order

1. Let the current full Linux pytest matrix finish; use actual failures only.
2. Repair the smallest real defect and rerun the complete matrix.
3. Require backend quality, mobile, and contracts green as well.
4. Record the exact green commit SHA.
5. Align Render staging to that exact SHA/branch and allow its normal auto-deploy.
6. Verify deployment identity, health, runtime state, and safety controls read-only.
7. Confirm live broadcast and auto-trading authority are unavailable.
8. Finish and test the OffRamp WalletConnect action before treating external-wallet withdrawal as end-to-end complete.
9. Mark PR #88 ready and merge the single controlled PR into `main`; do not create another archaeology branch.
