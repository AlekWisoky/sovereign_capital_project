export type SystemState = "active" | "defensive" | "sandbox_only" | "paused";

export type SummaryReadContract = {
  ok?: boolean;
  contractVersion?: string;
  truthFamily?: string;
  readModel?: string;
  synthesized?: boolean;
  capitalContractVersion?: string;
  capitalPolicyVersion?: string;
  stateContract?: Record<string, unknown>;
  sourceContracts?: Record<string, unknown>;
};

export type ProjectionCompatibility = {
  status: "canonical" | "warning" | "degraded";
  reasonCodes: string[];
  expectedTruthFamily?: string;
  expectedReadModel?: string;
  observedTruthFamily?: string;
  observedReadModel?: string;
  fallbackUsed?: boolean;
  sources?: Record<string, ProjectionCompatibility>;
};

export type ControlMode = "view_only" | "assist" | "auto";

export type CapitalTruthStateContract = {
  status?: string;
  blocked?: boolean;
  reasonCode?: string;
  reasonCodes?: string[];
  nextAction?: string;
};

export type CapitalTruthHealth = {
  status?: string;
  blocked?: boolean;
  reasonCode?: string;
  reasonCodes?: string[];
  freshnessClass?: string;
  freshnessReasonCode?: string;
  freshnessReasonCodes?: string[];
  nextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryHistoryStatus?: string;
  reliabilityClass?: string;
  reliabilityReasonCode?: string;
  reliabilityReasonCodes?: string[];
  recoveredFragile?: boolean;
  observedTsMs?: number;
  ledgerLastTsMs?: number;
  ageMs?: number | null;
  stateContract?: CapitalTruthStateContract;
};

export type PortfolioSummary = {
  navUsd: number;
  pct24h: number;
  pct7d: number;
  drawdownPct: number;
  state: SystemState;
  updatedAtMs: number;
};

export type ExposureState = {
  activePct: number;
  sandboxPct: number;
  idlePct: number;
  atRiskPct: number;
};

export type AlertItem = {
  id: string;
  tsMs: number;
  severity: "info" | "warn" | "danger";
  title: string;
  detail: string;
};

export type StrategyAllocation = {
  id: string;
  name: string;
  capitalUsd: number;
  roiPct: number;
  volPct: number;
  riskScore: number; // 0-100
  status: "active" | "sandbox" | "paused" | "probation";
};

export type CapitalFlowEvent = {
  id: string;
  tsMs: number;
  from: string;
  to: string;
  amountUsd: number;
  triggeredBy: "ai" | "operator" | "risk" | "system";
  why: string;
  riskResult: "approved" | "clamped" | "rejected";
  execSummary?: string;
};

export type AIDecisionEvent = {
  id: string;
  tsMs: number;
  intent: string;
  confidence: number; // 0-1
  strategies: string[];
  outcome?: "success" | "fail" | "skipped";
  reward?: number;
  rewardTrace?: Record<string, unknown>;
  notes?: string;
};

export type RegimeState = {
  current: string;
  confidence: number; // 0-1
  history: { tsMs: number; regime: string }[];
};

export type RiskState = {
  composite: number; // 0-100
  caps: {
    maxDailyLossPct: number;
    maxExposurePct: number;
    sandboxCapPct: number;
    probationCapPct: number;
  };
  breakers: {
    drawdownBreaker: boolean;
    gasAnomalyBreaker: boolean;
    driftBreaker: boolean;
  };
};


export type EngineSnapshot = {
  engineId: string;
  title: string;
  mode: string;
  lifecycle: string;
  opportunities: number;
  admitted: number;
  blocked: number;
  capitalCapPct?: number;
  confidenceFloor?: number;
  reason?: string;
};

