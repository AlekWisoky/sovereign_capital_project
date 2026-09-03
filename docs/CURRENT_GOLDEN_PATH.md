# Current Golden Path

Audit basis: repository HEAD `52d9669bda8c44d3ed74ab3df8bb5f572ff72fb2`. Source and focused executable tests are authority. `docs/SYSTEM_DEEP_DIVE.md` is not present at this HEAD; the uploaded copy is prior context only.

Status vocabulary: **PROVEN** means a focused executable test proves the stated boundary, not that production deployment is proven. **PARTIALLY PROVEN** means source and component tests exist but the complete boundary is not exercised. **CONFIGURATION-DEPENDENT** requires runtime addresses, keys, RPC/provider capability, or flags. **NOT PROVEN** lacks executable end-to-end evidence. **DISCONNECTED** exists but is not in the mandatory path. **MISSING** has no implementation found.

## Current architecture and boundaries

`RuntimePrimaryScanFacade` calls `arb_engine` against `JsonRpcClient`; normalized `Opportunity` objects are enriched and selected by runtime/decision services. Auto execution enters `RuntimeExecuteEntryFacade`, then `RuntimeExecuteDispatchFacade`, whose canonical auto-admission order is fund hold, family readiness, route/capture realism, flash-loan truth, and treasury governance. `RuntimeExecuteWrapperFacade` invokes `execution.try_execute_opportunity`; submitted transactions are recorded in PnL/replay/pending state and queued to `RuntimeReceiptFacade`.

`RuntimeReceiptFacade` polls the chain, decodes `ArbExecuted`, updates `PnLStore`, and calls `ReceiptService.synchronize_settlement_accounting`. `CapitalWriteService.commit_receipt_settlement` writes ledger, bankroll history, treasury snapshot, capital events, and optional internal-prime transition in one SQLite transaction. Operator services project those states to REST/WebSocket; the mobile command center can instead start in explicit mock mode and has a legacy fallback that overlays demo values.

## Actual execution sequence

```text
RPC block/eth_call
  -> quote_edges_batch
  -> find_two_leg_opportunities / find_three_leg_opportunities
  -> Opportunity(id, route_id, route, min_outs, can_execute=false)
  -> runtime profitability/route/capture enrichment
  -> DecisionEngine.annotate_and_decide
  -> RuntimeExecuteEntryFacade._execute_auto_entry
  -> RuntimeExecuteDispatchFacade._prepare_auto_execution_dispatch
  -> ExecutionService.auto_trade_admission_gate
  -> RuntimeExecuteWrapperFacade._run_prepared_auto_execution
  -> execution.try_execute_opportunity
  -> requote/route mutation -> calldata -> estimate/simulate -> terminal safety
  -> sign -> public/private RPC submit
  -> ExecutionService._record_exec -> PnL expected row/replay draft/_pending/_receipt_q
  -> RuntimeReceiptFacade._receipt_loop
  -> PnLStore.update_receipt + decode_arb_executed
  -> ReceiptService.synchronize_settlement_accounting
  -> CapitalWriteService.commit_receipt_settlement
  -> ledger/bankroll/treasury/capital-event state
  -> replay/learning/telemetry/operator summaries
```

## Stage map

Abbreviations: PS = persistent state; FB = failure behavior; R/T/I = retry, timeout, idempotency; CID = correlation identifier; M/O = mandatory or optional.

