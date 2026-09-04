# Authority Source Map

## Status

This is a read-only architecture inventory for Phase 3. It records repository facts and does not promote any heuristic, projection, configuration value, or test fixture into authority. The seven authority decisions remain **UNRESOLVED**.

Verified against branch `architecture-c-contract-tests`, HEAD `b70c572c5c36b927f3395365d3e57d2cf9567e31` and the surviving source/documentation artifacts.

## Source inventory

| Authority | Current Source | Fact Represented | Units | Revision | Persistence | Classification | Conflicts | Read-only Safe? |
|---|---|---|---|---|---|---|---|---|
| Treasury/capital truth | `backend/victor_ai_bot/treasury/ledger.py: TreasuryLedger`; `backend/victor_ai_bot/persistence/repositories/ledger_repository.py: LedgerRepository`; `backend/victor_ai_bot/runtime_services/capital_truth_service.py: CapitalTruthService` | Ledger transactions, asset/liability/equity/encumbrance projections, reconciliation across treasury, bankroll, InternalPrime, histories, and capital events | Mixed asset amounts, USD, float projections, legacy wei-shaped scalars | Ledger transaction IDs, capital commit IDs, timestamps; no single treasury revision authority | JSONL ledger, SQLite repository, JSON mirrors, histories, capital events | `PARTIALLY_PROVEN`, `CONFLICTING` | Asset-native values conflict with USD/wei/bankroll/family projections; mirrors can diverge; no generic reservation authority | Read paths are observational; no canonical snapshot adapter exists |
| Bankroll sizing | `backend/victor_ai_bot/bankroll.py: BankrollManager` | Realized-profit state, reinvestment, Kelly/volatility sizing, next amount | `wei`-named integers and configuration-derived values | State timestamps and history events | JSON state plus bankroll/capital-event repositories | `HEURISTIC`, `PARTIALLY_PROVEN` | Not equivalent to settled asset liquidity, treasury availability, or strategy-budget authority | `next_amount_in()` mutates state/history; read-only use requires a non-mutating projection |
| Internal capital/prime | `backend/victor_ai_bot/internal_prime/allocator.py: InternalPrimeAllocator`; `contracts.py: PrimeBorrowRequest, PrimeLoanPosition`; `inventory.py: InventoryPool` | USD notional, borrowed USD, collateral, family exposure, inventory, open/disputed loans | USD floats and asset inventory floats | Loan IDs, request IDs, `updatedTsMs`, state snapshots | JSON state/inventory, SQLite state repository, ledger transactions, capital events | `PARTIALLY_PROVEN`, specialized only | Specialized allocator is not generic reservation authority; USD collateral conflicts with asset-native ledger semantics | `snapshot()` is read-only; allocation/settlement mutate |
| Asset/decimal metadata | `backend/victor_ai_bot/config.py: ChainConfig`; `backend/config/*.yaml`; contract token addresses in `contracts/src/VictorArbExecutor.sol` | Chain IDs, token addresses, WETH/USDC/USDT configuration, executor dependencies | Address identity; decimals usually assumed elsewhere, not universally sourced | Config path/version only; no decimal metadata revision | YAML/config objects; contract deployment state external to repo | `PARTIALLY_PROVEN`, `CONFLICTING` | `usd_pricing.py` assumes six-decimal USDC/USDT; no universal token decimal authority or on-chain metadata snapshot | Config reads are read-only; live authority is configuration-dependent |
| Conversion/valuation | `backend/victor_ai_bot/usd_pricing.py`; `backend/victor_ai_bot/capital_demand.py: ConversionEvidence` | Block-tagged UniV3 conversion, gas-to-token/USD projections, rational conversion contract semantics | Token-native units, USD micro-units, configured stable assumptions | Block number for quotes; source/time/max age in `ConversionEvidence`; no universal revision | Per-block cache and runtime/PnL fields | `PARTIALLY_PROVEN`, `HEURISTIC` for USD fallback | Stablecoin-as-USD, decimal assumptions, fallback conversion, quote versus accounting authority | Quote functions can be read-only; cache reads are observational |
| Provider capacity | `backend/victor_ai_bot/execution_capture/flashloan_sizing.py: choose_flashloan_size`; provider config and runtime metadata | Provider selection, safe-size curve, provider limits, scores, caps | Dimensionless multipliers, USD/expected-profit fields, route-specific metadata | Runtime/config timestamps; no provider capacity revision | Runtime metadata, replay, telemetry | `HEURISTIC`, `UNPROVEN` as live authority | `_PROVIDER_LIMITS` and provider scores are not measured capacity; executor only supports Aave/Balancer callbacks | Sizing is read-oriented but may consume mutable runtime inputs; no authoritative adapter |
| Provider fees | `backend/victor_ai_bot/config.py: ExecutionConfig.flashloan_fee_bps`; `contracts/src/VictorArbExecutor.sol: executeOperation, receiveFlashLoan`; `backend/victor_ai_bot/executor_events.py` | Configured fee assumption pretrade; actual Aave premium/Balancer fee callback and emitted provider | Bps assumption or asset-native callback amount | Config revision versus receipt/provider callback evidence; no common fee revision | Config, receipt/PnL, replay | `PARTIALLY_PROVEN`, `CONFLICTING` | Configured fee can diverge from provider callback; fee authority is not separated from capacity | Contract/event reads are observational; provider adapter absent |
| Risk state | `backend/victor_ai_bot/risk_engine/`; drawdown/kill-switch modules; `backend/victor_ai_bot/runtime_services/execution_service.py` and admission helpers | Drawdown, kill switch, risk multipliers, execution and family gates | Mixed percentages, USD/wei-shaped values, booleans | Policy/config revisions are not unified; runtime state timestamps vary | Runtime state, JSON/history, audit/capital recovery where configured | `PARTIALLY_PROVEN` | Optional hooks can be swallowed; no single immutable RiskSnapshot | Individual reads may be observational; gate calls can mutate/audit |
| Governance state | `backend/victor_ai_bot/governance/`; `backend/victor_ai_bot/runtime_services/runtime_execute_dispatch_facade.py`; `ExecutionService.handle_governance_pre_execute` | Governance pre-execution decisions, readiness, operator controls | Flags, decisions, policy values | Config and runtime state; no universal governance revision | Runtime/control/audit state | `PARTIALLY_PROVEN` | Canonical auto path is tested, but universal manual/API/direct coverage is not proven | Read-only inspection is possible; handler invocation may mutate/audit |
| Goal state | `backend/victor_ai_bot/runtime_services/wealth_goal_service.py`; treasury goal config in `backend/victor_ai_bot/config.py` | Goal posture, aggressiveness cap, pacing, capital commitment posture | Percentages, risk labels, target values | Goal history/config timestamps; no universal GoalSnapshot revision | JSON/state/history and treasury metadata | `PARTIALLY_PROVEN`, `HEURISTIC` for sizing influence | Goal influence is fragmented; goal cannot authorize a trade, and mandatory final-notional causality is unproven | State reads may be observational; service methods may persist |
| Execution plan | `backend/victor_ai_bot/execution.py`; `calldata_builder.py`; `route_encoding.py`; `runtime_services/runtime_execute_dispatch_facade.py`; test-only `ExecutionPlanSnapshot` | Route, amount, min-outs, provider, fees, gas, calldata, deadline, simulation assumptions | Token-native integers, gas wei, config values | Route ID, deadlines, ABI version, test-only content hash; no production plan revision authority | Runtime metadata, PnL expected rows, replay bundles | `PARTIALLY_PROVEN`, `CONFLICTING` identity | Route ID can survive amount/quote/slippage mutation; final plan is not a universal immutable snapshot | Plan construction is not a pure read; future snapshot must be separate from execution |
| Opportunity/quote evidence | `backend/victor_ai_bot/arb_engine.py`; `runtime_services/runtime_primary_scan_facade.py`; quote adapters; `models.py` | Quotes, route legs, min-outs, block-derived opportunity and route identity | Asset-native integers and quote metadata | Block-derived opportunity IDs, per-block cache keys | Runtime memory, replay summaries, cache | `PROVEN` with mocks; `PARTIALLY_PROVEN` live | Exact RPC inputs/results, block hash/state, token decimals, and complete quote cache are not durable | Scanner/quote reads can be observational; network/cache calls are not pure snapshot construction |
| Freshness/latency evidence | `backend/victor_ai_bot/latency_profiler.py: LatencySpan, LatencyProfiler`; receipt timing; `CapitalTruthService` freshness classes; quote block tags | Stage durations, rolling p50/p90/p99, submit-to-receipt timing, source timestamps, stale probabilities | Milliseconds, blocks, timestamps, source age | In-memory rolling windows, timestamps, block tags; no policy revision/horizon authority | Mostly memory, runtime telemetry, histories | `PARTIALLY_PROVEN`, `HEURISTIC` for stale-risk | Telemetry explicitly does not decide; no empirical TTL, multidimensional envelope, or durable trace | Profiler reads are observational; timing itself uses clock and is not deterministic authority |
| Economic identity | `models.py: Opportunity`; replay IDs in `runtime_subsystems/replay_store.py`; PnL tx hash; ledger transaction IDs; capital commit IDs; InternalPrime loan/request IDs; test-only correlation field | Discovery, route, decision/replay, attempt, receipt, settlement, journal, and loan lineage fragments | String IDs and hashes | Mixed deterministic/content/time/UUID IDs; no universal revision | Runtime memory, SQLite, JSONL, replay JSON, capital events | `PARTIALLY_PROVEN`, `UNPROVEN` universal | No durable identity spans retries/replacements/reorgs; tx hash, route ID, and capitalCommitId begin at different stages | Existing ID reads are observational; identity creation would be a behavior change |

