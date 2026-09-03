# Authority Decision Packet

## Purpose and status

This is the canonical owner-review index for the seven unresolved economic authorities. Detailed repository evidence remains in [`WORKSPACE_CHECKPOINT.md`](WORKSPACE_CHECKPOINT.md), [`AUTHORITY_SOURCE_MAP.md`](AUTHORITY_SOURCE_MAP.md), and [`ECONOMIC_IDENTITY_DESIGN.md`](ECONOMIC_IDENTITY_DESIGN.md).

**Classification rule:** repository facts are not policy approval. Candidate designs are not implementation authorization. The seven decisions below remain **UNRESOLVED**.

**Repository:** `AlekWisoky/sovereign_capital_project`  
**Branch:** `architecture-c-contract-tests`  
**Documentation-only scope:** no runtime, test, persistence, configuration, settlement, ABI, or trading behavior changes.

## Decisions already made

These are documented engineering checkpoints or policy boundaries evidenced by committed repository state, not new financial approvals:

- The durable workspace checkpoint protocol exists in `docs/WORKSPACE_CHECKPOINT.md`.
- The economic identity hierarchy is documented as a **candidate architecture** in `docs/ECONOMIC_IDENTITY_DESIGN.md`.
- The read-only authority inventory exists in `docs/AUTHORITY_SOURCE_MAP.md`.
- Architecture C is contract/policy-approved but runtime-unwired.
- Borrowed principal is not automatically internal treasury capital.
- Missing, stale, contradictory, ambiguous, non-authoritative, or unreconciled critical state must fail closed.
- Checked-in execution defaults remain `dry_run: true` and `auto_trading: false`; live trading is disabled at repository level.
- Documentation is durable project memory, not runtime authorization.

## Decisions explicitly NOT made

The repository has not approved:

- treasury denomination;
- conversion authority;
- provider capacity authority;
- provider fee authority;
- exposure formula;
- reservation semantics;
- economic identity origin or persistence policy;
- freshness or TTL policy;
- finality policy;
- replacement policy;
- reorg policy;
- retention/privacy policy;
- multi-fill semantics.

## 1. Treasury denomination and reservation authority

**Why it matters:** available capital, encumbrance, reservation, and release cannot be safe while token-native amounts, wei-shaped scalars, USD projections, bankroll values, and InternalPrime collateral have competing meanings.

**Current evidence:** `TreasuryLedger` in `backend/victor_ai_bot/treasury/ledger.py` records asset/liability/equity/encumbrance concepts. `LedgerRepository` persists transaction journals. `CapitalTruthService` reconciles treasury, bankroll, ledger, InternalPrime, histories, and capital events. InternalPrime persists collateral, inventory, family exposure, and loans.

**Conflicts:** ledger assets, USD projections, `deployable_bankroll_wei`, family allocations, bankroll sizing, InternalPrime USD collateral, JSON mirrors, and SQLite state are not one authority. No generic reservation authority exists. **Classification: CONFLICTING / PARTIALLY_PROVEN.**

**Candidates:** (A) asset-specific ledger truth; (B) explicit chain/account treasury scope; (C) multi-asset treasury with explicit projections. A+B+C is the current engineering candidate: native balances scoped by chain/account/asset, with projections derived through explicit conversion. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A preserves units and replay but complicates cross-asset allocation. B prevents cross-chain/account aggregation but increases reconciliation scope. C supports allocation and reporting but makes conversion authority mandatory.

**Dependencies and consequences:** TreasurySnapshot, decimal authority, conversion, exposure, reservation concurrency, settlement posting, and next allocation depend on this decision. Choosing USD or generic wei would risk double counting and dimensional errors. Choosing native assets requires explicit projection policy.

**Owner decision required:** canonical scope, units, available/reserved/encumbered formulas, custody reconciliation, treasury revision, and reservation authority. **Status: UNRESOLVED.**

## 2. Conversion and decimal authority

**Why it matters:** gas, profit, fees, slippage, treasury values, and limits may use different assets and decimals.

**Current evidence:** `usd_pricing.py` uses block-tagged UniV3 quotes. `RuntimeReceiptFacade` converts gas to profit-token and optional USD units. `capital_demand.py: ConversionEvidence` defines rational conversion, direction, age, and rounding. **Classification: PARTIALLY_PROVEN / HEURISTIC.**

**Conflicts:** six-decimal stablecoin assumptions, configured USDC/USDT-as-USD, market quotes, accounting values, and fallback `_realized_usd_from_wei` behavior. **Classification: CONFLICTING.**

