export type DataSource = "backend" | "demo";

export type TruthStatus = "canonical" | "warning" | "degraded" | "unknown";

export type ProjectionCompatibility = {
  status?: TruthStatus;
  reasonCodes?: string[];
  expectedTruthFamily?: string;
  expectedReadModel?: string;
  observedTruthFamily?: string;
  observedReadModel?: string;
  fallbackUsed?: boolean;
};

export type Freshness = {
  observedTsMs?: number;
  ageMs?: number | null;
  freshnessClass?: string;
  reasonCodes?: string[];
};

export type CapitalTruth = Freshness & {
  status?: string;
  blocked?: boolean;
  reasonCode?: string;
  reasonCodes?: string[];
  nextAction?: string;
  reliabilityClass?: string;
  recoveredFragile?: boolean;
};

export type DeploymentInfo = {
  ok?: boolean;
  branch?: string;
  commit?: string;
  version?: string;
  mode?: string;
  broadcastEnabled?: boolean;
  dryRun?: boolean;
  autoTrading?: boolean;
};

export type WealthGoal = {
  goalId?: string;
  targetReturnPct?: number;
  timeframeDays?: number;
  riskTolerance?: string;
  maxDrawdownPct?: number;
  currentReturnPct?: number;
  progressPct?: number;
  goalAchieved?: boolean;
  goalStatus?: string;
  goalUrgency?: string;
  goalVelocityPctPerDay?: number;
  requiredVelocityPctPerDay?: number;
  capitalBaseUsd?: number;
  executionRealismScore?: number;
  stabilityScore?: number;
  riskScore?: number;
  goalLadder?: number[];
};

export type OpportunityProjection = {
  id: string;
  strategyFamily?: string;
  routeFamily?: string;
  routeId?: string;
  chain?: string;
  pair?: string;
  expectedNetUsd?: number;
  expectedProfitUsd?: number;
  expectedRoiPct?: number;
  requiredCapitalUsd?: number;
  safeSizeUsd?: number;
  sizeMult?: number;
  borrowMult?: number;
  confidence?: number;
  admissionStatus?: string;
  admissionReasonCodes?: string[];
  executable?: boolean;
  observedTsMs?: number;
  raw?: Record<string, unknown>;
};

export type DecisionLineage = {
  decisionId: string;
  correlationId?: string;
  opportunityId?: string;
  routeId?: string;
  executionId?: string;
  receiptId?: string;
  transactionId?: string;
  outcomeId?: string;
  sizingId?: string;
  action?: string;
};

export type DecisionDetail = DecisionLineage & {
  ok?: boolean;
  strategyFamily?: string;
  expectedNetUsd?: number;
  realizedNetUsd?: number;
  expectationErrorUsd?: number;
  settlementVerified?: boolean;
  admission?: {
    allowed?: boolean;
    status?: string;
    reasonCodes?: string[];
  };
  sizing?: {
    requestedSizeMult?: number;
    sizeMult?: number;
    borrowMult?: number;
    amountInRaw?: string;
    amountInUsd?: number;
    provider?: string;
    providerLimit?: number;
  };
  execution?: {
    status?: string;
    lane?: string;
    sendMode?: string;
    provider?: string;
    venue?: string;
    txHash?: string;
    endpoint?: string;
    relay?: string;
  };
  receipt?: {
    status?: number;
    txHash?: string;
    blockNumber?: number;
    provider?: string;
    venue?: string;
  };
  settlement?: {
    verified?: boolean;
    realizedAfterGasUsd?: number;
    gasCostUsd?: number;
    borrowCostUsd?: number;
    netRealizedUsd?: number;
    source?: string;
  };
  learning?: {
    learned?: boolean;
    expectationErrorUsd?: number;
    attribution?: Record<string, unknown>;
  };
};

export type TransactionRecord = {
  transactionId?: string;
  receiptId?: string;
  txHash?: string;
  tsMs?: number;
  status?: number | string;
  type?: string;
  strategyFamily?: string;
  provider?: string;
  venue?: string;
  chain?: string;
  lane?: string;
  amountUsd?: number;
  realizedNetUsd?: number;
  gasCostUsd?: number;
  borrowCostUsd?: number;
  decisionId?: string;
  metadata?: Record<string, unknown>;
  raw?: Record<string, unknown>;
};

export type FundLedgerProjection = {
  ok?: boolean;
  balanceSource?: string;
  transactionCount?: number;
  balances?: Record<string, number>;
  transactions?: TransactionRecord[];
  tail?: TransactionRecord[];
  capitalTruth?: CapitalTruth;
  internalPrime?: InternalPrimeState;
};

export type InternalPrimeState = {
  borrowedUsd?: number;
  capacityUsd?: number;
  utilization?: number;
  inventory?: Record<string, number>;
  familyExposure?: Record<string, number>;
  openLoans?: Array<Record<string, unknown>>;
  loanCount?: number;
  stateReady?: boolean;
  stateStatus?: string;
  stateReasonCode?: string;
};

export type TreasuryState = {
  ok?: boolean;
  balanceUsd?: number;
  realizedProfitUsd?: number;
  reinvestableProfitUsd?: number;
  governance?: Record<string, unknown>;
  aggressiveness?: Record<string, unknown>;
  raw?: Record<string, unknown>;
};

export type CommandCenterCanonicalSnapshot = {
  ok: boolean;
  dataSource?: "backend" | "mock";
  liveMode?: "live" | "backend-mock" | "demo";
  sourceLabel?: string;
  observedTsMs?: number;
  summaryContract?: Record<string, unknown>;
  projectionCompatibility?: ProjectionCompatibility;
  capitalTruthHealth?: CapitalTruth;
  globalExecutionBlocked?: boolean;
  globalExecutionReasonCodes?: string[];
  portfolio?: {
    navUsd?: number;
    pct24h?: number;
    pct7d?: number;
    drawdownPct?: number;
    state?: string;
    updatedAtMs?: number;
  };
  wealthGoal?: WealthGoal | null;
  engines?: Array<{
    engineId: string;
    title: string;
    mode: string;
    lifecycle: string;
    opportunities: number;
    admitted: number;
    blocked: number;
    reason?: string;
  }>;
  execution?: {
    liveExecution?: {
      items?: Array<Record<string, unknown>>;
    };
  };
  services?: Record<string, unknown>;
  observability?: Record<string, unknown>;
};

export type CanonicalReadState<T> = {
  data: T | null;
  loading: boolean;
  error: string;
  stale: boolean;
  lastUpdatedMs: number | null;
};

export type CanonicalControlCommand = {
  patch: Record<string, unknown>;
  reason: string;
  confirmationToken?: string;
};
