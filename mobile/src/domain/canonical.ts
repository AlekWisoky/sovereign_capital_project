export type DataFreshness = "fresh" | "stale" | "degraded" | "unavailable";

export type CanonicalLineage = {
  decisionId?: string;
  correlationId?: string;
  executionId?: string;
  receiptId?: string;
  outcomeId?: string;
  sizingId?: string;
  opportunityId?: string;
  routeId?: string;
  action?: string;
};

export type RuntimeHealth = {
  ok?: boolean;
  status?: string;
  reasonCode?: string;
  deploymentMode?: string;
  autoTrading?: boolean;
  dryRun?: boolean;
  sendMode?: string;
  version?: string;
  commitSha?: string;
  observedTsMs?: number;
};

export type CapitalTruth = {
  ok?: boolean;
  status?: string;
  reasonCode?: string;
  freshnessClass?: string;
  reliabilityClass?: string;
  availableCapitalUsd?: number;
  settledCapitalUsd?: number;
  realizedPnlUsd?: number;
  reinvestableProfitUsd?: number;
  updatedTsMs?: number;
};

export type InternalPrime = {
  stateReady?: boolean;
  status?: string;
  reasonCodes?: string[];
  allocatedCapitalUsd?: number;
  availableCapitalUsd?: number;
  reservedCapitalUsd?: number;
  deployedCapitalUsd?: number;
  updatedTsMs?: number;
};

export type WealthGoal = {
  goalId?: string;
  name?: string;
  targetUsd?: number;
  currentUsd?: number;
  targetReturnPct?: number;
  timeframeDays?: number;
  drawdownLimitPct?: number;
  riskTolerance?: string;
  progressPct?: number;
  requiredVelocityUsdPerDay?: number;
  currentVelocityUsdPerDay?: number;
  status?: string;
  updatedTsMs?: number;
};

export type Opportunity = CanonicalLineage & {
  id?: string;
  title?: string;
  family?: string;
  strategyFamily?: string;
  routeId?: string;
  expectedGrossProfitUsd?: number;
  expectedNetProfitUsd?: number;
  expectedRoiPct?: number;
  requiredCapitalUsd?: number;
  confidence?: number;
  pSuccess?: number;
  marginRatio?: number;
  gasRatio?: number;
  mode?: string;
  lifecycle?: string;
  admitted?: boolean;
  blocked?: boolean;
  reasonCodes?: string[];
};

export type DecisionSnapshot = CanonicalLineage & {
  expectedNetProfitUsd?: number;
  expectedRoiPct?: number;
  requiredCapitalUsd?: number;
  proposedBorrowAmount?: string;
  borrowMult?: number;
  sizeMult?: number;
  pSuccess?: number;
  action?: string;
  strategyFamily?: string;
  governanceAllowed?: boolean;
  admissionAllowed?: boolean;
  admissionReasonCodes?: string[];
  settlementVerified?: boolean;
  realizedNetProfitUsd?: number;
  expectationErrorUsd?: number;
  learningRecorded?: boolean;
};

export type TransactionRecord = CanonicalLineage & {
  transactionId?: string;
  txHash?: string;
  receiptId?: string;
  status?: string | number;
  timestampMs?: number;
  chain?: string;
  provider?: string;
  route?: string;
  family?: string;
  amountInUsd?: number;
  gasCostUsd?: number;
  borrowCostUsd?: number;
  realizedNetProfitUsd?: number;
  signedPnlUsd?: number;
  success?: boolean;
  settlementVerified?: boolean;
};

export type LiveTrade = TransactionRecord & {
  state?: "pending" | "submitted" | "confirmed" | "failed" | "settled" | "unknown";
  submittedAtMs?: number;
  confirmedAtMs?: number;
};

export type OmarState = {
  enabled?: boolean;
  mode?: string;
  recommendation?: string;
  action?: string;
  sizePreference?: number;
  gasPreference?: string;
  learningEligible?: boolean;
  learningReasonCode?: string;
  lastDecisionId?: string;
};

export type RiskState = {
  ok?: boolean;
  status?: string;
  reasonCodes?: string[];
  drawdownPct?: number;
  riskScore?: number;
  capitalLimitUsd?: number;
  activeFamilies?: string[];
  blockedFamilies?: string[];
  liveAuthority?: boolean;
};

export type ActivityFeed = {
  transactions: TransactionRecord[];
  liveTrades: LiveTrade[];
  decisions: DecisionSnapshot[];
};

export type CanonicalSystemSnapshot = {
  health: RuntimeHealth;
  capital: CapitalTruth;
  internalPrime: InternalPrime;
  wealthGoal: WealthGoal;
  omar: OmarState;
  risk: RiskState;
  opportunities: Opportunity[];
  activity: ActivityFeed;
  observedTsMs: number;
  freshness: DataFreshness;
};
