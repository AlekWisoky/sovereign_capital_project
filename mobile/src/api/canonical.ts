import { apiGet } from './client';
import type {
  ActivityFeed,
  CapitalTruth,
  CanonicalSystemSnapshot,
  DecisionSnapshot,
  InternalPrime,
  LiveTrade,
  OmarState,
  Opportunity,
  RiskState,
  RuntimeHealth,
  TransactionRecord,
  WealthGoal,
} from '../domain/canonical';

const record = (value: unknown): Record<string, any> => (value && typeof value === 'object' ? value as Record<string, any> : {});
const num = (value: unknown): number | undefined => {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};
const text = (value: unknown): string | undefined => value === undefined || value === null ? undefined : String(value);
const bool = (value: unknown): boolean | undefined => typeof value === 'boolean' ? value : undefined;

function lineage(raw: Record<string, any>) {
  return {
    decisionId: text(raw.decision_id ?? raw.decisionId),
    correlationId: text(raw.correlation_id ?? raw.correlationId),
    executionId: text(raw.execution_id ?? raw.executionId),
    receiptId: text(raw.receipt_id ?? raw.receiptId),
    outcomeId: text(raw.outcome_id ?? raw.outcomeId),
    sizingId: text(raw.sizing_id ?? raw.sizingId),
    opportunityId: text(raw.opportunity_id ?? raw.opportunityId ?? raw.id),
    routeId: text(raw.route_id ?? raw.routeId),
    action: text(raw.action),
  };
}

export function normalizeRuntimeHealth(raw: unknown): RuntimeHealth {
  const r = record(raw);
  return {
    ok: bool(r.ok),
    status: text(r.status),
    reasonCode: text(r.reason_code ?? r.reasonCode),
    deploymentMode: text(r.deployment_mode ?? r.deploymentMode ?? r.mode),
    autoTrading: bool(r.auto_trading ?? r.autoTrading),
    dryRun: bool(r.dry_run ?? r.dryRun),
    sendMode: text(r.send_mode ?? r.sendMode),
    version: text(r.version),
    commitSha: text(r.commit_sha ?? r.commitSha ?? r.sha),
    observedTsMs: num(r.observed_ts_ms ?? r.observedTsMs ?? Date.now()),
  };
}

export function normalizeCapitalTruth(raw: unknown): CapitalTruth {
  const r = record(raw);
  const nested = record(r.capitalTruth ?? r.capital_truth ?? r.health ?? r.summary);
  return {
    ok: bool(nested.ok ?? r.ok),
    status: text(nested.status ?? r.status),
    reasonCode: text(nested.reason_code ?? nested.reasonCode ?? r.reason_code ?? r.reasonCode),
    freshnessClass: text(nested.freshness_class ?? nested.freshnessClass),
    reliabilityClass: text(nested.reliability_class ?? nested.reliabilityClass),
    availableCapitalUsd: num(nested.available_capital_usd ?? nested.availableCapitalUsd),
    settledCapitalUsd: num(nested.settled_capital_usd ?? nested.settledCapitalUsd),
    realizedPnlUsd: num(nested.realized_pnl_usd ?? nested.realizedPnlUsd),
    reinvestableProfitUsd: num(nested.reinvestable_profit_usd ?? nested.reinvestableProfitUsd),
    updatedTsMs: num(nested.updated_ts_ms ?? nested.updatedTsMs),
  };
}

function normalizeOpportunity(raw: unknown): Opportunity {
  const r = record(raw);
  return {
    ...lineage(r),
    id: text(r.id ?? r.opportunity_id ?? r.opportunityId),
    title: text(r.title ?? r.name),
    family: text(r.family),
    strategyFamily: text(r.strategy_family ?? r.strategyFamily),
    expectedGrossProfitUsd: num(r.expected_gross_profit_usd ?? r.expectedGrossProfitUsd ?? r.gross_profit_usd),
    expectedNetProfitUsd: num(r.expected_net_profit_usd ?? r.expectedNetProfitUsd ?? r.net_profit_usd),
    expectedRoiPct: num(r.expected_roi_pct ?? r.expectedRoiPct ?? r.roi_pct),
    requiredCapitalUsd: num(r.required_capital_usd ?? r.requiredCapitalUsd),
    confidence: num(r.confidence),
    pSuccess: num(r.p_success ?? r.pSuccess),
    marginRatio: num(r.margin_ratio ?? r.marginRatio),
    gasRatio: num(r.gas_ratio ?? r.gasRatio),
    mode: text(r.mode),
    lifecycle: text(r.lifecycle ?? r.stage),
    admitted: bool(r.admitted),
    blocked: bool(r.blocked),
    reasonCodes: Array.isArray(r.reason_codes ?? r.reasonCodes) ? (r.reason_codes ?? r.reasonCodes).map(String) : undefined,
  };
}