| # | Stage and status | Actual file / symbol | Caller -> callee | Input -> output | PS; FB; R/T/I; CID; M/O; next-stage connection; evidence |
|---|---|---|---|---|---|
| 1 | Market/RPC data: **PARTIALLY PROVEN** | `backend/victor_ai_bot/rpc.py` `JsonRpcClient.call`, `batch`, `eth_call`; `runtime_primary_scan_facade.py` | runtime tick -> `JsonRpcClient` | RPC method/block -> `RpcResult`/block | PS: in-memory provider capability/cache. FB: error result. R: batch fallback only. T: client default 10s. I: read-only. CID: JSON-RPC integer only. M. Connected to quotes. Tests cover client hardening, not live correctness. |
| 2 | DEX quote: **PROVEN with mocks** | `arb_engine.py` `quote_edge`, `quote_edges_batch`; `quote_univ3.py`, `quote_curve.py`, `quote_balancer.py` | scanner -> quote adapters -> RPC | edges + amount -> amounts/meta | PS: per-block cache. FB: `None`, scanner skips. R: batch fallback, no semantic retry. T: parent scan budget. I: cache key. CID: edge key/block, not trade ID. M. Connected. `test_arb_engine_hardening.py`. |
| 3 | Opportunity discovery: **PROVEN with mocks** | `arb_engine.py` `find_two_leg_opportunities`, `find_three_leg_opportunities` | scan facade -> scanners | quotes/block/amount -> `Opportunity[]` | PS: runtime `_opps`. FB: route skipped/budget break. R: next tick. T: 1500/1600ms from facade. I: deterministic ID per chain/route/amount/block. CID: `Opportunity.id`, `route_id`. M. Connected. Arb tests. |
| 4 | Normalization: **PROVEN** | `models.py` `Opportunity`, `Route`, `RouteLeg` | scanner constructors -> runtime services | raw quote route -> Pydantic model | PS: runtime snapshot/replay. FB: validation exception. R: none. T: n/a. I: deterministic model content. CID: opp ID and route ID. M. Connected. Model use throughout tests. |
| 5 | Profitability: **PARTIALLY PROVEN** | `profitability_state.py`; `runtime_services/profitability_truth.py`; `execution.py` `_execution_profitability_plan`, `check_profit_and_repay` | runtime enrichment and execution -> safety | final minOut, amount, gas, configured fee -> after-cost profit | PS: opp meta, PnL plan. FB: fail closed where contract exists; `gas_cost_unavailable` exception path exists. R: next tick. T: RPC gas timeout. I: recomputable. CID: route/opp via containing objects. M at terminal execution. Connected. Safety/preflight/terminal tests. |
| 6 | Slippage/minOut: **PROVEN with mocks** | `arb_engine.py` `_apply_slippage`, `requote_opportunity` | scanner/execution sizing -> route legs | quote + bps -> per-leg minOut | PS: opportunity/replay. FB: requote returns `None`; execution aborts. R: next opportunity/tick. T: quote timeout. I: deterministic integer math. CID: route ID may remain while amounts mutate. M. Connected to calldata. Arb/execution tests. |
| 7 | Flash-loan sizing: **PARTIALLY PROVEN** | `execution_capture/flashloan_sizing.py`; `ExecutionService.auto_trade_flashloan_gate`; `execution.try_execute_opportunity` sizing/requote | capture/decision -> admission -> execution | provider truth + multipliers/caps -> borrow amount/provider | PS: capture metadata/pending/replay. FB: fail closed on auto path when sizing/provider missing. R: next tick. T: none local. I: deterministic given metadata. CID: opp/route. M for auto flash family, bypassable by direct call. Connected. `test_flashloan_sizing.py`, lifecycle proof. |
| 8 | Execution Capture: **PROVEN as auto-path gate; optional at initialization** | `runtime_services/admission_service.py` `prepare_capture`, `gate_capture_drop`; `execution_service.py` `_capture_coordination_failure`, `auto_trade_execution_realism_gate`; `execution_capture/decision_engine.py` | runtime enrichment -> capture evaluate -> auto admission | opportunity/context -> capture decision/route plan/drop | PS: quality/calibration stores and opp meta. FB: preparation raises or auto gate blocks. R: next tick. T: none. I: metadata-derived. CID: opp/route. M for current auto route realism; direct execution bypasses it. Connected. Admission/capture tests. |
| 9 | Decision Engine: **PROVEN component** | `decision_engine.py` `DecisionEngine.annotate_and_decide` | runtime decision facade -> engine | executable opps/budgets/config -> `TradeDecision` | PS: RL/route stats JSON and training JSONL. FB: skip. R: next tick. T: none. I: seeded action selection per block/opp, but learned state evolves. CID: opp/route, no universal ID. Optional by brain mode; mandatory for canonical auto. Connected. Decision tests. |
| 10 | Capital/treasury admission: **PARTIALLY PROVEN** | `execution_service.py` `auto_trade_hold_gate`, `auto_trade_treasury_gate`; `capital_admission_service.py` `evaluate` | dispatch -> canonical auto gate; separate `prepare_auto_execution` -> capital admission | capital truth/family/notional -> allow/deny | PS: capital/treasury repos. FB: fail closed in tested auto gate. R: recovery/next tick. T: none. I: read decision. CID: opp/route; later `capitalCommitId`. M on canonical auto for hold/treasury, but requested-notional `CapitalAdmissionService.evaluate` is not visibly called by `_prepare_auto_execution_dispatch`. Connection is incomplete. Admission tests. |
| 11 | Governance/risk: **PARTIALLY PROVEN** | `execution_service.py` `auto_trade_admission_gate`, `handle_governance_pre_execute`; `admission_service.py` `apply_control_and_risk_gates`; drawdown/kill-switch modules | dispatch -> admission/governance | fund/family/route/flash/treasury/governance state -> block/allow | PS: governance/drawdown/kill-switch stores. FB: canonical admission fails closed; several optional hooks catch and continue. R: next tick. T: none. I: decision reads. CID: intent ID appears late. M for auto admission sequence, not universal. Connected on auto path. `test_auto_trade_admission_sequence_contract.py`. |
| 12 | Route construction: **PROVEN component** | `execution_capture/route_execution_plan.py` `apply_execution_route_plan`; `route_encoding.py` `route_id_hex` | capture/ExecutionService/execution -> route mutation | legs/plan -> executable legs + route ID | PS: opp meta/replay. FB: auto gate or execution abort. R: next tick. T: none. I: route hash deterministic. CID: route ID. M for auto. Connected. Route-plan tests. |
| 13 | Calldata: **PROVEN component** | `calldata_builder.py` `build_execute_calldata` | `execution.try_execute_opportunity` -> builder | provider/borrow/minProfit/deadline/legs -> ABI v2 calldata + route ID | PS: execution plan/replay. FB: missing executor/profitTo yields no calldata and aborts live. R: none. T: deadline 30s default. I: deterministic except deadline. CID: route ID embedded. M live. Connected. Selector/calldata tests and ABI v2 contract. |
| 14 | Gas estimation: **PROVEN with mocks, configuration-dependent live** | `gas.py` `suggest_gas`; `rpc.py` `estimate_gas`; `execution.py` | execution -> RPC | tx skeleton -> fees/gas limit/cost | PS: plan/metrics. FB: abort when required. R: next attempt. T: RPC 10s. I: read-only. CID: enclosing opp/route. Config flag controls estimate requirement. Connected. Gas/execution tests. |
| 15 | Simulation: **CONFIGURATION-DEPENDENT** | `execution.py` `simulate_call` and simulation block | execution -> `eth_call` | calldata/from/block tags -> ok/revert reason | PS: plan/replay. FB: current-block failure aborts; historical/pending can soft fail. R: previous/pending probes, no retry. T: RPC timeout. I: block-tag deterministic only if archive state retained. CID: route ID in plan. Optional by config. Connected. Execution tests. |
| 16 | Signing: **CONFIGURATION-DEPENDENT** | `execution.py` `Account.sign_transaction` | execution -> eth-account | key/env + nonce + EIP-1559 tx -> raw tx | PS: none. FB: missing key/dependency aborts. R: none. T: none. I: deterministic for fixed nonce/tx. CID: no explicit universal ID. M live. Connected. No live-key proof. |
| 17 | Submission: **CONFIGURATION-DEPENDENT** | `rpc.py` `send_raw_tx`, `send_private_tx`; `execution.py` | execution -> send RPC | raw tx -> tx hash/error | PS: plan then pending/PnL/replay. FB: `send_failed`; no replacement. R: none. T: RPC 10s; private max block current+2. I: raw tx resubmission may be idempotent by tx hash, not managed. CID: tx hash. M live. Connected when successful. |
| 18 | Transaction lifecycle: **NOT PROVEN** | `runtime_receipt_facade.py` in-memory `_pending`, `_receipt_q`; `tx_confirmation.py` `assess_submitted_tx` | bookkeeping -> queue -> receipt loop | tx hash/pending metadata -> pending/mined classification | PS: expected PnL/replay, but queue/pending map are in-memory. FB: three receipt-loop retries then manual recovery. R: 3. T: 180s each, 2s poll. I: receipt settlement is idempotent. CID: tx hash. M after submit. Restart recovery, dropped tx, replacement, nonce reconciliation and reorg handling are not proven. |
| 19 | Receipt confirmation: **PARTIALLY PROVEN** | `rpc.py` `wait_for_receipt`; `runtime_receipt_facade.py` `_receipt_loop` | queue -> RPC | tx hash -> receipt/timeout | PS: PnL/ledger after success. FB: retry/exhausted metadata. R/T above. I: settlement duplicate check. CID: tx hash. M. Connected. Fixture tests prove processing, not live polling. |
| 20 | Event decoding: **PROVEN with fixtures** | `executor_events.py` `decode_arb_executed`; `pnl.py` `update_receipt` | receipt facade/PnL -> decoder | log -> token/profit/provider | PS: PnL row. FB: decode failure leaves truth unavailable; auto trading is disabled during settlement. R: none. T: none. I: pure decode. CID: route ID is indexed on-chain but decoder result is joined mainly by tx hash. M for successful settlement truth. Connected. Decode tests. |
| 21 | Realized PnL: **PROVEN with fixtures** | `pnl.py` `PnLStore.update_receipt`; `usd_pricing.py`; `ReceiptService.realized_after_wei` | receipt loop -> PnL store | receipt/event/gas conversion -> realized token/wei/USD | PS: SQLite `trades`. FB: DB exception propagates to receipt retry path; missing denomination blocks authoritative settlement. R: receipt retry. T: RPC pricing inherits timeout. I: UPDATE by tx hash, but no unique DB constraint. CID: tx hash, opp ID, route ID. M. Connected. PnL/settlement tests. |
| 22 | Treasury settlement: **PROVEN at component boundary, not end-to-end** | `receipt_service.py` `synchronize_settlement_accounting`; `capital_write_service.py` `commit_receipt_settlement` | receipt finalization -> capital writer | decoded outcome/pending -> ledger transaction, bankroll/treasury snapshots/events | PS: SQLite repos plus file mirrors. FB: transaction rolls back and auto trading disables. R: receipt/manual recovery. T: none. I: receipt duplicate checks in repo/ledger/set. CID: tx hash receipt ID, transaction ID, new capitalCommitId. M. Connected. `test_capital_write_service_atomicity.py`, `test_receipt_settlement_truth_path.py`. |
| 23 | Wealth goals: **PARTIALLY PROVEN** | `wealth_goal_service.py` `state`; `admission_service.py` `apply_family_budget`; `execution_service.py` `auto_trade_treasury_gate` | treasury/runtime -> goal service; capture budget/gate reads posture | goal + realized/risk state -> aggressiveness cap/pacing | PS: JSON state/history and treasury goal. FB: unavailable state or ignored optional clamp. R: next read. T: none. I: deterministic except time. CID: goal ID/revision, not trade ID. Optional/direct connection is inconsistent. Goal tests prove surfaces; no full test proves goal changes final borrow. |
| 24 | Replay bundle: **PARTIALLY PROVEN** | `replay_service.py`; `runtime_subsystems/replay_store.py` `create_bundle`, `finalize` | execution bookkeeping/receipt -> replay store | summaries/plan/receipt -> immutable-ish JSON bundle + tx index | PS: atomic JSON files. FB: returns empty/None. R: none. T: none. I: event/decision IDs deterministic; finalization rewrites bundle. CID: event ID, decision ID, tx hash, opp/route IDs. Optional by config. Connected. Store/service tests. Exact RPC responses, cache, mempool, nonce and full market snapshot are absent. |
| 25 | Telemetry/latency: **PARTIALLY PROVEN** | `latency_profiler.py`; `execution_service.py` `handle_post_execute_bookkeeping`; `receipt_service.py` `submit_to_receipt_ms` | execution/receipt -> rolling profiler/telemetry | local timestamps/outcomes -> p50/p90/p99 | PS: bounded memory and optional telemetry stores. FB: best effort. R: none. T: n/a. I: append metrics. CID: generally route/family/tx in outcome, no trace ID. Optional. Connected to summaries. Measures execution and submit-to-receipt separately, not market-data-to-settlement. |
| 26 | Mobile/operator state: **PARTIALLY PROVEN** | backend `operator_summary_service.py`; mobile `api/client.ts`, `api/wsSummary.ts`, `commandCenter/provider.ts`, `useCommandCenter.ts` | REST/WS -> provider/hooks/screens | summaries -> UI models | PS: client store. FB: reconnect/backoff; command center legacy fallback overlays `DEMO_SNAPSHOT`. R: WS exponential to 8s/poll. T: fetch defaults. I: read-only. CID: tx/route fields where supplied. Optional operator surface. Connected, but default source is `mock`, so authority is not guaranteed. Mobile projection tests. |