export type WealthGoalState = {
  targetReturnPct: number;
  timeframeDays: number;
  riskTolerance: string;
  maxDrawdownPct?: number;
  capitalCommitmentPct?: number;
  currentReturnPct?: number;
  progressPct?: number;
  goalAchieved?: boolean;
  goalStatus?: string;
  goalUrgency?: string;
  suggestedNextTargetPct?: number;
  goalId?: string;
  activeSinceMs?: number;
  achievedAtMs?: number;
  nextGoalAllowed?: boolean;
  pacing?: string;
  aggressivenessCap?: number;
  nextGoalAggressivenessHint?: number;
  goalVelocityPctPerDay?: number;
  requiredVelocityPctPerDay?: number;
  goalHorizonCompatibility?: number;
  elapsedGoalDays?: number;
  nextGoalReasons?: string[];
  nextGoalBlockedReasons?: string[];
  blockedGoalReasonCodes?: string[];
  pacingReasons?: string[];
  goalLadder?: number[];
  capitalBaseUsd?: number;
  executionRealismScore?: number;
  stabilityScore?: number;
  riskScore?: number;
  explanation?: Record<string, unknown>;
  history?: Array<Record<string, unknown>>;
};

export type AggressionMode = "conservative" | "balanced" | "aggressive";



export type LaunchMode = "V1_ONLY" | "V1_PLUS_STABLE_ALPHA" | "STAGED_MULTI_STRATEGY" | "FULL_MULTI_STRATEGY";

export type FamilyHealthState = 'live' | 'degraded' | 'observe_only' | 'capped_live' | 'disabled' | 'quarantined';

export type FamilyReadiness = {
  family: string;
  score: number;
  ready: boolean;
  status: 'eligible' | 'blocked' | 'degraded' | 'quarantined';
  reasons: string[];
  blockers: string[];
  count: number;
  successRate: number;
  gasEfficiency: number;
  calibrationQuality: number;
  routeReliability?: number;
  venueReliability?: number;
  competitionPressure?: number;
  telemetrySufficient?: boolean;
  capitalReady?: boolean;
  internalPrimeReady?: boolean;
  stageAllowed: boolean;
  active: boolean;
  rolloutIndex: number;
  degradedState?: string;
  currentHealthState?: FamilyHealthState | string;
  suggestedNextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
  capitalTruthRecoveryHistoryStatus?: string;
  capitalTruthDegradedSinceTsMs?: number;
  capitalTruthRecoveredAtTsMs?: number;
  capitalTruthDegradedDurationMs?: number;
  capitalTruthDegradedCount?: number;
  capitalTruthLastHealthyTsMs?: number;
  capitalTruthRecoveredRecently?: boolean;
  capitalTruthDegradationSeverityClass?: string;
  internalPrimeRecoveryHistoryStatus?: string;
  internalPrimeDegradedSinceTsMs?: number;
  internalPrimeRecoveredAtTsMs?: number;
  internalPrimeDegradedDurationMs?: number;
  internalPrimeDegradedCount?: number;
  internalPrimeLastHealthyTsMs?: number;
  internalPrimeRecoveredRecently?: boolean;
  internalPrimeDegradationSeverityClass?: string;
  riskLevel?: 'low' | 'medium' | 'high' | string;
  explorationBudgetOpen?: boolean;
};

export type LaunchRecommendation = {
  capitalTruthHealth?: CapitalTruthHealth;
  nextFamily: string;
  whyNow: string[];
  whyNotOthers: Record<string, string>;
  whyNotOthersDetails?: Record<string, LaunchBlockedFamilyDetail>;
  rollbackRecommendation?: string;
  globalExecutionBlocked?: boolean;
  globalExecutionReasonCodes?: string[];
  executionAdvisoryActive?: boolean;
  executionAdvisorySeverity?: string;
  executionAdvisoryClass?: string;
  executionAdvisoryReasonCode?: string;
  executionAdvisoryReasonCodes?: string[];
  executionAdvisoryNextAction?: string;
  capitalTruthReasonCodes?: string[];
  internalPrimeReasonCodes?: string[];
  holdReasonCode?: string;
  holdReasonCodes?: string[];
  suggestedNextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
};