export function normalizeTransaction(raw: unknown): TransactionRecord {
  const r = record(raw);
  const economics = record(r.economics ?? r.settlement ?? r.outcome);
  return {
    ...lineage(r),
    transactionId: text(r.transaction_id ?? r.transactionId ?? r.id),
    txHash: text(r.tx_hash ?? r.txHash ?? r.hash),
    receiptId: text(r.receipt_id ?? r.receiptId),
    status: typeof (r.status ?? economics.status) === 'number' ? Number(r.status ?? economics.status) : text(r.status ?? economics.status),
    timestampMs: num(r.timestamp_ms ?? r.timestampMs ?? r.ts_ms ?? (Number(r.ts) * 1000)),
    chain: text(r.chain),
    provider: text(r.provider ?? r.venue ?? r.endpoint ?? r.relay),
    route: text(r.route ?? r.route_id ?? r.routeId),
    family: text(r.family ?? r.strategy_family ?? r.strategyFamily),
    amountInUsd: num(r.amount_in_usd ?? r.amountInUsd ?? economics.amount_in_usd),
    gasCostUsd: num(r.gas_cost_usd ?? r.gasCostUsd ?? economics.gas_cost_usd),
    borrowCostUsd: num(r.borrow_cost_usd ?? r.borrowCostUsd ?? economics.borrow_cost_usd),
    realizedNetProfitUsd: num(r.realized_net_profit_usd ?? r.realizedNetProfitUsd ?? r.net_realized_usd ?? economics.net_realized_usd),
    signedPnlUsd: num(r.signed_pnl_usd ?? r.signedPnlUsd ?? economics.signed_pnl_usd),
    success: bool(r.success),
    settlementVerified: bool(r.settlement_verified ?? r.settlementVerified ?? economics.settlement_verified),
  };
}

function liveState(tx: TransactionRecord): LiveTrade['state'] {
  const status = String(tx.status ?? '').toLowerCase();
  if (tx.settlementVerified) return 'settled';
  if (status.includes('fail') || tx.success === false) return 'failed';
  if (status.includes('confirm') || status === '1') return 'confirmed';
  if (status.includes('submit') || status.includes('pending')) return 'submitted';
  return 'unknown';
}

export async function getCommandCenterSnapshot(baseUrl: string, adminKey?: string): Promise<Record<string, any>> {
  return record(await apiGet(baseUrl, '/api/commandcenter/snapshot', adminKey ? { 'X-Admin-Key': adminKey } : undefined));
}

export async function getRuntimeHealth(baseUrl: string): Promise<RuntimeHealth> {
  return normalizeRuntimeHealth(await apiGet(baseUrl, '/health'));
}

export async function getFundSummary(baseUrl: string, adminKey?: string): Promise<Record<string, any>> {
  return record(await apiGet(baseUrl, '/api/fund/summary', adminKey ? { 'X-Admin-Key': adminKey } : undefined));
}

export async function getSpreadOpportunities(baseUrl: string, adminKey?: string): Promise<Opportunity[]> {
  const raw = record(await apiGet(baseUrl, '/api/spread/opportunities', adminKey ? { 'X-Admin-Key': adminKey } : undefined));
  const rows = Array.isArray(raw.opps) ? raw.opps : Array.isArray(raw.items) ? raw.items : [];
  return rows.map(normalizeOpportunity);
}