## State transitions and identifiers

```text
Opportunity.id + route_id
  -> decision annotations / optional intent_id
  -> execution plan
  -> tx_hash
  -> PnL trade row and replay tx index
  -> receipt_id (= tx_hash)
  -> ledger transaction_id
  -> capitalCommitId shared by ledger/bankroll/treasury/capital events
```

There is no single required identifier spanning all stages. `route_id` is the closest pre-submit identifier, `tx_hash` is authoritative after submit, and `capitalCommitId` begins only at settlement.

## Answers A-M

| Question | Current verdict | Source evidence |
|---|---|---|
| A | **PARTIALLY PROVEN** | Source connects scan -> decision -> canonical auto dispatch -> execution, and component tests cover each boundary. No one test drives a scanner-created opportunity through that entire chain. |
| B | **PARTIALLY PROVEN** | Receipt fixtures prove PnL plus atomic ledger/bankroll/treasury writes. No submitted transaction fixture is carried from execution bookkeeping into the real receipt worker and capital truth in one test. |
| C | **NO** | IDs change from opportunity/route to tx hash to transaction/capital commit IDs; no mandatory trace/correlation field spans all stores. |
| D | **NO** | Replay verifies stored context/hash, but lacks exact RPC responses, block/state proof, cache contents, nonce, mempool/private relay response and deterministic clock/random state. |
| E | **PARTIALLY** | Goal-derived aggressiveness is used in `AdmissionService.apply_family_budget`, and treasury goal state affects treasury governance. Mandatory invocation on the canonical dispatch path and final-size propagation are not proven. |
| F | **GATES CANONICAL AUTO; BYPASSABLE** | Capture drop/private-lane/post-ordering checks block `auto_trade_execution_realism_gate`; direct `try_execute_opportunity` does not require capture. |
| G | **NO UNIVERSAL GATE** | Canonical auto has a fail-closed ordered gate, but execution safety is split and direct/manual paths can reach lower-level execution without the full admission sequence. |
| H | **NO** | `LatencySpan` starts inside prepared execution; receipt latency starts at submission. There is no shared market-observation timestamp through settlement. |
| I | **PARTIALLY PROVEN** | Terminal safety uses slippage-aware final minOut, configured flash fee and gas. Correctness requires input/output/gas values to share denomination; conversion is explicit only during receipt accounting, and provider fee configuration can diverge from actual callback fee. |
| J | **NO** | Pending queue/map are in-memory; no restart rehydration, replacement manager, dropped-tx policy, nonce journal, confirmation depth or reorg rollback was found. |
| K | **YES** | `try_execute_opportunity` enforces terminal profitability but not the full capture/fund/family/treasury/governance sequence. Manual API clients exist and must be proven to route through equivalent gates. |
| L | **MIXED** | Backend mode consumes authoritative summaries, but command center defaults to `mock`; legacy backend fallback spreads `DEMO_SNAPSHOT` into the returned model and labels it `backend-mock`. |
| M | **PARTIALLY CLOSED** | Atomic receipt settlement updates ledger, bankroll and treasury snapshots and can affect next sizing. Pretrade reservation/allocation linkage and a single deterministic end-to-end test are missing. |