export type LaunchBlockedFamilyDetail = {
  capitalTruthHealth?: CapitalTruthHealth;
  reasonCode: string;
  blockedBy: string[];
  suggestedNextAction?: string;
  capitalTruthReasonCodes?: string[];
  globalExecutionReasonCodes?: string[];
  internalPrimeReasonCodes?: string[];
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
  status?: string;
  degradedState?: string;
};

export type LaunchSummary = {
  summaryContract?: SummaryReadContract;
  projectionCompatibility?: ProjectionCompatibility;
  capitalTruthHealth?: CapitalTruthHealth;
  currentLaunchMode: LaunchMode;
  activeFamilies: string[];
  nextRecommendedFamily: string;
  blockedFamilies: Record<string, string>;
  blockedFamilyDetails?: Record<string, LaunchBlockedFamilyDetail>;
  families: FamilyReadiness[];
  reasons: string[];
  recommendation?: LaunchRecommendation;
  rollbackRecommendation?: string;
  healthGraph?: Record<string, unknown>;
  globalExecutionBlocked?: boolean;
  globalExecutionReasonCodes?: string[];
  capitalTruthReasonCodes?: string[];
  internalPrimeReasonCodes?: string[];
  holdReasonCode?: string;
  holdReasonCodes?: string[];
  suggestedNextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
};

export type ProfitMixItem = {
  family: string;
  contributionPct: number;
  returnOnDeployedCapital: number;
  failureAdjustedProfitability: number;
  costAdjustedProfitability: number;
  readinessToScale: number;
};

export type FundHealthSummary = {
  summaryContract?: SummaryReadContract;
  projectionCompatibility?: ProjectionCompatibility;
  capitalTruthHealth?: CapitalTruthHealth;
  fundStage: string;
  riskPosture: string;
  riskScore: number;
  capitalQualityScore?: number;
  researchQualityScore?: number;
  falseAdmissionRate?: number;
  falseDropRate?: number;
  globalExecutionBlocked?: boolean;
  globalExecutionReasonCodes?: string[];
  capitalTruthStatus?: string;
  capitalTruthReasonCodes?: string[];
  internalPrimeReasonCodes?: string[];
  holdReasonCode?: string;
  holdReasonCodes?: string[];
  suggestedNextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
  capitalTruthRecoveryHistoryStatus?: string;
  capitalTruthDegradedSinceTsMs?: number;
  capitalTruthRecoveredAtTsMs?: number;
  capitalTruthDegradedDurationMs?: number;
  capitalTruthDegradedCount?: number;
  capitalTruthLastHealthyTsMs?: number;
  capitalTruthRecoveredRecently?: boolean;
  capitalTruthDegradationSeverityClass?: string;
  internalPrimeRecoveryHistoryStatus?: string;
  internalPrimeDegradedSinceTsMs?: number;
  internalPrimeRecoveredAtTsMs?: number;
  internalPrimeDegradedDurationMs?: number;
  internalPrimeDegradedCount?: number;
  internalPrimeLastHealthyTsMs?: number;
  internalPrimeRecoveredRecently?: boolean;
  internalPrimeDegradationSeverityClass?: string;
  capitalTruthObservedTsMs?: number;
  capitalTruthLedgerLastTsMs?: number;
  capitalTruthAgeMs?: number | null;
  capitalTruthFreshnessClass?: string;
  capitalTruthFreshnessReasonCodes?: string[];
  internalPrimeJournalLastTsMs?: number;
  internalPrimeJournalAgeMs?: number | null;
  internalPrimeFreshnessClass?: string;
  internalPrimeFreshnessReasonCodes?: string[];
  capitalReady?: boolean;
  internalPrimeReady?: boolean;
};