## Repository facts versus recommendations

### Repository facts

- `TreasuryLedger` and `LedgerRepository` are the strongest existing accounting foundations, but they do not establish one canonical treasury denomination or reservation authority.
- `CapitalTruthService` is a reconciliation/read service over several institutional sources, not a transactional reservation authority.
- `ConversionEvidence` and the authority snapshot test are contract/test-level boundaries; they do not select live sources.
- Provider capacity limits and scores in `flashloan_sizing.py` are heuristics. The executor contract supports Aave and Balancer callbacks and exposes actual callback fee data only after execution reaches the provider.
- `LatencyProfiler` is observability-only by design. Its metrics are not freshness policy.
- The current identity sources form partial lineage, not a universal economic identity.

### Recommendations requiring owner approval

- Do not promote any current heuristic, configuration value, or USD projection to authority without a policy decision.
- Prefer future read-only adapters that return immutable snapshots or explicit `UNRESOLVED / NON-AUTHORITATIVE` status.
- Keep authority acquisition outside the future pure `CapitalDemandComposer`.
- Treat missing, stale, contradictory, or unscoped critical evidence as a fail-closed read result.
- Keep the proposed economic identity hierarchy in `docs/ECONOMIC_IDENTITY_DESIGN.md` as a candidate until identity policy is approved.