export async function getXaiLatest(baseUrl: string, limit = 20, adminKey?: string): Promise<DecisionSnapshot[]> {
  const raw = await apiGet(baseUrl, `/api/xai/latest?limit=${encodeURIComponent(String(limit))}`, adminKey ? { 'X-Admin-Key': adminKey } : undefined);
  const rows = Array.isArray(raw) ? raw : Array.isArray(record(raw).items) ? record(raw).items : [];
  return rows.map((row) => ({ ...lineage(record(row)), ...record(row) })) as DecisionSnapshot[];
}

export async function getXaiDecision(baseUrl: string, decisionId: string, adminKey?: string): Promise<DecisionSnapshot> {
  const raw = record(await apiGet(baseUrl, `/api/xai/decision/${encodeURIComponent(decisionId)}`, adminKey ? { 'X-Admin-Key': adminKey } : undefined));
  const r = record(raw.decision ?? raw);
  return {
    ...lineage(r),
    expectedNetProfitUsd: num(r.expected_net_profit_usd ?? r.expectedNetProfitUsd ?? r.expected_net),
    expectedRoiPct: num(r.expected_roi_pct ?? r.expectedRoiPct),
    requiredCapitalUsd: num(r.required_capital_usd ?? r.requiredCapitalUsd),
    proposedBorrowAmount: text(r.proposed_borrow_amount ?? r.proposedBorrowAmount ?? r.borrow_amount),
    borrowMult: num(r.borrow_mult ?? r.borrowMult),
    sizeMult: num(r.size_mult ?? r.sizeMult),
    pSuccess: num(r.p_success ?? r.pSuccess),
    action: text(r.action),
    strategyFamily: text(r.strategy_family ?? r.strategyFamily ?? r.family),
    governanceAllowed: bool(r.governance_allowed ?? r.governanceAllowed),
    admissionAllowed: bool(r.admission_allowed ?? r.admissionAllowed),
    admissionReasonCodes: Array.isArray(r.admission_reason_codes ?? r.admissionReasonCodes) ? (r.admission_reason_codes ?? r.admissionReasonCodes).map(String) : undefined,
    settlementVerified: bool(r.settlement_verified ?? r.settlementVerified),
    realizedNetProfitUsd: num(r.realized_net_profit_usd ?? r.realizedNetProfitUsd ?? r.realized_net),
    expectationErrorUsd: num(r.expectation_error_usd ?? r.expectationErrorUsd ?? r.expectation_error),
    learningRecorded: bool(r.learning_recorded ?? r.learningRecorded ?? r.learned),
  };
}

export async function getActivityFeed(baseUrl: string, adminKey?: string, limit = 50): Promise<ActivityFeed> {
  const fund = await getFundSummary(baseUrl, adminKey);
  const ledger = record(fund.ledger);
  const rows = Array.isArray(ledger.transactions) ? ledger.transactions : Array.isArray(ledger.tail) ? ledger.tail : [];
  const transactions = rows.slice(-limit).reverse().map(normalizeTransaction);
  return {
    transactions,
    liveTrades: transactions
      .filter((tx) => !tx.settlementVerified && tx.txHash)
      .map((tx) => ({ ...tx, state: liveState(tx) })),
    decisions: [],
  };
}

