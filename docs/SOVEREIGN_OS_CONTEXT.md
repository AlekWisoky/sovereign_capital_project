# Sovereign Capital OS Constitution

## Recovery contract
The repository is the durable source of truth. A new agent must read this file, `docs/SOVEREIGN_OS_STATE.md`, `docs/SOVEREIGN_OS_DECISIONS.md`, and `docs/SOVEREIGN_OS_CHANGELOG.md` before editing, then inspect Git state and the latest relevant commits. Never rely on a lost ClickUp/Codex workspace.

## Identity and doctrine
Sovereign Capital OS is an institutional-grade execution, arbitrage, learning, capital-allocation, treasury, risk, accounting, replay, recovery, and operator-control machine. Profit matters, but never overrides capital safety, accounting integrity, risk controls, governance, rollout readiness, or execution reliability.

The intended synchronized flow is: `DISCOVER -> PRICE -> FILTER -> CAPITAL-DEMAND COMPOSE -> PORTFOLIO SELECT -> ADMIT -> SIZE -> REQUOTE -> RISK CHECK -> SIMULATE -> SIGN -> SUBMIT -> TRACK -> CONFIRM -> DECODE -> AUTHORITATIVE PNL -> SETTLE -> UPDATE LEDGER -> UPDATE TREASURY -> UPDATE WEALTH STATE -> LEARN -> REPLAY -> NEXT ALLOCATION`.

No subsystem may become an isolated parallel truth. Missing, stale, contradictory, ambiguous, non-authoritative, or unreconciled critical state means **NO TRADE**.

## Economics, capital, and risk
Expected realized economics must remain positive after applicable flashloan fees, gas, slippage, route risk, execution uncertainty, capacity constraints, failure exposure, and latency deterioration. Revalidate after changes to size, borrow, route, quote, provider, gas, simulation, or execution plan.

For flashloans, external borrowed notional is not internal treasury commitment, gas reserve, provider capacity, worst-case exposure, or strategy-budget consumption. Never silently reinterpret route amounts, borrowed principal, gas wei, or USD multiplied by `10^18` as universal treasury capital. Treasury denomination and conversion evidence must be explicit.

Portfolio selection must respect declared treasury budgets, strategy budgets, correlation, crowding, liquidity, capacity, gas, risk, drawdown, and conflicts. A goal, AI recommendation, or aggressiveness setting cannot rescue invalid capital truth or authorize a trade.

## Architecture C and CapitalDemand
Architecture C is the approved capital architecture. `CapitalDemand` must be composed authoritatively before `DecisionEngine` portfolio selection and preserve separate dimensions for execution notional, asset, decimals, internal commitment, gas reserve, fee reserve, provider capacity, worst-case exposure, strategy-budget consumption, capital source, treasury denomination, conversion evidence, freshness, provenance, correlation identity, execution-plan identity, solvency, and policy constraints.

The selector scalar has exactly one approved meaning: **strategy-budget consumption in the explicitly declared treasury denomination**. It must not mean route amount, borrowed principal, raw wei, USD x `10^18`, or internal commitment. Current contract code and tests are additive and runtime-unwired.

## Rollout and strategy modes
Phase A initial live eligibility is flash-loan arbitrage only, and only with full readiness, governance, profitability, capital truth, execution quality, recovery, replay, and rollout evidence. Other families may be observed, researched, backtested, simulated, shadowed, or staged; code existence is not authorization.

Single-strategy mode: the user selects one strategy and only that ready, governed strategy may receive live allocation. Multi-strategy mode: the user selects multiple strategies and treasury allocates separate budgets while respecting correlation, crowding, capacity, liquidity, and global risk. AI-managed mode: AI may rank or recommend, but cannot silently activate a strategy or bypass governance/readiness.

Expansion requires realized sample size, positive risk-adjusted performance, stable execution, capacity understanding, capital truth, failure/recovery behavior, replayability, governance approval, and rollout readiness.

## Wealth Goals and aggressiveness
Users may manually specify a desired wealth goal, horizon, objective, and risk constraints, or receive an AI-generated recommendation. Goals control pacing, allocation, sizing, compounding, and risk posture only within hard safety controls. A goal is a target and constraint, never trade permission. Aggressiveness is a bounded modifier applied only after valid demand and safety approval; it cannot bypass profitability, capital, risk, drawdown, capacity, correlation, governance, readiness, or execution safety.

## Ledger, PnL, settlement, and compounding
The eventual institutional chain is: opportunity -> decision -> capital authorization -> reservation -> execution -> durable transaction lifecycle -> receipt -> event decoding -> authoritative realized PnL -> settlement -> treasury update -> capital availability -> next allocation.

Authoritative settlement is: receipt -> decoded `ArbExecuted` profit -> `gasUsed * effectiveGasPrice` -> required denomination conversion -> realized-after-gas PnL -> settlement. Settlement must reject contradictory caller-supplied realized values. Learning and intelligent compounding consume finalized ledger and treasury truth, not synthetic or injected outcomes.

## Recovery and replay
Durable state must survive process restart, service restart, delayed receipts, transaction replacement, dropped transactions, confirmation depth, and reorgs. Persist pending state, nonce ownership, replacement lineage, lifecycle state, admission evidence, and idempotent settlement state.

Replay must capture scanner and quote inputs, RPC requests/results, block identity, market/token metadata, conversion evidence, treasury/family/governance/risk/goal state, seeds, policies, sizing, calldata, gas, simulation, receipt, decoded event, PnL, settlement, and lifecycle evidence. Incomplete replay must say `incomplete` or `non_deterministic`, never claim deterministic proof.

## Operator authority
Operator and mobile state must reconstruct from authoritative persisted state and expose authority, freshness, lifecycle, capital, execution, risk, degraded, and recovery markers. Demo snapshots, injected summaries, stale fallbacks, and in-memory-only values must not appear as authoritative live capital truth.

## Latency
Latency is a first-class economic objective: optimize opportunity freshness, quote/RPC, decision, portfolio selection, admission, simulation, signing, submission, receipt, opportunity-to-submission, and opportunity-to-settlement latency. The eventual decision rule must reject when opportunity age plus estimated remaining latency plus safety margin exceeds economic freshness horizon, and profitability must model deterioration. Speed never overrides profitability, capital truth, risk, stale-opportunity rejection, governance, rollout readiness, or fail-closed behavior. Existing timing instrumentation must be preserved.

## Safe evolution and prohibited shortcuts
Prefer additive, small, reviewable changes with focused tests. Never weaken gates to make tests pass, invent economics or provenance, silently mix denominations, bypass canonical admission, enable extra families, accept contradictory PnL, present synthetic fixtures as production proof, or claim unexecuted tests passed. Documentation never authorizes live trading. Actual runtime gates remain authoritative.

## Stage 1 truth
Stage 1 is a characterization fixture, not a proven production closed loop. It uses synthetic enrichment, handoffs, transaction hash, receipt, and settlement context. Its known economics are `gasUsed=21,000`, `effectiveGasPrice=1`, gas cost `21,000`; with event profit `50`, realized after gas is `max(0, 50 - 21,000) = 0`. Do not repair or reinterpret this fixture as part of documentation work.