export type GovernanceRules = {
  v1Focus: "flashloan_atomic";
  aiAuthority: "read_only" | "bounded" | "full";
  controlMode?: ControlMode;
  governanceEnabled: boolean;
  mutationEnabled: boolean;
  evolutionFrozen: boolean;
  allocationsFrozen: boolean;
  sandboxOnly: boolean;
  paused: boolean;

  // Advanced toggles (additive)
  metricsEnabled?: boolean;
  latencyProfilingEnabled?: boolean;
  rewardTraceEnabled?: boolean;
  rftEpisodeExportEnabled?: boolean;
  chaosBreakersEnabled?: boolean;
  rpcBatchEnabled?: boolean;
  kellyEnabled?: boolean;
  autoReinvestEnabled?: boolean;
  forceSendMode?: "" | "public" | "private" | "protected_rpc";
  forceGasMode?: "" | "standard" | "fast" | "instant";
  brainMode?: "" | "off" | "rl" | "baseline";
  aggressionMode?: AggressionMode;
  fullSystemEnabled?: boolean;
};


export type ExecutionDiagnostics = {
  endpointQuality?: { lanes?: Record<string, { endpoints?: Array<{ endpoint: string; score: number; avg_latency_ms?: number; success_rate?: number; timeout_rate?: number; error_rate?: number }>; relays?: Array<{ endpoint: string; score: number; avg_latency_ms?: number; success_rate?: number }> }> };
  endpointUniverse?: Record<string, { lane?: string; reason?: string; candidates?: Array<{ url?: string; endpoint?: string; source?: string; operator_preferred?: boolean; privacy_class?: string }>; relays?: Array<{ url?: string; endpoint?: string; source?: string; operator_preferred?: boolean; privacy_class?: string }> }>;
  routeQuality?: { items?: Array<{ key: string; route_family: string; venue_subset: string[]; split_signature: string; success_rate: number; mean_realized_edge_usd: number; quality: number; pair?: string; size_bucket?: string; latency_class?: string }> };
  liveExecution?: { items?: Array<{ txHash: string; routeFamily: string; family: string; lane: string; endpoint: string; relay?: string; endpointReason?: string; endpointUniverseReason?: string; selectedVenues?: string[]; fallbackReady?: boolean; routeExecutable?: boolean; routeInvalidCauses?: string[]; adversarial?: { pendingCount?: number; staleProbability?: number; interferenceProbability?: number; postOrderingRealizedEdge?: number; copyRisk?: number; relayNecessity?: number; requiresPrivateLane?: boolean }; flashloan?: { providerPriority?: string[]; selectedProvider?: string; fallbackProvider?: string; providerChoiceReason?: string; reserveDistortion?: number; routeViable?: boolean; searcherInvalidation?: boolean; routeMutationRequired?: boolean; reasonCodes?: string[]; sizing?: { allowed?: boolean; requested_size_mult?: number; size_mult?: number; borrow_mult?: number; net_edge?: number; fragility?: number; provider_limit?: number; provider_choice_reason?: string; reason_codes?: string[] } }; tsMs?: number }> };
  venueScorecards?: { items?: Array<{ venue: string; quality: number; success_rate?: number; mean_edge_usd?: number; pair?: string; size_bucket?: string; latency_class?: string }> };
  drawdown?: { drawdownPct?: number; intradayLossUsd?: number; hardStop?: { active?: boolean; reason_codes?: string[] }; familyDrawdown?: Record<string, number> };
  killSwitch?: { suppressions?: Record<string, unknown>; history?: Array<Record<string, unknown>>; metrics?: Record<string, unknown> };
};

export type ServiceHealthSummary = {
  admission?: { ok?: boolean; lastRouteFamily?: string; lastLane?: string; fallbackReady?: boolean; routeExecutable?: boolean; drawdownHardStop?: boolean };
  execution?: { ok?: boolean; lastEndpoint?: string; lastLane?: string; lastRelay?: string; routeExecutable?: boolean; fallbackReady?: boolean; routeInvalidCauses?: string[] };
  receipt?: { ok?: boolean; lastTxHash?: string; lastRouteFamily?: string; lastProvider?: string };
  telemetry?: { ok?: boolean; tailCount?: number; liveItems?: number; feedback?: Record<string, unknown> };
  wealthGoal?: { goalId?: string; progressPct?: number; pacing?: string; goalAchieved?: boolean; nextGoalAllowed?: boolean; nextGoalBlockedReasons?: string[]; capitalBaseUsd?: number; executionRealismScore?: number; stabilityScore?: number };
};