export async function getCanonicalSystemSnapshot(baseUrl: string, adminKey?: string): Promise<CanonicalSystemSnapshot> {
  const [health, fund, opportunities, decisions] = await Promise.all([
    getRuntimeHealth(baseUrl),
    getFundSummary(baseUrl, adminKey),
    getSpreadOpportunities(baseUrl, adminKey),
    getXaiLatest(baseUrl, 20, adminKey),
  ]);
  const capital = normalizeCapitalTruth(fund);
  const summary = record(fund.summary ?? fund);
  const internalPrimeRaw = record(fund.internalPrime ?? fund.internal_prime);
  const goalRaw = record(await apiGet(baseUrl, '/api/wealth/goal', adminKey ? { 'X-Admin-Key': adminKey } : undefined));
  const goal = record(goalRaw.goal ?? goalRaw);
  const activity = await getActivityFeed(baseUrl, adminKey);
  const observedTsMs = Date.now();
  return {
    health,
    capital,
    internalPrime: {
      stateReady: bool(internalPrimeRaw.stateReady),
      status: text(internalPrimeRaw.status),
      reasonCodes: Array.isArray(internalPrimeRaw.reasonCodes ?? internalPrimeRaw.reason_codes) ? (internalPrimeRaw.reasonCodes ?? internalPrimeRaw.reason_codes).map(String) : undefined,
      allocatedCapitalUsd: num(internalPrimeRaw.allocatedCapitalUsd ?? internalPrimeRaw.allocated_capital_usd),
      availableCapitalUsd: num(internalPrimeRaw.availableCapitalUsd ?? internalPrimeRaw.available_capital_usd),
      reservedCapitalUsd: num(internalPrimeRaw.reservedCapitalUsd ?? internalPrimeRaw.reserved_capital_usd),
      deployedCapitalUsd: num(internalPrimeRaw.deployedCapitalUsd ?? internalPrimeRaw.deployed_capital_usd),
      updatedTsMs: num(internalPrimeRaw.updatedTsMs ?? internalPrimeRaw.updated_ts_ms),
    },
    wealthGoal: {
      goalId: text(goal.goal_id ?? goal.goalId),
      name: text(goal.name ?? goal.title),
      targetUsd: num(goal.target_usd ?? goal.targetUsd ?? goal.target),
      currentUsd: num(goal.current_usd ?? goal.currentUsd ?? goal.current),
      targetReturnPct: num(goal.target_return_pct ?? goal.targetReturnPct),
      timeframeDays: num(goal.timeframe_days ?? goal.timeframeDays),
      drawdownLimitPct: num(goal.drawdown_limit_pct ?? goal.drawdownLimitPct),
      riskTolerance: text(goal.risk_tolerance ?? goal.riskTolerance),
      progressPct: num(goal.progress_pct ?? goal.progressPct),
      requiredVelocityUsdPerDay: num(goal.required_velocity_usd_per_day ?? goal.requiredVelocityUsdPerDay),
      currentVelocityUsdPerDay: num(goal.current_velocity_usd_per_day ?? goal.currentVelocityUsdPerDay),
      status: text(goal.status),
      updatedTsMs: num(goal.updated_ts_ms ?? goal.updatedTsMs),
    },
    omar: {
      enabled: bool(summary.omar?.enabled),
      mode: text(summary.omar?.mode),
      recommendation: text(summary.omar?.recommendation),
      action: text(summary.omar?.action),
      sizePreference: num(summary.omar?.size_preference ?? summary.omar?.sizePreference),
      gasPreference: text(summary.omar?.gas_preference ?? summary.omar?.gasPreference),
      learningEligible: bool(summary.omar?.learning_eligible ?? summary.omar?.learningEligible),
      learningReasonCode: text(summary.omar?.learning_reason_code ?? summary.omar?.learningReasonCode),
      lastDecisionId: text(summary.omar?.last_decision_id ?? summary.omar?.lastDecisionId),
    },
    risk: {
      ok: bool(summary.risk?.ok),
      status: text(summary.risk?.status),
      reasonCodes: Array.isArray(summary.risk?.reason_codes ?? summary.risk?.reasonCodes) ? (summary.risk.reason_codes ?? summary.risk.reasonCodes).map(String) : undefined,
      drawdownPct: num(summary.risk?.drawdown_pct ?? summary.risk?.drawdownPct),
      riskScore: num(summary.risk?.risk_score ?? summary.risk?.riskScore),
      capitalLimitUsd: num(summary.risk?.capital_limit_usd ?? summary.risk?.capitalLimitUsd),
      activeFamilies: Array.isArray(summary.active_families) ? summary.active_families.map(String) : undefined,
      blockedFamilies: Array.isArray(summary.blocked_families) ? summary.blocked_families.map(String) : undefined,
      liveAuthority: Boolean(health.autoTrading && !health.dryRun),
    },
    opportunities,
    activity: { ...activity, decisions },
    observedTsMs,
    freshness: health.ok === false ? 'degraded' : 'fresh',
  };
}