**Candidates:** (A) execution-asset-native accounting; (B) block-pinned market conversion; (C) approved oracle/accounting conversion. Current engineering candidate: A for execution and settlement, B for executable cross-asset economics, and separately governed C for reporting. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A is dimensionally strongest but does not compare assets. B reflects market state but depends on liquidity and historical state. C stabilizes reporting but can diverge from executable value.

**Dependencies and consequences:** ConversionSnapshot, decimals, PnL, treasury projections, exposure, replay, and rounding all depend on this decision. Missing or conflicting conversion must block any future cross-asset authority.

**Owner decision required:** decimal source, source hierarchy, stablecoin/depeg treatment, rounding, block/hash requirements, and USD role. **Status: UNRESOLVED.**

## 3. Provider capacity and fee authority

**Why it matters:** configured fees and provider multipliers do not prove borrowable capacity or actual callback cost.

**Current evidence:** `flashloan_sizing.py: choose_flashloan_size` uses `_PROVIDER_LIMITS`, scores, safe curves, and fragility caps. `VictorArbExecutor.sol` supports Aave and Balancer callbacks; Aave premium and Balancer fee amounts arrive on-chain. **Classification: HEURISTIC pretrade sizing / PARTIALLY_PROVEN callback evidence.**

**Conflicts:** configured `flashloan_fee_bps`, dimensionless provider limits, provider scores, and callback fee. Maker/Uniswap appear in heuristic sizing but are not supported by the executor’s provider branches. **Classification: CONFLICTING.**

**Candidates:** (A) configuration authority; (B) measured provider capacity/fee snapshots; (C) callback-only fee authority. Current engineering candidate: separate ProviderCapacitySnapshot and ProviderFeeSnapshot, measured before execution, with callback fee authoritative after execution. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A is simple but not live authority. B supports fail-closed admission but requires provider adapters and revisions. C is strong for settlement but too late for pretrade admission.

**Dependencies and consequences:** Demand, exposure, execution plan, profitability, settlement, and replay depend on provider evidence. Stale or unavailable capacity/fee must block future live admission.

**Owner decision required:** supported providers, query method, fee precedence, revision, freshness, and safety haircut. **Status: UNRESOLVED.**

## 4. Worst-case exposure/liability model

**Why it matters:** gas, slippage, flash fees, collateral, pending attempts, replacement, reorg, and recovery costs can be independent, correlated, nested, or mutually exclusive.

**Current evidence:** execution, risk, drawdown, kill-switch, capture, InternalPrime, and capital truth track separate pieces. Complete replacement/reorg/recovery liability composition is absent. **Classification: PARTIALLY_PROVEN / UNPROVEN.**

**Candidates:** (A) vector-preserving; (B) conservative maximum; (C) additive; (D) vector plus policy-specific scenario projections. Current engineering candidate: D. Preserve an ExposureVector, then apply approved additive/max/correlation rules only at named policy boundaries. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A preserves units but needs projections. B is simple for mutually exclusive scenarios but can omit simultaneous liabilities. C is transparent but can double count. D is expressive but requires explicit risk policy.

**Dependencies and consequences:** ExposureSnapshot must bind plan, provider, gas, conversion, reservation, pending lineage, and policy revision. Demand, reservation, risk, release, and replay cannot be proven without it.

**Owner decision required:** dimensions, overlap/correlation, replacement/reorg bounds, recovery reserve, and scalar limits. **Status: UNRESOLVED.**

## 5. Strategy budget and concurrent reservation semantics

**Why it matters:** previewing capital does not prevent two opportunities from consuming the same capital or family allowance.

**Current evidence:** `CapitalAdmissionService.evaluate` previews requested notional and source policy. InternalPrime performs specialized inventory/loan allocation and settlement. Family targets and allocations are projections. Generic reservations are absent. **Classification: PARTIALLY_PROVEN / UNPROVEN.**

**Candidates:** (A) scalar reservation; (B) vector reservation; (C) family-budget reservation; (D) vector reservation constrained by family/global budgets. Current engineering candidate: D. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A is simple but loses units. B protects asset/liability dimensions but is more complex. C controls strategy allocation but cannot prevent asset double spending. D covers both but needs atomic revision and concurrency semantics.

**Dependencies and consequences:** Treasury, exposure, identity, reservation repository, pending lifecycle, replacement/reorg policy, and settlement release depend on this decision. No reservation writes are authorized yet.

**Owner decision required:** atomicity, state machine, expiry, replacement, release, dispute, reorg, family budget meaning, and concurrency model. **Status: UNRESOLVED.**

## 6. Durable economic identity

**Why it matters:** retries and transaction replacements must not be counted as new economic trades.