export type GovernanceChangeEvent = {
  id: string;
  tsMs: number;
  actor: string;
  action: string;
  reason: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  hash: string;
  prevHash: string;
};

export type MutationProposal = {
  id: string;
  tsMs: number;
  title: string;
  summary: string;
  expectedDeltaPct: number;
  riskDelta: number;
  probationCapPct: number;
  status: "queued" | "approved" | "rejected";
};

export type EquityPoint = { tsMs: number; navUsd: number; regime?: string };

export type CommandCenterSnapshot = {
  summaryContract?: SummaryReadContract;
  projectionCompatibility?: ProjectionCompatibility;
  capitalTruthHealth?: CapitalTruthHealth;
  ok: boolean;
  portfolio: PortfolioSummary;
  controlMode?: ControlMode;
  pausedReason?: string;
  globalExecutionBlocked?: boolean;
  globalExecutionReasonCodes?: string[];
  executionAdvisoryActive?: boolean;
  executionAdvisorySeverity?: string;
  executionAdvisoryClass?: string;
  executionAdvisoryReasonCode?: string;
  executionAdvisoryReasonCodes?: string[];
  executionAdvisoryNextAction?: string;
  capitalTruthReasonCodes?: string[];
  internalPrimeReasonCodes?: string[];
  holdReasonCode?: string;
  holdReasonCodes?: string[];
  suggestedNextAction?: string;
  recoveryReady?: boolean;
  recoveryStatus?: string;
  recoveryReasonCode?: string;
  recoveryReasonCodes?: string[];
  recoveryNextAction?: string;
  recoveryFreshnessClass?: string;
  recoveryFreshnessReasonCode?: string;
  recoveryFreshnessReasonCodes?: string[];
  recoveryFreshnessNextAction?: string;
  recoveryHistoryComponent?: string;
  recoveryHistoryStatus?: string;
  recoveryDegradedSinceTsMs?: number;
  recoveryRecoveredAtTsMs?: number;
  recoveryDegradedDurationMs?: number;
  recoveryDegradedCount?: number;
  recoveryLastHealthyTsMs?: number;
  recoveryRecoveredRecently?: boolean;
  recoveryDegradationSeverityClass?: string;
  capitalTruthReliabilityClass?: string;
  capitalTruthReliabilityReasonCode?: string;
  capitalTruthReliabilityReasonCodes?: string[];
  capitalTruthRecoveredFragile?: boolean;
  internalPrimeReliabilityClass?: string;
  internalPrimeReliabilityReasonCode?: string;
  internalPrimeReliabilityReasonCodes?: string[];
  internalPrimeRecoveredFragile?: boolean;
  recoveryReliabilityClass?: string;
  recoveryReliabilityReasonCode?: string;
  recoveryReliabilityReasonCodes?: string[];
  recoveryReliabilityNextAction?: string;
  recoveryRecoveredFragile?: boolean;
  capitalTruthRecoveryHistoryStatus?: string;
  capitalTruthDegradedSinceTsMs?: number;
  capitalTruthRecoveredAtTsMs?: number;
  capitalTruthDegradedDurationMs?: number;
  capitalTruthDegradedCount?: number;
  capitalTruthLastHealthyTsMs?: number;
  capitalTruthRecoveredRecently?: boolean;
  capitalTruthDegradationSeverityClass?: string;
  internalPrimeRecoveryHistoryStatus?: string;
  internalPrimeDegradedSinceTsMs?: number;
  internalPrimeRecoveredAtTsMs?: number;
  internalPrimeDegradedDurationMs?: number;
  internalPrimeDegradedCount?: number;
  internalPrimeLastHealthyTsMs?: number;
  internalPrimeRecoveredRecently?: boolean;
  internalPrimeDegradationSeverityClass?: string;
  capitalTruthFreshnessClass?: string;
  capitalTruthFreshnessReasonCodes?: string[];
  internalPrimeFreshnessClass?: string;
  internalPrimeFreshnessReasonCodes?: string[];
  rpcDegraded?: boolean;
  dataSource?: "backend" | "mock";
  liveMode?: "live" | "backend-mock" | "demo";
  sourceLabel?: string;
  engines?: EngineSnapshot[];
  wealthGoal?: WealthGoalState | null;
  aiIntent: { intent: string; confidence: number; strategies: string[] };
  exposure: ExposureState;
  alerts: AlertItem[];
  allocations: StrategyAllocation[];
  capitalFlows: CapitalFlowEvent[];
  decisions: AIDecisionEvent[];
  regime: RegimeState;
  risk: RiskState;
  governance: GovernanceRules;
  governanceHistory: GovernanceChangeEvent[];
  sandbox: {
    sandboxNavUsd: number;
    probationTradesLeft: number;
    proposals: MutationProposal[];
  };
  analytics: {
    equity: EquityPoint[];
    realizedAfterGas?: { tsMs: number; valueUsd: number }[];
    drawdown?: { tsMs: number; drawdownPct: number }[];
    laneSuccess?: { lane: string; successPct: number; stalePct: number }[];
    venueQuality?: { venue: string; quality: number; successPct: number }[];
    utilizationPct: number;
    returnPerRisk: number;
    execSuccessPct: number;
    slippagePct: number;
    complexityCost: number;
  };
  fundSummary?: FundHealthSummary;
  launch?: LaunchSummary;
  profitMix?: { families: ProfitMixItem[]; totalRealizedPnlUsd: number };
  execution?: ExecutionDiagnostics;
  services?: ServiceHealthSummary;
  observability: {
    loopMsP50: number;
    loopMsP90?: number;
    loopMsP99?: number;
    rpcErrRate: number;
    oppsSeen: number;
    oppsExecutable: number;
    execLatencyMsP50?: number;
    execLatencyMsP90?: number;
    execLatencyMsP99?: number;
    submitToReceiptMsP50?: number;
    submitToReceiptMsP90?: number;
    submitToReceiptMsP99?: number;
  };
};