## Read-only snapshot contract boundary

No production snapshot types were added in this milestone. The repository has no clearly approved production module for them that would not accidentally wire runtime behavior or select unresolved policy. The existing `backend/tests/test_authority_snapshot_contracts.py` remains explicitly `TEST_ONLY_SYNTHETIC` and covers immutable, provenance-bearing, revision-aware, freshness-aware, conflict-aware contracts with injected evaluation time.

Future read-only contracts should include, at minimum:

- explicit source/asset/account identity;
- integer or otherwise declared units and decimals;
- provenance and source revision;
- observed time and block/hash where relevant;
- freshness status and horizon policy reference;
- conflict/unavailability state;
- immutable content identity;
- no I/O or mutation during validation.

Candidate adapter boundaries, not implementations:

- `read_treasury_snapshot(...)`
- `read_conversion_snapshot(...)`
- `read_provider_capacity_snapshot(...)`
- `read_provider_fee_snapshot(...)`
- `read_exposure_snapshot(...)`
- `read_risk_snapshot(...)`
- `read_governance_snapshot(...)`
- `read_goal_snapshot(...)`
- `read_freshness_snapshot(...)`
- `read_execution_plan_snapshot(...)`
- `read_decision_snapshot(...)`

## Decision preservation

All seven authority decisions remain **UNRESOLVED**:

1. Treasury denomination and reservation authority.
2. Conversion and decimal authority.
3. Provider capacity and fee authority.
4. Worst-case exposure/liability formula.
5. Strategy budget and concurrent reservation semantics.
6. Durable economic/trade correlation identity.
7. Opportunity freshness and empirical latency horizons.

This map does not approve a candidate, create persistence, or authorize runtime integration.