**Current evidence:** the repository contains `Opportunity.id`, `route_id`, optional `intent_id`, replay decision/event IDs, `tx_hash`, receipt IDs, ledger transaction IDs, `capitalCommitId`, InternalPrime loan IDs, and request IDs. Authority snapshot tests require correlation to remain distinct from tx hash, plan, commit, and replay identity. **Classification: PARTIALLY_PROVEN components / UNPROVEN universal identity.**

**Candidate architecture:** `economic_intent -> reservation -> execution_plan -> transaction_attempt -> replacement_lineage -> receipt -> settlement -> ledger_transaction -> replay_event`, documented in `docs/ECONOMIC_IDENTITY_DESIGN.md`. This is a **CANDIDATE**, not approved policy.

**Advantages/disadvantages:** route ID is stable but incomplete; tx hash is concrete but attempt-specific; capitalCommitId is useful but begins at settlement; an intent root preserves lineage but requires new persistence and owner-approved semantics.

**Dependencies and consequences:** identity origin/persistence must precede reservation, lifecycle recovery, settlement linkage, replay, and any runtime integration. Missing identity must fail closed for future live-capable paths.

**Owner decision required:** creation point, multiple fills, cross-chain scope, replacement/cancellation, finality/reorg, privacy/retention, and disputed-state ownership. **Status: UNRESOLVED.**

## 7. Opportunity freshness and empirical latency policy

**Why it matters:** quote age, block age, treasury revisions, provider changes, risk state, and remaining execution latency can become stale independently.

**Current evidence:** `LatencySpan`/`LatencyProfiler`, receipt timing, block-tagged quote caches, scanner budgets, execution deadlines, and CapitalTruthService freshness classes exist. **Classification: PARTIALLY_PROVEN instrumentation / HEURISTIC stale-risk.**

**Conflicts:** wall-clock age, block age, source revision, quote drift, and in-memory telemetry are not one decision authority. **Classification: CONFLICTING.**

**Candidates:** (A) scalar TTL; (B) block-age policy; (C) source-specific TTLs; (D) multidimensional FreshnessSnapshot. Current engineering candidate: D, with no numerical horizons invented before measurement. **This recommendation is NOT approved policy.**

**Advantages/disadvantages:** A is simple but hides source conflicts. B handles chain state but misses off-chain state. C is better but still incomplete across interacting inputs. D is expressive but requires durable traces and empirical policy.

**Dependencies and consequences:** FreshnessSnapshot, DecisionSnapshot validation, demand, admission, simulation, execution, provider capacity, and replay depend on this decision.

**Owner decision required:** dimensions, horizons, block/time tolerance, remaining-latency model, safety margin, and mandatory blockers. **Status: UNRESOLVED.**

## Cross-reference and implementation boundary

The operational checkpoint is [`WORKSPACE_CHECKPOINT.md`](WORKSPACE_CHECKPOINT.md). The static source inventory is [`AUTHORITY_SOURCE_MAP.md`](AUTHORITY_SOURCE_MAP.md). The candidate identity model is [`ECONOMIC_IDENTITY_DESIGN.md`](ECONOMIC_IDENTITY_DESIGN.md). The Sovereign OS documents remain the historical constitution, state, decisions, and changelog.

Until owner approval and evidence exist, do not implement snapshot types, adapters, reservations, CapitalDemandComposer, DecisionEngine integration, settlement/PnL changes, execution changes, Solidity/ABI changes, configuration changes, or live trading.

## Dependency matrix

| Decision | Dependent components | Blocked components | Required evidence |
|---|---|---|---|
| Treasury | TreasurySnapshot, capital truth, ledger, reservation | Demand, reservations, next allocation | custody scope, units, revisions, reconciliation |
| Conversion | ConversionSnapshot, PnL, treasury projections | cross-asset demand/settlement | decimals, source hierarchy, depeg, rounding |
| Provider | capacity/fee snapshots, sizing, execution, settlement | provider-aware live admission | capacity/fee reads, revisions, freshness |
| Exposure | ExposureSnapshot, risk, demand, reservation | scalar risk limits | dimensions, overlap, reorg/recovery bounds |
| Budget/reservation | ReservationSnapshot, treasury revision, family policy | concurrent admission/release | atomicity, concurrency, expiry, release, reorg |
| Identity | lifecycle records, replay, operator | restart/replacement proof | origin, uniqueness, parent-child and reorg semantics |
| Freshness | FreshnessSnapshot, admission, execution, replay | stale-opportunity rejection | empirical age/latency curves and safety margins |

## Status summary

All seven decisions remain **UNRESOLVED**. Repository evidence insufficient - owner decision required.

## Documentation-only safety boundary

This packet changes no runtime behavior, persistence, tests, production configuration, settlement/PnL semantics, Solidity/ABI, signing, submission, strategy activation, or live-trading state.