export type ControlPatch = Partial<{
  controlMode: ControlMode;
  paused: boolean;
  sandboxOnly: boolean;
  allocationsFrozen: boolean;
  evolutionFrozen: boolean;
  mutationEnabled: boolean;
  governanceEnabled: boolean;
  defensiveMode: boolean;
  reduceExposureHalf: boolean;

  metricsEnabled: boolean;
  latencyProfilingEnabled: boolean;
  rewardTraceEnabled: boolean;
  rftEpisodeExportEnabled: boolean;
  chaosBreakersEnabled: boolean;
  rpcBatchEnabled: boolean;
  kellyEnabled: boolean;
  autoReinvestEnabled: boolean;
  forceSendMode: "" | "public" | "private" | "protected_rpc";
  forceGasMode: "" | "standard" | "fast" | "instant";
  brainMode: "" | "off" | "rl" | "baseline";
  aggressionMode: AggressionMode;
  fullSystemEnabled: boolean;
}>;

export type ExplainAlternative = { kind: string; candidate: string; reason: string };
export type ExplainResponse = {
  ok: boolean;
  text: string;
  facts: Record<string, unknown>;
  causal?: {
    whyRoute?: string;
    whySize?: string;
    whyLane?: string;
    whyNow?: string;
    whyNot?: ExplainAlternative[];
    suppressionReasons?: string[];
    routeInvalidCauses?: string[];
    adversarialFragility?: Record<string, unknown>;
    flashloan?: Record<string, unknown>;
    serviceSummary?: ServiceHealthSummary;
  };
};
